import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { HTTPException } from 'hono/http-exception';
import { secureHeaders } from 'hono/secure-headers';

import type { AppEnvironment } from './environment.ts';

import { getConfig } from './config/get-config.ts';
import { authRoutes } from './routes/auth.ts';
import { wellKnownRoutes } from './routes/jwks.ts';

export const app = new Hono<AppEnvironment>()
	.use(
		secureHeaders({
			contentSecurityPolicy: { defaultSrc: ["'none'"], frameAncestors: ["'none'"] },
		}),
	)
	.use(
		'*',
		cors({
			allowHeaders: ['authorization', 'content-type'],
			allowMethods: ['GET', 'POST', 'OPTIONS'],
			maxAge: 86400,
			origin: (origin, context) => {
				const allowed = getConfig(context.env).corsOrigins;
				return allowed.includes('*') || allowed.includes(origin) ? origin : null;
			},
		}),
	)
	.get('/health', (context) => context.json({ status: 'ok' }))
	.route('/auth', authRoutes)
	.route('/.well-known', wellKnownRoutes)
	.notFound((context) => context.json({ error: 'not found' }, 404))
	.onError((error, context) => {
		if (error instanceof HTTPException) {
			return error.getResponse();
		}
		console.error(error);
		return context.json({ error: 'internal error' }, 500);
	});
