import { z } from 'zod';

const rsaPublicFields = {
	alg: z.literal('RS256'),
	e: z.string().min(1),
	kid: z.string().min(1),
	kty: z.literal('RSA'),
	n: z.string().min(1),
};

export const privateJwkSchema = z.strictObject({
	...rsaPublicFields,
	d: z.string().min(1),
	dp: z.string().min(1),
	dq: z.string().min(1),
	p: z.string().min(1),
	q: z.string().min(1),
	qi: z.string().min(1),
});

export const publicJwksSchema = z.array(z.strictObject(rsaPublicFields)).min(1);

export type PrivateJwk = z.infer<typeof privateJwkSchema>;
export type PublicJwk = z.infer<typeof publicJwksSchema>[number];
