import { z } from 'zod';

export const sessionClaimsSchema = z.object({
	sub: z.string().min(1),
	ver: z.number().int().positive(),
});

export type SessionClaims = z.infer<typeof sessionClaimsSchema>;
