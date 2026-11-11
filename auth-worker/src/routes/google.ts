import { Hono } from 'hono';
import { verifyWithJwks } from 'hono/jwt';
import { z } from 'zod';

import type { AppEnvironment } from '../environment.ts';

import { getConfig } from '../config/get-config.ts';
import {
	findUserByEmail,
	findUserByGoogleSub,
	insertGoogleUser,
} from '../db/users.ts';
import { readJson } from '../http/read-json.ts';
import { signSession } from '../session/token.ts';

const GOOGLE_JWKS_URI = 'https://www.googleapis.com/oauth2/v3/certs';
const GOOGLE_ISSUER = 'https://accounts.google.com';

const requestSchema = z.object({ id_token: z.string().min(20) });

const claimsSchema = z.object({
	aud: z.union([z.string(), z.array(z.string())]),
	email: z.string().min(3),
	email_verified: z.union([z.boolean(), z.string()]).optional(),
	sub: z.string().min(1),
});

/**
Verifies a Google ID token and returns its claims, or null when rejected.
*/
const verifyGoogleToken = async (
	idToken: string,
	clientIds: string[],
): Promise<null | z.infer<typeof claimsSchema>> => {
	try {
		const payload = await verifyWithJwks(idToken, {
			allowedAlgorithms: ['RS256'],
			jwks_uri: GOOGLE_JWKS_URI,
			verification: { iss: GOOGLE_ISSUER },
		});
		const claims = claimsSchema.safeParse(payload);
		if (!claims.success) return null;

		const audiences = Array.isArray(claims.data.aud) ? claims.data.aud : [claims.data.aud];
		const audienceAllowed = audiences.some((audience) => clientIds.includes(audience));
		if (!audienceAllowed) return null;

		const verified = claims.data.email_verified;
		if (verified !== true && verified !== 'true') return null;

		return claims.data;
	} catch {
		return null;
	}
};

export const googleRoutes = new Hono<AppEnvironment>().post('/google', async (context) => {
	const config = getConfig(context.env);
	if (config.googleClientIds.length === 0) {
		return context.json({ error: 'google_not_configured' }, 503);
	}

	const body = await readJson(context, config.maxJsonBytes);
	if (!body.ok) {
		return context.json({ error: 'invalid_request' }, body.status);
	}

	const parsed = requestSchema.safeParse(body.value);
	if (!parsed.success) {
		return context.json({ error: 'invalid_request' }, 400);
	}

	const claims = await verifyGoogleToken(parsed.data.id_token, config.googleClientIds);
	if (!claims) {
		return context.json({ error: 'invalid_google_token' }, 401);
	}

	const email = claims.email.trim().toLowerCase();

	const linked = await findUserByGoogleSub(context.env.DB, claims.sub);
	if (linked) {
		const token = await signSession(config.jwt, {
			sub: linked.id,
			ver: linked.session_version,
		});
		return context.json({
			access_token: token,
			expires_in: config.jwt.ttlSeconds,
			token_type: 'Bearer',
			user: { email: linked.email, id: linked.id },
		});
	}

	const existing = await findUserByEmail(context.env.DB, email);
	if (existing) {
		// Never auto-link a Google identity onto an existing password account.
		return context.json(
			{ error: existing.password_hash ? 'link_required' : 'conflict' },
			409,
		);
	}

	const created = await insertGoogleUser(context.env.DB, email, claims.sub);
	if (!created) {
		return context.json({ error: 'email_exists' }, 409);
	}

	const token = await signSession(config.jwt, { sub: created.id, ver: 1 });
	return context.json(
		{
			access_token: token,
			expires_in: config.jwt.ttlSeconds,
			token_type: 'Bearer',
			user: { email: created.email, id: created.id },
		},
		201,
	);
});
