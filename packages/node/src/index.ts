export {
  VergeClient,
  type VergeClientOptions,
  type FetchLike,
  type BrowserInfo,
  type SandboxResponse,
  type VncTicketResponse,
  type CdpInfoResponse,
  type CreateSandboxPayload,
  type UpdateSandboxPayload,
  type RequestErrorBody,
  type VncUrlResponse,
} from './client.js';

export {
  VergeError,
  VergeAuthError,
  VergeConfigError,
  VergeConflictError,
  VergeNotFoundError,
  VergeServerError,
  VergeValidationError,
} from './errors.js';
