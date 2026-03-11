#!/usr/bin/env node
import { VergeClient } from './client.js';
import {
  VergeAuthError,
  VergeConfigError,
  VergeConflictError,
  VergeNotFoundError,
  VergeServerError,
  VergeValidationError,
} from './errors.js';

const EXIT_SERVER = 1;
const EXIT_CONFIG = 2;
const EXIT_AUTH = 3;
const EXIT_NOT_FOUND = 4;
const EXIT_CONFLICT = 5;
const EXIT_VALIDATION = 6;

async function main(argv) {
  try {
    const { global, rest } = parseGlobal(argv);
    if (rest[0] !== 'sandbox') {
      throw new VergeConfigError('unsupported command; expected: sandbox');
    }

    const client = new VergeClient({ baseUrl: global.baseUrl, token: global.token });
    const result = await dispatchSandbox(client, rest.slice(1));
    emitResult(result, global.jsonOutput);
    return 0;
  } catch (error) {
    return handleError(error, argv.includes('--json'));
  }
}

function parseGlobal(argv) {
  const global = { baseUrl: undefined, token: undefined, jsonOutput: false };
  const rest = [];

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--base-url') global.baseUrl = argv[++i];
    else if (arg === '--token') global.token = argv[++i];
    else if (arg === '--json') global.jsonOutput = true;
    else rest.push(arg);
  }

  return { global, rest };
}

async function dispatchSandbox(client, args) {
  const command = args[0];

  if (command === 'list' || command === 'ls') return client.listSandboxes();
  if (command === 'create') {
    const opts = parseOptions(args.slice(1));
    return client.createSandbox({
      alias: opts.alias,
      width: Number(opts.width ?? 1280),
      height: Number(opts.height ?? 1024),
      ...(opts['default-url'] ? { default_url: opts['default-url'] } : {}),
      ...(opts.image ? { image: opts.image } : {}),
    });
  }

  const idOrAlias = args[1];
  if (!idOrAlias) throw new VergeConfigError('missing <id-or-alias>');
  if (command === 'get') return client.getSandbox(idOrAlias);
  if (command === 'update') {
    const opts = parseOptions(args.slice(2));
    if (!opts.alias) throw new VergeConfigError('missing required option --alias');
    return client.updateSandbox(idOrAlias, { alias: opts.alias });
  }
  if (command === 'pause') return client.pauseSandbox(idOrAlias);
  if (command === 'resume') return client.resumeSandbox(idOrAlias);
  if (command === 'rm') return client.deleteSandbox(idOrAlias);
  if (command === 'cdp') return client.getCdpInfo(idOrAlias);
  if (command === 'vnc') return client.getVncUrl(idOrAlias);

  throw new VergeConfigError(`unsupported sandbox command: ${command}`);
}

function parseOptions(args) {
  const options = {};
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg.startsWith('--')) {
      options[arg.slice(2)] = args[i + 1];
      i += 1;
    }
  }
  return options;
}

function emitResult(result, jsonOutput) {
  if (jsonOutput || typeof result === 'object') console.log(JSON.stringify(result, null, 2));
  else console.log(result);
}

function handleError(error, jsonOutput) {
  if (error instanceof VergeConfigError) return emitError(error.message, EXIT_CONFIG, jsonOutput);
  if (error instanceof VergeAuthError) return emitError(error.message, EXIT_AUTH, jsonOutput);
  if (error instanceof VergeNotFoundError) return emitError(error.message, EXIT_NOT_FOUND, jsonOutput);
  if (error instanceof VergeConflictError) return emitError(error.message, EXIT_CONFLICT, jsonOutput);
  if (error instanceof VergeValidationError) return emitError(error.message, EXIT_VALIDATION, jsonOutput);
  if (error instanceof VergeServerError) return emitError(error.message, EXIT_SERVER, jsonOutput);
  if (error instanceof Error) return emitError(error.message, EXIT_SERVER, jsonOutput);
  return emitError('unknown error', EXIT_SERVER, jsonOutput);
}

function emitError(message, code, jsonOutput) {
  const payload = { ok: false, error: message, exit_code: code };
  if (jsonOutput) console.error(JSON.stringify(payload, null, 2));
  else console.error(message);
  return code;
}

main(process.argv.slice(2)).then((code) => {
  process.exitCode = code;
});
