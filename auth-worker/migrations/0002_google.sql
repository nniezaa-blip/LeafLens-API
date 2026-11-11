-- Allow Google-only accounts: password_hash becomes nullable and google_sub is
-- stored so a Google identity maps to exactly one user.
CREATE TABLE users_new (
	id TEXT PRIMARY KEY,
	email TEXT NOT NULL UNIQUE COLLATE NOCASE,
	password_hash TEXT,
	google_sub TEXT UNIQUE,
	email_verified INTEGER NOT NULL DEFAULT 0,
	session_version INTEGER NOT NULL DEFAULT 1,
	created_at INTEGER NOT NULL DEFAULT (unixepoch()),
	updated_at INTEGER NOT NULL DEFAULT (unixepoch()),

	CHECK (password_hash IS NOT NULL OR google_sub IS NOT NULL)
);

INSERT INTO users_new (id, email, password_hash, email_verified, session_version, created_at, updated_at)
SELECT id, email, password_hash, 1, session_version, created_at, updated_at FROM users;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;
