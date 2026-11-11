import type { Context } from 'hono';

export type JsonResult = { ok: false; status: 400 | 413 } | { ok: true; value: unknown };

/**
Reads a JSON body, rejecting oversized or malformed payloads.
*/
export const readJson = async (context: Context, maxBytes: number): Promise<JsonResult> => {
	const text = await context.req.text();
	if (text.length > maxBytes) {
		return { ok: false, status: 413 };
	}
	try {
		return { ok: true, value: JSON.parse(text) };
	} catch {
		return { ok: false, status: 400 };
	}
};
