import type { MiddlewareHandler } from 'hono';

import type { AppEnvironment } from '../environment.ts';

import { getConfig } from '../config/get-config.ts';
import { findUserById } from '../db/users.ts';
import { verifySession } from '../session/token.ts';

/**
Reads a bearer token from the Authorization header.
*/
const readBearerToken = (header: string | undefined): null | string => {
	if (!header) {
		return null;
	}
	const [scheme, value] = header.split(' ');
	if (scheme?.toLowerCase() !== 'bearer' || !value) {
		return null;
	}
	return value.trim();
};

/**
Rejects the request unless it carries a valid, unrevoked session token.
*/
export const requireUser: MiddlewareHandler<AppEnvironment> = async (context, next) => {
	const config = getConfig(context.env);
	const token = readBearerToken(context.req.header('authorization'));
	const claims = token === null ? null : await verifySession(config.jwt, token);
	if (!claims) {
		return context.json({ error: 'unauthorized' }, 401);
	}

	const user = await findUserById(context.env.DB, claims.sub);
	if (!user || user.session_version !== claims.ver) {
		return context.json({ error: 'unauthorized' }, 401);
	}

	context.set('user', { email: user.email, id: user.id });
	await next();
};
