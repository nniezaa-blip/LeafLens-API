import { Hono } from 'hono';

import type { AppEnvironment } from '../environment.ts';

import { getArgon2 } from '../auth/argon2.ts';
import { getDummyHash } from '../auth/dummy-hash.ts';
import { hashPassword, isPasswordCorrect } from '../auth/password.ts';
import { isAttemptAllowed } from '../auth/rate-limit.ts';
import { credentialsSchema } from '../auth/schemas.ts';
import { getConfig } from '../config/get-config.ts';
import { findUserByEmail, insertUser } from '../db/users.ts';
import { clientIp } from '../http/client-ip.ts';
import { readJson } from '../http/read-json.ts';
import { requireUser } from '../middleware/require-user.ts';
import { signSession } from '../session/token.ts';

/**
Response body every successful register/login returns.
*/
const sessionBody = (accessToken: string, expiresIn: number, user: { email: string; id: string }) => ({
	access_token: accessToken,
	expires_in: expiresIn,
	token_type: 'Bearer',
	user,
});

export const authRoutes = new Hono<AppEnvironment>()
	.post('/register', async (context) => {
		const config = getConfig(context.env);
		const body = await readJson(context, config.maxJsonBytes);
		if (!body.ok) {
			return context.json({ error: 'invalid_request' }, body.status);
		}

		const credentials = credentialsSchema.safeParse(body.value);
		if (!credentials.success) {
			return context.json({ error: 'invalid_request' }, 400);
		}

		const attemptKey = `register:${clientIp(context)}`;
		if (!(await isAttemptAllowed(context.env.LOGIN_LIMITER, attemptKey))) {
			return context.json({ error: 'too_many_attempts' }, 429);
		}

		const { email, password } = credentials.data;
		const argon2 = await getArgon2();
		const passwordHash = await hashPassword(argon2, config.password, password);
		const user = await insertUser(context.env.DB, email, passwordHash);
		if (!user) {
			return context.json({ error: 'email_exists' }, 409);
		}

		const token = await signSession(config.jwt, { sub: user.id, ver: 1 });
		return context.json(sessionBody(token, config.jwt.ttlSeconds, user), 201);
	})
	.post('/login', async (context) => {
		const config = getConfig(context.env);
		const body = await readJson(context, config.maxJsonBytes);
		if (!body.ok) {
			return context.json({ error: 'invalid_request' }, body.status);
		}

		const credentials = credentialsSchema.safeParse(body.value);
		if (!credentials.success) {
			return context.json({ error: 'invalid_request' }, 400);
		}

		const { email, password } = credentials.data;
		const attemptKey = `login:${clientIp(context)}:${email}`;
		if (!(await isAttemptAllowed(context.env.LOGIN_LIMITER, attemptKey))) {
			return context.json({ error: 'too_many_attempts' }, 429);
		}

		const argon2 = await getArgon2();
		const user = await findUserByEmail(context.env.DB, email);
		const hash = user?.password_hash ?? (await getDummyHash(argon2, config.password));
		const isValid = await isPasswordCorrect(argon2, {
			encoded: hash,
			password,
			pepper: config.password.pepper,
		});
		if (!user || !isValid) {
			return context.json({ error: 'invalid_credentials' }, 401);
		}

		const token = await signSession(config.jwt, { sub: user.id, ver: user.session_version });
		return context.json(
			sessionBody(token, config.jwt.ttlSeconds, { email: user.email, id: user.id }),
		);
	})
	.post('/logout', (context) => context.body(null, 204))
	.get('/me', requireUser, (context) => {
		context.header('Cache-Control', 'private, no-store');
		return context.json(context.var.user);
	});
