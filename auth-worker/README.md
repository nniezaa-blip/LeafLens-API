# lextari-auth

Authentication Worker for Lextari: **Hono + TypeScript on Cloudflare Workers, D1 storage, Argon2id passwords, RS256 JWTs with a public JWKS.**

It replaces Supabase Auth. The Flutter app logs in against this Worker; the Python API Worker only verifies the issued access token against `/.well-known/jwks.json`. It is a deliberate copy of the proven auth Worker in [`mishoshup/sillyusachi`](https://github.com/mishoshup/sillyusachi/tree/main/apps/api), narrowed to auth-only.

---

## 1. What lives here

```text
auth-worker/
├── migrations/
│   └── 0001_users.sql        # users table
├── scripts/
│   └── gen-keys.ts           # writes .dev.vars (RSA key pair + pepper)
├── src/
│   ├── app.ts                # Hono app: CORS, security headers, routes
│   ├── index.ts              # default export
│   ├── environment.ts        # Bindings / Variables types
│   ├── auth/
│   │   ├── argon2.ts         # one WASM instance per isolate
│   │   ├── password.ts       # pepper + Argon2id hash / verify
│   │   ├── dummy-hash.ts     # constant-cost miss for unknown emails
│   │   ├── rate-limit.ts     # Workers rate-limit binding
│   │   └── schemas.ts        # zod credential schema
│   ├── config/
│   │   ├── schema.ts         # vars + secrets → typed Config
│   │   ├── get-config.ts     # parsed once per env object
│   │   └── json-string.ts    # JSON-encoded env var helper
│   ├── db/users.ts           # D1 queries
│   ├── http/                 # client IP, bounded JSON reader
│   ├── middleware/
│   │   └── require-user.ts   # Bearer token → user
│   ├── routes/
│   │   ├── auth.ts           # register / login / logout / me
│   │   └── jwks.ts           # public JWKS
│   └── session/              # RS256 signing, claims, JWK schemas
└── wrangler.jsonc
```

Copied nearly verbatim from [`sillyusachi/apps/api`](https://github.com/mishoshup/sillyusachi/tree/main/apps/api) — specifically [`src/routes/auth.ts`](https://github.com/mishoshup/sillyusachi/blob/main/apps/api/src/routes/auth.ts), [`src/auth/`](https://github.com/mishoshup/sillyusachi/tree/main/apps/api/src/auth), [`src/session/`](https://github.com/mishoshup/sillyusachi/tree/main/apps/api/src/session), [`src/db/users.ts`](https://github.com/mishoshup/sillyusachi/blob/main/apps/api/src/db/users.ts), [`src/config/`](https://github.com/mishoshup/sillyusachi/tree/main/apps/api/src/config), and [`migrations/0003_users.sql`](https://github.com/mishoshup/sillyusachi/blob/main/apps/api/migrations/0003_users.sql).

Differences from [`sillyusachi`](https://github.com/mishoshup/sillyusachi), all deliberate:

| sillyusachi | here | Why |
|---|---|---|
| `username` | `email` | Lextari accounts are email-based. |
| `__Host-` session cookie | `access_token` in the JSON body, sent as `Authorization: Bearer` | Flutter mobile has no cookie jar. |
| single Worker for everything | auth Worker only | API Worker stays Python and only verifies tokens. |

---

## 2. Endpoints

| Method | Path | Auth | Success | Failure |
|---|---|---|---|---|
| `GET` | `/health` | — | `200 {"status":"ok"}` | — |
| `GET` | `/.well-known/jwks.json` | — | `200 {"keys":[…]}` | — |
| `POST` | `/auth/register` | — | `201` session body | `400 invalid_request`, `409 email_exists`, `413` body too large, `429 too_many_attempts` |
| `POST` | `/auth/login` | — | `200` session body | `400 invalid_request`, `401 invalid_credentials`, `429 too_many_attempts` |
| `POST` | `/auth/logout` | Bearer | `204` | — |
| `GET` | `/auth/me` | Bearer | `200 {"id","email"}` | `401 unauthorized` |

Session body:

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6…",
  "expires_in": 43200,
  "token_type": "Bearer",
  "user": { "id": "944bf52d-…", "email": "danial@example.com" }
}
```

Access-token claims: `sub` (user id), `ver` (`session_version`), `iss` (`lextari-auth`), `aud` (`lextari-app`), `iat`, `nbf`, `exp`. TTL is `SESSION_TTL_SECONDS` (default 12 h).

Error bodies are always `{"error":"<code>"}` so clients can map codes without parsing prose. Login never reveals whether the email exists: unknown email and wrong password both return `401 invalid_credentials`, and an unknown email is still checked against a cached dummy Argon2 hash so timing matches.

---

## 3. Security model

- **Argon2id** with 19 MiB, `t=2`, `p=1`, 32-byte output, compiled once per isolate from WASM.
- **Pepper**: the password is `HMAC-SHA256(password, PASSWORD_PEPPER)` before Argon2. The pepper is a Worker secret, never in D1, so a database dump alone cannot be attacked offline. `PASSWORD_PEPPER` is mandatory and must be at least 32 characters.
- **RS256** signing with the private JWK as a secret. The API verifies locally against the public JWKS; it never calls this Worker per request.
- **Rate limiting** via the Workers `ratelimits` binding: 5 attempts / 60 s per key, keyed `register:<ip>` and `login:<ip>:<email>`.
- **`ver` claim**: every `session_version` mismatch is rejected, giving a future password-change flow a way to invalidate existing tokens.
- Generic errors, bounded JSON bodies (`MAX_JSON_BYTES`), `secureHeaders`, and an explicit CORS allow-list.

### Known limitations

- `POST /auth/logout` is client-side only. Access tokens are stateless JWTs, so a copied token stays valid until `exp`. Add a D1 revocation list or shorten the TTL if that matters.
- No refresh tokens. On expiry the app logs in again (12 h default).
- No email verification, password reset, or Google login yet. Anyone can register with an arbitrary email.

---

## 4. Local development

```bash
cd auth-worker
bun install
bun run keys:dev                  # writes .dev.vars: RSA pair + pepper
bun run db:migrate                # applies migrations locally
bun run dev                       # http://127.0.0.1:8788
```

`keys:dev` refuses to overwrite an existing `.dev.vars`; pass `--force` to regenerate. Regenerating the key pair invalidates every issued token (expected); regenerating the pepper invalidates every stored password hash (see §6).

Flutter (`.env`):

```dotenv
AUTH_URL=http://10.0.2.2:8788   # 10.0.2.2 = host loopback from the Android emulator
```

Python API (`.dev.vars` / `wrangler.jsonc`):

```dotenv
AUTH_JWKS_URL=http://localhost:8788/.well-known/jwks.json
AUTH_ISSUER=lextari-auth
AUTH_AUDIENCE=lextari-app
```

Smoke test:

```bash
curl -s localhost:8788/health
curl -s localhost:8788/.well-known/jwks.json | head -c 120

curl -s -X POST localhost:8788/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"danial@example.com","password":"correcthorsebattery"}'

TOKEN=$(curl -s -X POST localhost:8788/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"danial@example.com","password":"correcthorsebattery"}' \
  | sed -E 's/.*"access_token":"([^"]+)".*/\1/')

curl -s localhost:8788/auth/me -H "authorization: Bearer $TOKEN"
curl -s -X POST localhost:8788/auth/register ...   # repeat → 409 email_exists
curl -s -X POST localhost:8788/auth/login -d '{"email":"danial@example.com","password":"wrongpassword"}' ...  # → 401
```

Last verified locally: `/health` 200, JWKS served with the expected `kid`, register 201, login 200, `/auth/me` 200 with a token and 401 without, wrong password 401, duplicate email 409, malformed email 400, logout 204.

### Deploying later

```bash
bunx wrangler d1 create lextari                       # put the id into d1_databases[0].database_id
bunx wrangler d1 migrations apply lextari --remote
bunx wrangler secret bulk < secrets.json              # JWT_PRIVATE_JWK, JWT_PUBLIC_JWKS, PASSWORD_PEPPER
bunx wrangler deploy
```

Point the API's `AUTH_JWKS_URL` at the deployed Worker and the Flutter `AUTH_URL` at the same origin.

---

## 5. Data model

```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  session_version INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);
```

`session_version` is bumped by any future password change; tokens carrying an older `ver` are rejected by `/auth/me` and by any Worker that checks it.

---

## 6. Rotating the pepper without breaking logins

`password_hash` covers the pepper, so replacing `PASSWORD_PEPPER` silently invalidates **every** existing hash: every user would get `401 invalid_credentials` forever, with no way to tell it apart from a wrong password. Rotate in place with a versioned pepper instead of swapping blindly.

### 6.1 Schema change

```sql
-- migrations/0002_pepper_versions.sql
ALTER TABLE users ADD COLUMN pepper_version INTEGER NOT NULL DEFAULT 1;
CREATE INDEX idx_users_pepper_version ON users(pepper_version);
```

Existing rows default to version `1`, which is correct while `PASSWORD_PEPPER` is still pepper v1.

### 6.2 Config change

Keep the current pepper in `PASSWORD_PEPPER` and add the old one(s) as a JSON secret, e.g. `PASSWORD_PEPPERS`:

```json
{ "1": "old-pepper-value", "2": "current-pepper-value" }
```

```ts
// src/config/schema.ts
PASSWORD_PEPPERS: jsonString(z.record(z.string(), z.string().min(32))),
PEPPER_VERSION: positiveInt,

// transform
password: {
  memoryKib: environment.ARGON2_MEMORY_KIB,
  pepper: environment.PASSWORD_PEPPER,          // current
  peppers: environment.PASSWORD_PEPPERS,       // every version still in the wild
  version: environment.PEPPER_VERSION,
  timeCost: environment.ARGON2_TIME_COST,
},
```

### 6.3 Login flow: verify with the stored version, then rehash

```ts
const user = await findUserByEmail(context.env.DB, email);
const storedPepper = config.password.peppers[String(user?.pepper_version ?? 1)];
const isValid = await isPasswordCorrect(argon2, {
  encoded: user?.password_hash ?? (await getDummyHash(argon2, config.password)),
  password,
  pepper: storedPepper,
});
if (!user || !isValid) {
  return context.json({ error: 'invalid_credentials' }, 401);
}

// Lazy upgrade: only the login that proves ownership rewrites the hash.
if (user.pepper_version !== config.password.version) {
  const rehashed = await hashPassword(argon2, config.password, password);
  await updatePasswordAndPepper(context.env.DB, user.id, rehashed, config.password.version);
}
```

Note the rehash **does not** bump `session_version`: the user just proved the password, so existing sessions stay valid. Bump it only when a password is *changed*.

`db/users.ts` gains:

```ts
export const updatePasswordAndPepper = async (
  database: D1Database,
  id: string,
  passwordHash: string,
  pepperVersion: number,
): Promise<void> => {
  await database
    .prepare(
      `UPDATE users
       SET password_hash = ?2, pepper_version = ?3, updated_at = unixepoch()
       WHERE id = ?1`,
    )
    .bind(id, passwordHash, pepperVersion)
    .run();
};
```

### 6.4 Rollout order (order matters)

1. Deploy the schema (`pepper_version`, default `1`). Nothing changes behaviour yet.
2. Deploy code that *reads* `pepper_version` and `PASSWORD_PEPPERS`, with `PEPPER_VERSION=1` and v1 as the current pepper. Verify logins still work.
3. Generate pepper v2. Add it to `PASSWORD_PEPPERS` (keeping v1) and set `PEPPER_VERSION=2`, `PASSWORD_PEPPER=<v2>`. Deploy. **New** hashes are v2; **old** users still verify with v1 and are upgraded on their next successful login.
4. Watch the migration drain:

```sql
SELECT pepper_version, COUNT(*) FROM users GROUP BY pepper_version;
```

5. Once `pepper_version = 2` covers every account you care about (or after an agreed window), remove v1 from `PASSWORD_PEPPERS`. Any user who has not logged in since step 3 now needs a password reset — decide that window before you start.

### 6.5 Rollback

Every step is additive. Before step 3 the old code path still works; after step 3 you can roll back either by restoring the previous deployment *and* putting v1 back into `PASSWORD_PEPPER` (v2 hashes then become unverifiable until you roll forward again) or simply by keeping both peppers configured. Keep both versions configured for the whole window — that removes the need for a hard rollback.

### 6.6 If the pepper already leaked or was lost

With no versioned peppers, a lost or exposed pepper is unrecoverable by design. You have two honest options:

- **Force a reset:** add a `password_reset_required` flag, let users set a new password through a reset flow, and mark the column migrated.
- **Migrate from Supabase:** you cannot. Supabase stores bcrypt hashes that this Worker does not verify, and even re-hashing them would require the plaintext. On cutover, existing Supabase users must register again (or you keep GoTrue alongside and import users with a forced reset).

---

## 7. Rotating the JWT signing key

Unlike the pepper, this is cheap: verification uses `kid`.

1. Generate a new pair, e.g. `bun run keys:dev --force` into a scratch file.
2. Publish **both** public keys in `JWT_PUBLIC_JWKS`, keeping the old `kid` present.
3. Switch `JWT_PRIVATE_JWK` (and the matching `kid`) to the new key and deploy.
4. Wait longer than the access-token TTL (12 h) so outstanding tokens expire.
5. Drop the old public key from `JWT_PUBLIC_JWKS`.
