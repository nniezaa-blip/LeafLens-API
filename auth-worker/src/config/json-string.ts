import { z } from 'zod';

/**
Wraps a schema so it accepts a JSON-encoded string of that shape.
*/
export const jsonString = <Schema extends z.ZodType>(schema: Schema) =>
	z
		.string()
		.transform((raw, context): unknown => {
			try {
				return JSON.parse(raw);
			} catch {
				context.issues.push({ code: 'custom', input: raw, message: 'invalid JSON' });
				return z.NEVER;
			}
		})
		.pipe(schema);
