import { z } from 'zod';

export const connectionConfig = z.object({
  baseUrl: z.string().url().refine(value => {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password && !url.search && !url.hash;
  }, 'baseUrl must be HTTP(S) without credentials, query or fragment'),
  token: z.string().min(1),
  sandbox: z.string().trim().min(1),
  requestTimeoutMs: z.number().int().min(1).max(300_000).default(30_000),
  toolCallTimeoutMs: z.number().int().min(1).max(300_000).default(60_000),
  cdpTicketTtlSec: z.number().int().min(1).max(3600).default(300),
  handoffTtlSec: z.number().int().min(1).max(3600).default(300),
});

export type ConnectionConfig = z.infer<typeof connectionConfig>;
