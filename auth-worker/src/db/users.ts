export interface UserRow {
	email: string;
	id: string;
	password_hash: null | string;
	session_version: number;
}

const USER_COLUMNS = 'id, email, password_hash, session_version';

/**
Finds a user by case-insensitive email.
*/
export const findUserByEmail = async (
	database: D1Database,
	email: string,
): Promise<null | UserRow> =>
	database
		.prepare(`SELECT ${USER_COLUMNS} FROM users WHERE email = ?`)
		.bind(email)
		.first<UserRow>();

/**
Finds a user by id.
*/
export const findUserById = async (database: D1Database, id: string): Promise<null | UserRow> =>
	database.prepare(`SELECT ${USER_COLUMNS} FROM users WHERE id = ?`).bind(id).first<UserRow>();

/**
Creates a user, or returns null when the email is already registered.
*/
export const insertUser = async (
	database: D1Database,
	email: string,
	passwordHash: string,
): Promise<null | { email: string; id: string }> =>
	database
		.prepare(
			`INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)
			 ON CONFLICT (email) DO NOTHING
			 RETURNING id, email`,
		)
		.bind(crypto.randomUUID(), email, passwordHash)
		.first<{ email: string; id: string }>();

/**
Finds a user by their Google subject claim.
*/
export const findUserByGoogleSub = async (
	database: D1Database,
	googleSub: string,
): Promise<null | UserRow> =>
	database
		.prepare(`SELECT ${USER_COLUMNS} FROM users WHERE google_sub = ?`)
		.bind(googleSub)
		.first<UserRow>();

/**
Creates a Google-only user, or returns null when the email is taken.
*/
export const insertGoogleUser = async (
	database: D1Database,
	email: string,
	googleSub: string,
): Promise<null | { email: string; id: string }> =>
	database
		.prepare(
			`INSERT INTO users (id, email, google_sub, email_verified) VALUES (?, ?, ?, 1)
			 ON CONFLICT DO NOTHING
			 RETURNING id, email`,
		)
		.bind(crypto.randomUUID(), email, googleSub)
		.first<{ email: string; id: string }>();
