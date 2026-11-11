import { Hono } from 'hono';

import type { AppEnvironment } from '../environment.ts';

import { getConfig } from '../config/get-config.ts';

/**
Public JWKS so the API Worker can verify access tokens without calling back.
*/
export const wellKnownRoutes = new Hono<AppEnvironment>().get('/jwks.json', (context) => {
	const config = getConfig(context.env);
	context.header('Cache-Control', 'public, max-age=300');
	return context.json({ keys: config.jwt.publicKeys });
});
