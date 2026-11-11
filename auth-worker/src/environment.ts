/**
Bindings and per-request variables for the Lextari auth Worker.
*/
export interface Bindings {
	ARGON2_MEMORY_KIB: string;
	ARGON2_TIME_COST: string;
	CORS_ORIGINS: string;
	DB: D1Database;
	JWT_AUDIENCE: string;
	JWT_ISSUER: string;
	JWT_PRIVATE_JWK: string;
	JWT_PUBLIC_JWKS: string;
	LOGIN_LIMITER: RateLimit;
	MAX_JSON_BYTES: string;
	PASSWORD_PEPPER: string;
	SESSION_TTL_SECONDS: string;
}

export interface SessionUser {
	email: string;
	id: string;
}

export interface Variables {
	user: SessionUser;
}

export interface AppEnvironment {
	Bindings: Bindings;
	Variables: Variables;
}
