import { sign, verifyWithJwks } from 'hono/jwt';

import type { Config } from '../config/schema.ts';
import type { SessionClaims } from './claims.ts';

import { sessionClaimsSchema } from './claims.ts';

type JwtConfig = Config['jwt'];

/**
Signs an RS256 session token for the given claims.
*/
export const signSession = async (jwt: JwtConfig, claims: SessionClaims): Promise<string> => {
	const now = Math.floor(Date.now() / 1000);
	return sign(
		{
			...claims,
			aud: jwt.audience,
			exp: now + jwt.ttlSeconds,
			iat: now,
			iss: jwt.issuer,
			nbf: now,
		},
		jwt.privateKey,
		'RS256',
	);
};

/**
Verifies a session token and returns its claims, or null when invalid.
*/
export const verifySession = async (
	jwt: JwtConfig,
	token: string,
): Promise<null | SessionClaims> => {
	try {
		const payload = await verifyWithJwks(token, {
			allowedAlgorithms: ['RS256'],
			keys: jwt.publicKeys,
			verification: { aud: jwt.audience, iss: jwt.issuer },
		});
		const claims = sessionClaimsSchema.safeParse(payload);
		return claims.success ? claims.data : null;
	} catch {
		return null;
	}
};
