#!/usr/bin/env node
import { cac } from 'cac';

import { VergeClient, type VergeClientOptions } from './client.js';
import {
  VergeAuthError,
  VergeConfigError,
  VergeConflictError,
  VergeNotFoundError,
  VergeServerError,
  VergeValidationError,
} from './errors.js';

const EXIT_OK = 0;
const EXIT_SERVER = 1;
const EXIT_CONFIG = 2;
const EXIT_AUTH = 3;
const EXIT_NOT_FOUND = 4;
const EXIT_CONFLICT = 5;
const EXIT_VALIDATION = 6;

type JsonPrimitive = boolean | number | string | null;
type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

interface GlobalOptions {
  baseUrl?: string;
  token?: string;
  json?: boolean;
  help?: boolean;
  version?: boolean;
}

interface CreateOptions extends GlobalOptions {
  alias?: string;
  width?: number;
  height?: number;
  defaultUrl?: string;
  image?: string;
}

interface UpdateOptions extends GlobalOptions {
  alias?: string;
}

interface CliIo {
  stdout: { log: (message: string) => void };
  stderr: { error: (message: string) => void };
}

interface RunCliOptions {
  argv: string[];
  clientFactory?: (options: VergeClientOptions) => VergeClient;
  io?: CliIo;
}

const VALUE_OPTIONS = new Map<string, string>([
  ['--base-url', '--base-url <url>'],
  ['--token', '--token <token>'],
]);

const TOP_LEVEL_COMMANDS = new Set(['sandbox']);

const defaultIo: CliIo = {
  stdout: { log: (message) => console.log(message) },
  stderr: { error: (message) => console.error(message) },
};

function parseDimensionOption(name: '--width' | '--height', value: number | undefined): number | undefined {
  if (value === undefined) return undefined;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  throw new VergeConfigError(`option \`${name} <${name.slice(2)}>\` value is invalid`);
}

function createCli(clientFactory: (options: VergeClientOptions) => VergeClient) {
  const cli = cac('verge-browser');
  cli.help();
  cli.version('0.1.0');

  cli
    .option('--base-url <url>', 'API base URL')
    .option('--token <token>', 'API bearer token')
    .option('--json', 'Emit JSON output');

  cli
    .command('sandbox <action> [idOrAlias]', 'Manage sandboxes')
    .usage('verge-browser sandbox <list|ls|create|get|update|pause|resume|rm|cdp|vnc> [idOrAlias] [options]')
    .option('--alias <alias>', 'Sandbox alias')
    .option('--width <width>', 'Viewport width in pixels', { type: ['number'] })
    .option('--height <height>', 'Viewport height in pixels', { type: ['number'] })
    .option('--default-url <url>', 'Default browser URL')
    .option('--image <image>', 'Runtime image override')
    .action(async (action: string, idOrAlias: string | undefined, options: CreateOptions & UpdateOptions) => {
      const client = clientFactory(toClientOptions(options));
      if (action === 'list' || action === 'ls') {
        return client.listSandboxes();
      }
      if (action === 'create') {
        const width = parseDimensionOption('--width', options.width) ?? 1280;
        const height = parseDimensionOption('--height', options.height) ?? 1024;
        return client.createSandbox({
          width,
          height,
          ...(options.alias ? { alias: options.alias } : {}),
          ...(options.defaultUrl ? { default_url: options.defaultUrl } : {}),
          ...(options.image ? { image: options.image } : {}),
        });
      }

      if (!idOrAlias) {
        throw new VergeConfigError('missing <id-or-alias>');
      }
      if (action === 'get') return client.getSandbox(idOrAlias);
      if (action === 'update') {
        if (!options.alias) {
          throw new VergeConfigError('missing required option --alias');
        }
        return client.updateSandbox(idOrAlias, { alias: options.alias });
      }
      if (action === 'pause') return client.pauseSandbox(idOrAlias);
      if (action === 'resume') return client.resumeSandbox(idOrAlias);
      if (action === 'rm') return client.deleteSandbox(idOrAlias);
      if (action === 'cdp') return client.getCdpInfo(idOrAlias);
      if (action === 'vnc') return client.getVncUrl(idOrAlias);
      throw new VergeConfigError(`unsupported sandbox command: ${action}`);
    });

  return cli;
}

function toClientOptions(options: GlobalOptions): VergeClientOptions {
  return {
    ...(options.baseUrl ? { baseUrl: options.baseUrl } : {}),
    ...(options.token ? { token: options.token } : {}),
  };
}

function validateGlobalOptionValues(argv: string[]): void {
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === undefined) continue;
    const optionName = VALUE_OPTIONS.get(arg);
    if (!optionName) continue;

    const next = argv[index + 1];
    const afterNext = argv[index + 2];
    const valueLooksMissing = next === undefined
      || next.startsWith('--')
      || (TOP_LEVEL_COMMANDS.has(next) && afterNext !== undefined);
    if (valueLooksMissing) {
      throw new VergeConfigError(`option \`${optionName}\` value is missing`);
    }
    index += 1;
  }
}

function emitResult(result: JsonValue | undefined, jsonOutput: boolean, io: CliIo): void {
  if (result === undefined) return;
  if (jsonOutput || typeof result === 'object') {
    io.stdout.log(JSON.stringify(result, null, 2));
    return;
  }
  io.stdout.log(String(result));
}

function emitError(message: string, code: number, jsonOutput: boolean, io: CliIo): number {
  const payload = { ok: false, error: message, exit_code: code };
  if (jsonOutput) {
    io.stderr.error(JSON.stringify(payload, null, 2));
  } else {
    io.stderr.error(message);
  }
  return code;
}

function handleError(error: unknown, jsonOutput: boolean, io: CliIo): number {
  if (error instanceof VergeConfigError) return emitError(error.message, EXIT_CONFIG, jsonOutput, io);
  if (error instanceof VergeAuthError) return emitError(error.message, EXIT_AUTH, jsonOutput, io);
  if (error instanceof VergeNotFoundError) return emitError(error.message, EXIT_NOT_FOUND, jsonOutput, io);
  if (error instanceof VergeConflictError) return emitError(error.message, EXIT_CONFLICT, jsonOutput, io);
  if (error instanceof VergeValidationError) return emitError(error.message, EXIT_VALIDATION, jsonOutput, io);
  if (error instanceof VergeServerError) return emitError(error.message, EXIT_SERVER, jsonOutput, io);
  if (error instanceof Error && error.name === 'CACError') return emitError(error.message, EXIT_CONFIG, jsonOutput, io);
  if (error instanceof Error) return emitError(error.message, EXIT_SERVER, jsonOutput, io);
  return emitError('unknown error', EXIT_SERVER, jsonOutput, io);
}

export async function runCli({ argv, clientFactory = (options) => new VergeClient(options), io = defaultIo }: RunCliOptions): Promise<number> {
  const cli = createCli(clientFactory);

  try {
    validateGlobalOptionValues(argv);
    cli.parse(['node', 'verge-browser', ...argv], { run: false });
    const matched = cli.matchedCommand;
    const options = cli.options as GlobalOptions;
    if (options.help || options.version) {
      return EXIT_OK;
    }
    if (!matched) {
      if (cli.args.length === 0) {
        cli.outputHelp();
        return EXIT_CONFIG;
      }
      throw new VergeConfigError(`unsupported command: ${cli.args.join(' ')}`);
    }

    const action = matched.commandAction;
    if (!action) {
      throw new VergeConfigError(`unsupported command: ${matched.rawName}`);
    }

    matched.checkRequiredArgs();
    matched.checkUnknownOptions();
    matched.checkOptionValue();

    const positionalArgs: Array<string | undefined> = [...cli.args];
    while (positionalArgs.length < matched.args.length) {
      positionalArgs.push(undefined);
    }

    const result = await action.apply(matched, [...positionalArgs, options]);
    emitResult(result as JsonValue | undefined, Boolean(options.json), io);
    return EXIT_OK;
  } catch (error) {
    return handleError(error, argv.includes('--json'), io);
  }
}

export async function main(argv: string[]): Promise<number> {
  return runCli({ argv });
}

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  main(process.argv.slice(2)).then((code) => {
    process.exitCode = code;
  });
}
