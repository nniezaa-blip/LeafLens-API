export interface UserRow {
	email: string;
	id: string;
	password_hash: string;
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
