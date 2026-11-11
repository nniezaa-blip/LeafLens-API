import { z } from 'zod';

import { privateJwkSchema, publicJwksSchema } from '../session/keys.ts';
import { jsonString } from './json-string.ts';

const positiveInt = z.coerce.number().int().positive();

export const configSchema = z
	.object({
		ARGON2_MEMORY_KIB: positiveInt,
		ARGON2_TIME_COST: positiveInt,
		CORS_ORIGINS: z.string(),
		JWT_AUDIENCE: z.string().min(1),
		JWT_ISSUER: z.string().min(1),
		JWT_PRIVATE_JWK: jsonString(privateJwkSchema),
		JWT_PUBLIC_JWKS: jsonString(publicJwksSchema),
		MAX_JSON_BYTES: positiveInt,
		PASSWORD_PEPPER: z.string().min(32),
		SESSION_TTL_SECONDS: positiveInt,
	})
	.refine(
		(environment) =>
			environment.JWT_PUBLIC_JWKS.some((key) => key.kid === environment.JWT_PRIVATE_JWK.kid),
		'JWT_PUBLIC_JWKS must contain the signing key kid',
	)
	.transform((environment) => ({
		corsOrigins: environment.CORS_ORIGINS.split(',')
			.map((origin) => origin.trim())
			.filter((origin) => origin.length > 0),
		jwt: {
			audience: environment.JWT_AUDIENCE,
			issuer: environment.JWT_ISSUER,
			privateKey: environment.JWT_PRIVATE_JWK,
			publicKeys: environment.JWT_PUBLIC_JWKS,
			ttlSeconds: environment.SESSION_TTL_SECONDS,
		},
		maxJsonBytes: environment.MAX_JSON_BYTES,
		password: {
			memoryKib: environment.ARGON2_MEMORY_KIB,
			pepper: environment.PASSWORD_PEPPER,
			timeCost: environment.ARGON2_TIME_COST,
		},
	}));

export type Config = z.infer<typeof configSchema>;
