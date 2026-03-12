#!/usr/bin/env node
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { basename, dirname, resolve } from 'node:path';
import { cac } from 'cac';

import {
  VergeClient,
  type BrowserActionsPayload,
  type JsonObject,
  type VergeClientOptions,
} from './client.js';
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
const FALLBACK_VERSION = '0.0.0';

interface GlobalOptions {
  baseUrl?: string;
  token?: string;
  json?: boolean;
  help?: boolean;
  version?: boolean;
}

interface SandboxOptions extends GlobalOptions {
  alias?: string;
  kind?: 'xvfb_vnc' | 'xpra';
  width?: number;
  height?: number;
  defaultUrl?: string;
  image?: string;
  metadata?: string;
}

interface BrowserScreenshotOptions extends GlobalOptions {
  type?: 'window' | 'page';
  format?: 'png' | 'jpeg' | 'webp';
  targetId?: string;
  output?: string;
}

interface BrowserActionsOptions extends GlobalOptions {
  input?: string;
  payload?: string;
}

interface FileWriteOptions extends GlobalOptions {
  content?: string;
  overwrite?: boolean;
}

interface FileDownloadOptions extends GlobalOptions {
  output?: string;
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
  ['--metadata', '--metadata <json>'],
  ['--input', '--input <file>'],
  ['--payload', '--payload <json>'],
  ['--content', '--content <text>'],
  ['--output', '--output <path>'],
]);

const TOP_LEVEL_COMMANDS = new Set(['sandbox', 'browser', 'files']);

const defaultIo: CliIo = {
  stdout: { log: (message) => console.log(message) },
  stderr: { error: (message) => console.error(message) },
};

function parseDimensionOption(name: '--width' | '--height', value: number | string | Array<number | string> | undefined | null): number | undefined {
  if (Array.isArray(value)) {
    if (value.length === 0) return undefined;
    return parseDimensionOption(name, value[value.length - 1]);
  }
  if (value === undefined || value === null || value === '') return undefined;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'number' && Number.isNaN(value)) return undefined;
  if (typeof value === 'string' && value.trim() === '') return undefined;
  if (typeof value === 'string' && Number.isFinite(Number(value))) return Number(value);
  throw new VergeConfigError(`option \`${name} <${name.slice(2)}>\` value is invalid`);
}

function parseJsonObjectOption(name: string, value: string | undefined): JsonObject | undefined {
  if (!value) return undefined;
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      throw new Error('expected object');
    }
    return parsed as JsonObject;
  } catch {
    throw new VergeConfigError(`option \`${name}\` must be valid JSON object`);
  }
}

function parseJsonValueOption<T>(name: string, value: string): T {
  try {
    return JSON.parse(value) as T;
  } catch {
    throw new VergeConfigError(`option \`${name}\` must be valid JSON`);
  }
}

async function readJsonFile<T>(path: string, label: string): Promise<T> {
  try {
    const content = await readFile(path, 'utf8');
    return JSON.parse(content) as T;
  } catch {
    throw new VergeConfigError(`${label} must be a readable JSON file`);
  }
}

async function writeOutputFile(path: string, data: Uint8Array | string): Promise<string> {
  const target = resolve(path);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, data);
  return target;
}

async function loadCliVersion(): Promise<string> {
  try {
    const packageJsonPath = new URL('../../package.json', import.meta.url);
    const content = await readFile(packageJsonPath, 'utf8');
    const parsed = JSON.parse(content) as { version?: unknown };
    return typeof parsed.version === 'string' ? parsed.version : FALLBACK_VERSION;
  } catch {
    return FALLBACK_VERSION;
  }
}

function createCli(clientFactory: (options: VergeClientOptions) => VergeClient, version: string) {
  const cli = cac('verge-browser');
  cli.help();
  cli.version(version);

  cli
    .option('--base-url <url>', 'API base URL')
    .option('--token <token>', 'API bearer token')
    .option('--json', 'Emit JSON output');

  cli
    .command('sandbox <action> [idOrAlias]', 'Manage sandboxes')
    .usage('verge-browser sandbox <list|ls|create|get|update|pause|resume|rm|cdp|session|restart> [idOrAlias] [options]')
    .option('--alias <alias>', 'Sandbox alias')
    .option('--kind <kind>', 'Sandbox kind: xvfb_vnc or xpra')
    .option('--width <width>', 'Viewport width in pixels', { type: ['number'] })
    .option('--height <height>', 'Viewport height in pixels', { type: ['number'] })
    .option('--default-url <url>', 'Default browser URL')
    .option('--image <image>', 'Runtime image override')
    .option('--metadata <json>', 'Sandbox metadata as JSON object')
    .action(async (action: string, idOrAlias: string | undefined, options: SandboxOptions) => {
      const client = clientFactory(toClientOptions(options));
      if (action === 'list' || action === 'ls') {
        return client.listSandboxes();
      }
      if (action === 'create') {
        const width = parseDimensionOption('--width', options.width);
        const height = parseDimensionOption('--height', options.height);
        const metadata = parseJsonObjectOption('--metadata', options.metadata);
        return client.createSandbox({
          ...(options.alias ? { alias: options.alias } : {}),
          ...(options.kind ? { kind: options.kind } : { kind: 'xvfb_vnc' }),
          ...(width !== undefined ? { width } : {}),
          ...(height !== undefined ? { height } : {}),
          ...(options.defaultUrl ? { default_url: options.defaultUrl } : {}),
          ...(options.image ? { image: options.image } : {}),
          ...(metadata ? { metadata } : {}),
        });
      }

      if (!idOrAlias) {
        throw new VergeConfigError('missing <id-or-alias>');
      }
      if (action === 'get') return client.getSandbox(idOrAlias);
      if (action === 'update') {
        const metadata = parseJsonObjectOption('--metadata', options.metadata);
        if (!options.alias && !metadata) {
          throw new VergeConfigError('missing update fields; pass --alias and/or --metadata');
        }
        return client.updateSandbox(idOrAlias, {
          ...(options.alias !== undefined ? { alias: options.alias } : {}),
          ...(metadata ? { metadata } : {}),
        });
      }
      if (action === 'pause') return client.pauseSandbox(idOrAlias);
      if (action === 'resume') return client.resumeSandbox(idOrAlias);
      if (action === 'rm') return client.deleteSandbox(idOrAlias);
      if (action === 'cdp') return client.getCdpInfo(idOrAlias);
      if (action === 'session') return client.getSessionUrl(idOrAlias);
      if (action === 'restart') return client.restartBrowser(idOrAlias);
      throw new VergeConfigError(`unsupported sandbox command: ${action}`);
    });

  cli
    .command('browser <action> <idOrAlias>', 'Inspect or control the browser inside a sandbox')
    .usage('verge-browser browser <screenshot|actions> <idOrAlias> [options]')
    .option('--type <type>', 'Screenshot type: window or page')
    .option('--format <format>', 'Screenshot format: png, jpeg, or webp')
    .option('--target-id <targetId>', 'Optional CDP target id for page screenshots')
    .option('--output <path>', 'Write screenshot bytes to a file')
    .option('--input <file>', 'JSON file for browser actions payload')
    .option('--payload <json>', 'Inline JSON payload for browser actions')
    .action(async (action: string, idOrAlias: string, options: BrowserScreenshotOptions & BrowserActionsOptions) => {
      const client = clientFactory(toClientOptions(options));
      if (action === 'screenshot') {
        const screenshot = await client.getBrowserScreenshot(idOrAlias, {
          ...(options.type ? { type: options.type } : {}),
          ...(options.format ? { format: options.format } : {}),
          ...(options.targetId ? { target_id: options.targetId } : {}),
        });
        if (options.output) {
          const target = await writeOutputFile(options.output, Buffer.from(screenshot.data_base64, 'base64'));
          return { ...screenshot, output: target };
        }
        return screenshot;
      }
      if (action === 'actions') {
        const payload = await loadBrowserActionsPayload(options);
        return client.executeBrowserActions(idOrAlias, payload);
      }
      throw new VergeConfigError(`unsupported browser command: ${action}`);
    });

  cli
    .command('files <action> <idOrAlias> [path]', 'Manage sandbox workspace files')
    .usage('verge-browser files <list|read|write|upload|download|rm> <idOrAlias> [path] [options]')
    .option('--content <text>', 'Inline text content for file writes')
    .option('--overwrite', 'Overwrite existing files')
    .option('--output <path>', 'Local output path for downloads')
    .action(async (action: string, idOrAlias: string, path: string | undefined, options: FileWriteOptions & FileDownloadOptions) => {
      const client = clientFactory(toClientOptions(options));
      if (action === 'list') {
        return client.listFiles(idOrAlias, path ?? '/workspace');
      }
      if (!path) {
        throw new VergeConfigError('missing <path>');
      }
      if (action === 'read') {
        const file = await client.readFile(idOrAlias, path);
        return options.json ? file : file.content;
      }
      if (action === 'write') {
        if (options.content === undefined) {
          throw new VergeConfigError('missing required option --content');
        }
        return client.writeFile(idOrAlias, { path, content: options.content, overwrite: Boolean(options.overwrite) });
      }
      if (action === 'upload') {
        const localPath = resolve(path);
        const bytes = await readFile(localPath);
        return client.uploadFile(idOrAlias, { filename: basename(localPath), data: bytes });
      }
      if (action === 'download') {
        const file = await client.downloadFile(idOrAlias, path);
        if (options.output) {
          const target = await writeOutputFile(options.output, file.data);
          return { path: file.path, output: target, contentType: file.contentType };
        }
        return { path: file.path, contentType: file.contentType, data_base64: Buffer.from(file.data).toString('base64') };
      }
      if (action === 'rm') {
        return client.deleteFile(idOrAlias, path);
      }
      throw new VergeConfigError(`unsupported files command: ${action}`);
    });

  return cli;
}

async function loadBrowserActionsPayload(options: BrowserActionsOptions): Promise<BrowserActionsPayload> {
  if (options.input) {
    return readJsonFile<BrowserActionsPayload>(options.input, 'option `--input`');
  }
  if (options.payload) {
    return parseJsonValueOption<BrowserActionsPayload>('--payload', options.payload);
  }
  throw new VergeConfigError('missing browser actions payload; pass --input or --payload');
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

function emitResult(result: unknown, jsonOutput: boolean, io: CliIo): void {
  if (result === undefined) return;
  if (typeof result === 'string' && !jsonOutput) {
    io.stdout.log(result);
    return;
  }
  io.stdout.log(JSON.stringify(result, null, 2));
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
  const version = await loadCliVersion();
  const cli = createCli(clientFactory, version);

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
    emitResult(result, Boolean(options.json), io);
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
