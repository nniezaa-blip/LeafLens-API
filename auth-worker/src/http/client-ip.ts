import type { Context } from 'hono';

/**
Returns the client IP that Cloudflare saw.
*/
export const clientIp = (context: Context): string =>
	context.req.header('cf-connecting-ip') ?? 'unknown';
