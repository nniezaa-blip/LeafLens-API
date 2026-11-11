# LeafLens — Cloudflare Workers, D1 & Authentication

**Full architecture, migration plan and free-tier strategy**

| | |
|---|---|
| **Project** | LeafLens — AI-Powered Plant Health Monitoring |
| **Context** | Final Year Project, Bachelor of Computer Science, IIUM |
| **Repositories** | `leaflens` (Flutter) + `leaflens-api` (FastAPI) |
| **Date** | 2 November 2026 |
| **Version** | 1.0 |

> This document assumes the project is a final year project with no production users. There is no requirement to migrate existing Supabase accounts or password hashes. A fresh auth database is acceptable.

---

## Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Audit](#2-current-state-audit)
3. [Concepts and Terminology](#3-concepts-and-terminology)
4. [Target Architecture](#4-target-architecture)
5. [Authentication Design](#5-authentication-design)
6. [Keeping the Python API Lightweight](#6-keeping-the-python-api-lightweight)
7. [WebSocket: Is It Possible?](#7-websocket-is-it-possible)
8. [Full Workers Migration](#8-full-workers-migration)
9. [Free-Tier Strategy](#9-free-tier-strategy)
10. [CI/CD and Deployment](#10-cicd-and-deployment)
11. [Flutter Changes](#11-flutter-changes)
12. [Security Checklist](#12-security-checklist)
13. [Risks and Mitigations](#13-risks-and-mitigations)
14. [Decision Matrix and Recommendations](#14-decision-matrix-and-recommendations)
15. [Appendices](#15-appendices)

---

## 1. Executive Summary

LeafLens currently has two repositories:

- **`leaflens` (Flutter)** — uses `supabase_flutter` for login/signup. The app does not query Supabase tables; Supabase is only the identity provider.
- **`leaflens-api` (FastAPI)** — does not handle passwords. It verifies a Supabase JWT, proxies ThingsBoard REST calls, and stores one table, `user_devices`, in Supabase Postgres.

The migration is **not a database swap**. It is an **auth provider replacement**. Supabase Auth currently does five jobs:

1. Stores users.
2. Hashes passwords.
3. Issues JWTs.
4. Refreshes sessions.
5. Provides email flows.

D1 only stores data. If Supabase is removed, the other jobs must be implemented somewhere.

### 1.1 Recommended split

The recommended full-Workers architecture is asymmetric:

```text
Flutter
  ├── /auth/*  → leaflens-auth Worker (Hono/TypeScript, D1)
  │                 - email/password + Google
  │                 - Argon2id
  │                 - JWT + refresh tokens
  │                 - JWKS
  │
  └── /api/*   → leaflens-api Worker (Python/FastAPI, D1)
                    - devices / telemetry / RPC / health
                    - thin request path
                    - pyfetch → ThingsBoard REST
```

- **Auth Worker:** Hono/TypeScript. Lean cold start, Argon2 WASM, JOSE for Google ID tokens and own JWTs.
- **API Worker:** Python/FastAPI. Keeps the existing business logic, but must stay lightweight per request: D1 binding, `pyfetch`, no SQLAlchemy, no global connections, no password hashing.
- **D1:** one database for the FYP (`users`, `refresh_tokens`, `user_devices`).
- **ThingsBoard:** stays external on the existing VPS/Docker. Workers cannot run ThingsBoard or its MQTT broker.
- **Flutter:** remains a mobile client; only the API/auth services move.

### 1.2 Key findings from the repositories

- **Auth-only scope.** The Flutter app only calls Supabase Auth; there are no Supabase table queries.
- **One relational table.** The only Postgres model is `user_devices`. Porting it to D1 is small.
- **No user migration.** Fresh accounts are acceptable. No bcrypt import, no dual verification, no UUID preservation.
- **WebSocket is not wired.** `app/clients/tb_ws.py` is never imported. `app/routers/ws.py` only echoes `subscribed` and `pong`.
- **Flutter WS mismatch.** Flutter sends an `auth` message; the backend expects a query token. The example path is `/ws` while the route is `/api/v1/ws`.
- **Dashboard is hardcoded.** `dashboard_screen.dart` contains a TODO to wire real telemetry.
- **No CI workflows.** Neither repository has `.github/workflows` yet.

### 1.3 The constraint that matters

The free-tier question is not about D1 or Workers requests. It is about **password hashing CPU time**.

- Workers Free: **10 ms CPU per request**.
- Argon2id at 19 MiB / t=2: **borderline**, roughly 8–20 ms depending on the isolate.
- Bcrypt: **not faster**; usually slower at equivalent security.
- Test **deployed**, not `wrangler dev` / `pywrangler dev` (local dev does not enforce the CPU limit).
- If Argon2 fits, keep it. If it does not, use OTP/OAuth, keep Supabase Auth, or pay $5 for Workers Paid. Do not weaken the hash.

---

## 2. Current State Audit

### 2.1 Repository summary

| Repository | Stack | Auth role | Database | Deploy |
|---|---|---|---|---|
| `leaflens` | Flutter 3.x, Riverpod, GoRouter, Hive, Firebase Messaging | `supabase_flutter` (email/password) | Supabase Auth only | Local / mobile build |
| `leaflens-api` | FastAPI, SQLAlchemy async, asyncpg, Alembic, httpx, PyJWT | Verifies Supabase JWT | Supabase Postgres (`user_devices`) | Docker / VPS |

### 2.2 Flutter auth surface

| File | Role |
|---|---|
| `lib/features/auth/data/leaf_lens_auth.dart` | Wraps Supabase; exposes signIn, signUp, signOut, accessToken, onAuthChange. |
| `lib/features/auth/data/auth_repository.dart` | Maps Supabase `AuthException` codes to user-facing messages. |
| `lib/features/dashboard/data/dashboard_providers.dart` | `authStateProvider` watches Supabase auth state and syncs `ApiClient.token`. |
| `lib/core/router/auth_guard.dart` | Uses `isLoggedIn` or `LeafLensAuth.accessToken` for redirects. |
| `lib/core/config/app_config.dart` | `SUPABASE_URL` and `SUPABASE_ANON_KEY` from `dart-define`. |
| `lib/core/init/leaf_lens_auth_init.dart` | Calls `Supabase.initialize` once at startup. |

There is no Supabase table query (no `.from(...)`) in the app. The dashboard is still hardcoded and has a TODO to wire telemetry.

### 2.3 FastAPI surface

| File | Role |
|---|---|
| `app/auth/jwks.py` | Fetches Supabase JWKS and verifies HS256 token with audience `authenticated`. |
| `app/auth/dependencies.py` | FastAPI dependency that extracts the Bearer token. |
| `app/clients/thingsboard.py` | `httpx` client for ThingsBoard REST: telemetry, RPC, devices. |
| `app/routers/devices.py` | SQLAlchemy queries on `user_devices`; ThingsBoard device creation. |
| `app/routers/telemetry.py` | Latest and historical telemetry through ThingsBoard. |
| `app/routers/rpc.py` | One-way and two-way RPC relay. |
| `app/routers/health.py` | Growth Health Score computation from telemetry. |
| `app/routers/ws.py` | Inbound WebSocket echo only; expects `?token=`, sends `subscribed`/`pong`. |
| `app/clients/tb_ws.py` | Unused ThingsBoard WebSocket client; dead code. |
| `app/config.py` | `pydantic-settings` singleton; `sys.exit` on missing env. |

### 2.4 Findings that reduce the migration scope

- **No real-time dependency yet.** The dashboard is hardcoded; the WS relay does not deliver telemetry. The first Workers release can drop WS and use REST polling.
- **No data migration.** FYP accounts can be recreated. No bcrypt import, no legacy password verification.
- **One relational table.** D1 can hold `users`, `refresh_tokens` and `user_devices` without a complex schema port.
- **Two deployment targets, not one.** Flutter is a client; only the API/auth services move to Workers.

> **Important correction:** Cloudflare does not have a product called R1. The SQLite database is **D1**. R2 is object storage.

### 2.5 Planning implications

| Finding | Implication |
|---|---|
| No user migration | Start with a fresh D1 auth database. No bcrypt import, no dual verification, no UUID preservation. |
| No legacy hash | Use Argon2id for all new passwords. Bcrypt is only relevant if old hashes are imported, which is out of scope. |
| No real-time UI dependency | Drop WebSocket for the first release; wire the dashboard with REST polling. |
| One relational table | Port `user_devices` to D1 with raw SQL; the migration is small and testable. |
| Two deployment targets | Flutter remains a client; only Auth and API move to Workers. |

---

## 3. Concepts and Terminology

### 3.1 Cloudflare products

| Product | What it is | Free-tier note |
|---|---|---|
| **Workers** | Runs server code at the edge. Replaces the FastAPI host, not ThingsBoard. | 100k requests/day; 10 ms CPU. Paid: 30 s default CPU. |
| **D1** | SQLite database managed by Cloudflare. Good for auth and small relational data. | 5M row reads/day, 100k writes/day, 5 GB total. |
| **R2** | Object storage for files and images. Not a database. | 10 GB storage; no egress fees. |
| **KV** | Key-value store for configuration and small cached values. | Eventually consistent; not for auth writes. |
| **Durable Objects** | Stateful objects with WebSocket support and alarms. | SQLite-backed DOs are available on Free with daily limits. |
| **Hyperdrive** | Connection pooling and caching for external Postgres/MySQL. | Lets Python Workers use `asyncpg` against Postgres. |
| **Workers Builds** | Cloudflare's GitHub integration: push to deploy. | Build command + deploy command in the dashboard. |
| **Static Assets / Pages** | Hosts the Flutter web build (HTML/JS/CSS). | Not used for the mobile app. |

### 3.2 CI vs CD vs Workers Builds

- **CI (Continuous Integration)** checks the code: lint, type-check, test, build. It should run on every push and pull request.
- **CD (Continuous Deployment)** publishes the code after checks pass.
- **Cloudflare Workers Builds** connects a GitHub repository to a Worker and deploys on push to the configured branch.

The reference repository `sillyusachi` has a `ci.yml` that only runs format, lint, check and test. It has no deploy step. That strongly suggests deployment is handled by Workers Builds (GitHub integration), not by GitHub Actions.

### 3.3 Python Workers in 2026

Python Workers reached general availability in September 2026. FastAPI runs through an ASGI adapter:

```python
from fastapi import FastAPI
from workers import asgi

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

Default = asgi.entrypoint(app)
```

The runtime is Pyodide-based. Pure Python packages and packages with Pyodide wheels work. Native extensions that are not packaged for Pyodide do not.

Important consequences:

- **FastAPI, Pydantic, PyJWT, `argon2-cffi`, bcrypt and cryptography** have Pyodide wheels and can work.
- **`uvicorn`, Docker and Alembic at runtime** are not used.
- **`asyncpg`** can work through Hyperdrive, because Workers now expose TCP sockets and Cloudflare documents `asyncpg` with Hyperdrive.
- **`websockets`** (the TCP library) is not appropriate; use the Workers WebSocket API or a Durable Object.
- **`httpx`** may work, but `pyodide.http.pyfetch` is the predictable choice for outbound HTTP.

### 3.4 Free-tier limits that matter

| Resource | Free allowance | Assessment for LeafLens |
|---|---|---|
| Workers requests | 100,000 / day | Enough for an FYP demo. |
| Workers CPU | 10 ms / request | The hard constraint for password hashing. |
| D1 rows read | 5 million / day | Auth and device queries are tiny. |
| D1 rows written | 100,000 / day | Registration/login writes are tiny. |
| D1 storage | 5 GB total | Auth data is megabytes. |
| Durable Objects | 100k requests/day, 5 GB SQL storage | Optional; only needed for real-time. |
| Workers Builds | Free build minutes / GitHub integration | Check current dashboard limits. |

---

## 4. Target Architecture

There are two viable target shapes. Both keep ThingsBoard and the ESP32 outside Cloudflare. The difference is whether auth and business API live in one Worker or two.

### 4.1 Current architecture

```text
                         ┌──────────────────┐
                         │  Supabase Auth   │
                         └────────┬─────────┘
                                  │ login / JWT
┌─────────┐    REST + JWT        │
│ Flutter │──────────────────────┼──────────────┐
└─────────┘                      │              │
      │                          ▼              ▼
      │                  ┌──────────────┐  ┌──────────────────┐
      └─────────────────▶│ leaflens-api │─▶│   ThingsBoard    │
                         │   FastAPI    │  │   REST / MQTT    │
                         └──────┬───────┘  └──────────────────┘
                                │
                                ▼
                         ┌──────────────────┐
                         │ Supabase Postgres│
                         │  user_devices    │
                         └──────────────────┘
```

### 4.2 Option A — one Worker

A single Python Worker contains `/auth/*` and `/api/v1/*`, with one D1 database. This is the smallest number of moving parts: one deploy, one URL, one set of secrets, one CI/CD pipeline.

| Aspect | Assessment |
|---|---|
| Advantages | Fewer deploys; one URL; simpler local development; less configuration drift. |
| Disadvantages | Auth and telemetry share CPU/memory limits; a bug in one area can affect the other; harder to reason about security boundaries. |
| Best for | A short FYP where speed of delivery matters more than service separation. |

### 4.3 Option B — split Auth and API Workers (recommended)

Two Workers, both deployed from the same repository or from two repositories. The recommended split is deliberately asymmetric:

- **Auth Worker in Hono/TypeScript** for a lean cold start and Argon2 WASM.
- **API Worker in Python/FastAPI** for the existing business logic, kept lightweight per request.

```text
┌─────────┐
│ Flutter │
└────┬────┘
     │
     │ 1. login (email/password or Google)
     ▼
┌─────────────────────┐        ┌──────────────────┐
│  leaflens-auth      │───────▶│        D1        │
│  Hono + Argon2      │        │ users, refresh,  │
│  issues JWT         │        │ user_devices     │
└─────────┬───────────┘        └──────────────────┘
          │ 2. access token
          ▼
┌─────────────────────┐        ┌──────────────────┐
│  leaflens-api       │───────▶│   ThingsBoard    │
│  Python/FastAPI     │        │   REST           │
│  verifies JWT       │        └──────────────────┘
└─────────────────────┘
```

| Component | Responsibility | Data | Secrets / config |
|---|---|---|---|
| Auth Worker | Register, login, Google login, refresh, logout, me, JWKS. | D1: `users`, `refresh_tokens`. | Argon2, JWT private key, pepper. |
| API Worker | Devices, telemetry, RPC, health score, readiness. | D1: `user_devices`. | JWT public keys, ThingsBoard API key. |
| D1 | One database for the FYP (can split later). | `users`, `refresh_tokens`, `user_devices`. | Bound to both Workers. |
| ThingsBoard | External IoT platform. | Its own database. | Stays on VPS/Docker. |
| Flutter | Mobile client. | Secure storage for tokens. | Calls both Workers over HTTPS. |

### 4.4 Why split auth from the API

- Auth has a different threat model and CPU profile from telemetry. Isolating it makes both easier to reason about.
- The auth Worker can be written in Hono/TypeScript for lower cold-start and CPU overhead, while the API remains Python/FastAPI.
- A bug or CPU spike in telemetry cannot take down login.
- The JWT boundary is explicit: the API only needs the public key, never the password pepper or private signing key.
- This matches the stated preference for separation: one service, one responsibility.

### 4.5 Request and token flow

1. Flutter sends email/password to `POST /auth/login` on the Auth Worker.
2. The Auth Worker reads the user from D1, verifies Argon2id, and signs a short-lived access token (for example 15 minutes) plus a refresh token (for example 30 days).
3. Flutter stores the tokens in secure storage and sends `Authorization: Bearer <access>` to the API Worker.
4. The API Worker verifies the JWT signature with the Auth Worker's public JWKS, checks issuer and audience, and extracts `sub` (user id).
5. The API Worker queries D1 for device mappings and calls ThingsBoard REST with its own API key.
6. When the access token expires, Flutter calls `POST /auth/refresh` and retries the request once.

### 4.6 One URL or two?

Two URLs are simpler: `AUTH_URL` and `API_URL`. If a single origin is required, add a gateway Worker that routes `/auth/*` to the Auth Worker via a service binding and everything else to the API Worker. This is optional; it adds a hop and more configuration. For an FYP, two URLs are acceptable.

### 4.7 What stays outside Cloudflare

**ThingsBoard is not moving.** ThingsBoard is a Java IoT platform with MQTT, a rule engine and its own database. It cannot run on Workers. Keep it on the existing VPS/Docker host. The ESP32 continues to publish MQTT to ThingsBoard. Workers only replaces the FastAPI gateway between Flutter and ThingsBoard.

Similarly, the Flutter mobile app is not deployed to Workers. Only the Flutter **web** build, if used, can be hosted as static assets. The mobile app is distributed through the Play Store or App Store.

---

## 5. Authentication Design

This section defines the auth service independently of the hosting choice. It applies whether the service is a Python Worker, a Hono Worker, or a traditional FastAPI host.

### 5.1 What Supabase does today

| Job | Supabase | Self-hosted equivalent |
|---|---|---|
| User storage | `auth.users` table | D1 `users` table |
| Password hashing | bcrypt (new users) | Argon2id (recommended) or bcrypt for legacy |
| Login/signup API | GoTrue endpoints | Your `/auth/*` endpoints |
| JWT issuance | Supabase signing keys | Your RS256 key pair |
| Refresh tokens | Supabase session | `refresh_tokens` table, rotation |
| Email confirmation | Supabase email | Optional; needs an email provider |
| Password reset | Supabase email | Optional; needs an email provider |
| Rate limiting | Supabase | Cloudflare binding or D1 attempts table |

### 5.2 D1 schema

```sql
CREATE TABLE users (
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

CREATE TABLE refresh_tokens (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at INTEGER NOT NULL,
  revoked_at INTEGER,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_refresh_user ON refresh_tokens(user_id);

CREATE TABLE user_devices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  tb_device_id TEXT NOT NULL UNIQUE,
  device_name TEXT NOT NULL,
  device_type TEXT NOT NULL DEFAULT 'leaflens-env',
  mac_address TEXT UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_user_devices_user ON user_devices(user_id);
```

Notes:

- `password_hash` is nullable so Google-only users can exist.
- `google_sub` stores Google's stable `sub` claim, not the email.
- `CHECK` prevents a user with no authentication method.
- `session_version` can invalidate all tokens after a password change; it is optional for the first version.
- `refresh_tokens.token_hash` stores a SHA-256 hash of the refresh token, never the raw token.

### 5.3 Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Email + password; create user; Argon2id; issue tokens. |
| POST | `/auth/login` | Email + password; verify Argon2id; issue tokens. |
| POST | `/auth/google` | Google ID token; verify; find/create/link; issue tokens. |
| POST | `/auth/link/google` | Bearer token; link Google to the logged-in account. |
| POST | `/auth/set-password` | Bearer token; add a password to a Google-only account. |
| POST | `/auth/refresh` | Refresh token; rotate and issue a new access token. |
| POST | `/auth/logout` | Revoke the refresh token. |
| GET | `/auth/me` | Bearer token; return the current user. |
| GET | `/.well-known/jwks.json` | Public keys for API Workers. |

### 5.4 Password hashing: Argon2id

Recommended parameters:

- **Argon2id**
- **19 MiB** memory
- **t=2**
- **p=1**
- 32-byte hash
- 16-byte salt
- Server-side pepper: `HMAC-SHA256(password, pepper)` before Argon2

The pepper is a Worker secret, not stored in D1.

Additional controls:

- **Dummy hash:** if the email does not exist, verify against a fixed dummy hash so the response time does not reveal registered emails.
- **Rate limit:** 5 attempts per minute per IP+email; return 429 after that.
- **Generic error:** `invalid email or password` for both wrong email and wrong password.
- **Pepper rotation:** changing the pepper invalidates all hashes. Plan a rehash-on-login migration if it ever changes.

On Workers, Argon2 is usually implemented with `@phi-ag/argon2` (WASM) in JavaScript, or `argon2-cffi` in Python. The WASM path is the leanest for the free tier. Compile the WASM once per isolate; do not instantiate it per request.

### 5.5 Argon2 vs bcrypt: the speed question

Bcrypt is not a faster alternative. It is also deliberately slow. At equivalent security, bcrypt is usually slower than Argon2id at 19 MiB, and bcrypt also has a 72-byte password limit and no memory-hardness.

| Algorithm | Setting | Approx. CPU | Free-tier assessment |
|---|---|---|---|
| Argon2id WASM | 19 MiB, t=2, p=1 | ~8–20 ms | Borderline on Free; test deployed. |
| Bcrypt WASM | cost 10 | ~50–150 ms | Usually too slow for Free. |
| Bcrypt JS (`bcryptjs`) | cost 10 | ~150–400 ms | Not suitable for Workers. |
| Bcrypt | cost 8 | ~20–60 ms | Weaker; still risky. |
| PBKDF2 | 600k | ~50–100 ms | Too slow for Free. |
| PBKDF2 | 100k | ~10–20 ms | Borderline and weaker than Argon2. |
| OTP HMAC | 6-digit code | <1 ms | No password hash; rate-limited. |

> **Do not weaken the hash to fit the free tier.** If Argon2 at 19 MiB does not fit, change the authentication method (OTP/OAuth), use an external free auth provider, or pay $5 for Workers Paid. Lowering Argon2 to a few MiB or using plain SHA-256 is not an acceptable security trade-off.

### 5.6 JWT and JWKS

Use RS256 (or EdDSA) with a private key stored as a Worker secret. The Auth Worker exposes the public key at `/.well-known/jwks.json`. The API Worker verifies tokens locally; it does not call the Auth Worker on every request.

| Token | Lifetime | Content | Transport |
|---|---|---|---|
| Access token | 15 minutes | `sub`, `email`, `iss`, `aud`, `iat`, `exp` | Bearer header |
| Refresh token | 30 days | random opaque token; hash in D1 | `POST /auth/refresh` |
| Issuer | `leaflens-auth` | Auth Worker | API verifies |
| Audience | `leaflens-app` | Flutter/API | API verifies |
| Signing | RS256 | private key secret | public JWKS |

Recommended claims: `sub` (user id), `email`, `iss`, `aud`, `iat`, `exp`. Do not put roles or secrets in the token unless needed. The API must not trust a client-supplied user id; it must use `sub` from the verified token.

### 5.7 Refresh token rotation

1. Login returns an access token and a random refresh token.
2. The refresh token is stored as a SHA-256 hash in D1, with user id, expiry and `revoked_at`.
3. On refresh, the server looks up the hash, checks expiry and revocation, marks the old token revoked, and issues a new refresh token.
4. If a revoked token is reused, revoke the whole token family for that user (reuse detection).
5. Logout revokes the current refresh token.

### 5.8 Email/password + Google

Both login methods can coexist. One user row can have a password hash, a Google subject, or both. The same user id is used for device mappings, so switching login method does not orphan devices.

#### Google login flow

1. Flutter uses `google_sign_in` to obtain a Google **ID token**.
2. Flutter sends the ID token to `POST /auth/google`.
3. The Auth Worker verifies the token with Google's JWKS, checking issuer, audience, expiry and `email_verified`.
4. The Worker looks up `google_sub`; if found, log in.
5. If not found, it looks up the email. If no user exists, create a Google-only user.
6. If a password account already exists for that email, return `409 link_required` instead of auto-linking.
7. The client logs in with the password, then calls `POST /auth/link/google` with the Google ID token.

#### Account linking rules

| Situation | Action | Reason |
|---|---|---|
| Google sub exists | Log in | Same Google account. |
| Email exists, no user | Create Google-only user | `email_verified = 1`. |
| Email exists, password account | `409 link_required` | Prevents account takeover. |
| Email exists, different Google sub | `409 conflict` | Do not merge automatically. |
| Password signup, email is Google-only | `409 use_google_then_set_password` | User logs in with Google, then sets a password. |
| Password signup, email exists | `409 email_exists` | No duplicate accounts. |

> **Do not auto-link by email.** If password signup does not verify email ownership, auto-linking a Google login by email lets an attacker who registered the victim's email attach the victim's Google identity to the attacker's password account. Require a password login before linking, or verify email ownership first.

### 5.9 Email verification and password reset

Supabase provides these for free. A self-hosted auth service does not. For the FYP, they can be deferred, but the limitation should be documented: without email verification, anyone can register with an email they do not own.

If these flows are required, use a free transactional email provider (Resend, Brevo) and add:

- `POST /auth/verify-email` with a single-use token.
- `POST /auth/forgot-password` and `POST /auth/reset-password`.
- Rate limits and short expiry (15–30 minutes).

---

## 6. Keeping the Python API Lightweight

The API Worker should be a thin gateway, not a full application server. The goal is to keep each request cheap:

1. Verify the JWT.
2. Read D1.
3. Call ThingsBoard with `pyfetch`.
4. Return JSON.

Password hashing, email and Google token exchange belong to the Auth Worker, not here.

### 6.1 Heavy patterns to remove

| Heavy pattern | Lightweight replacement |
|---|---|
| SQLAlchemy + asyncpg + Alembic | D1 binding + raw SQL (or Hyperdrive + asyncpg only if keeping Postgres). |
| `httpx.AsyncClient` with a global pool | `pyodide.http.pyfetch` per call; no global socket pool. |
| `pydantic-settings` + `.env` + singleton | `request.scope['env']` + a small request-scoped `Settings` object. |
| `BaseHTTPMiddleware` for everything | No middleware, or a pure ASGI middleware only where necessary. |
| `sentry_sdk` | Workers Logs / observability; keep Sentry in Flutter. |
| `uvicorn`, Docker, reload | Workers runtime; `pywrangler dev` locally. |
| In-memory rate limiter | Cloudflare rate-limit binding or a D1 attempts table. |
| `response_model` on every route | Plain dict responses on hot paths; Pydantic only where it earns its CPU. |
| All routers imported eagerly | Keep the API app small; split Workers if a domain grows. |
| Large dependency set | Minimal `pyproject`: `fastapi`, `pyjwt[crypto]`, `pydantic` only if needed. |

### 6.2 A healthy request path

```text
1. ASGI adapter receives the request.
2. JWT verified against a module-level cached JWKS (public keys only).
3. Handler reads request.scope["env"].DB and runs one or two indexed D1 queries.
4. Handler calls ThingsBoard with pyfetch; the wait is I/O, not CPU.
5. Handler returns a plain JSON-serialisable dict.
```

Rules of thumb:

- No connection is opened at import time.
- No mutable global holds user data.
- No Argon2, email or Google exchange in this Worker.
- No large framework added to save a few lines.
- If a route still exceeds the CPU budget, move that route to Hono or split it into its own Worker rather than adding more middleware.

> **Mental model:** the Auth Worker is a small security service. The Python API Worker is a stateless translator between Flutter, D1 and ThingsBoard. Keeping those roles separate is what makes the free tier and the CPU budget manageable.

---

## 7. WebSocket: Is It Possible?

**Yes.** WebSocket is possible on Workers, including Python Workers. The real question is where the WebSocket state lives and where the telemetry comes from.

### 7.1 Four levels

| Level | Where the socket lives | Telemetry source | Best for |
|---|---|---|---|
| 1. Drop WebSocket | None | Flutter polls REST every 5–10s. | First Workers release; FYP demo. |
| 2. FastAPI WS in API Worker | Python API Worker | Client messages only, or poll TB inside the handler. | Simple ack/ping; a few clients. |
| 3. Durable Object | API Worker routes to DO | DO alarm polls TB REST and broadcasts. | Real-time dashboard; recommended if needed. |
| 4. DO + ThingsBoard WS | DO holds outbound TB WS | TB subscription protocol. | Advanced; more work and more failure modes. |

The current repository is at level 0:

- `tb_ws.py` is never imported.
- `/ws` only echoes `subscribed` and `pong`.
- Flutter sends a first `auth` message, which the backend does not read.
- The example path is `/ws` while the route is `/api/v1/ws`.
- The dashboard is still hardcoded, so no UI depends on the socket yet.

### 7.2 Level 1 — drop it (recommended first)

Wire the dashboard to REST polling:

```text
Every 5–10 seconds:
GET /api/v1/telemetry/{device_id}/latest
Authorization: Bearer <access_token>
```

This removes the socket, the Durable Object and the reconnect complexity from the first release.

### 7.3 Level 2 — FastAPI WebSocket inside the Python API Worker

The Python Workers ASGI adapter supports the WebSocket scope. A normal FastAPI route works:

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.auth.jwks import verify_access_token

router = APIRouter()

@router.websocket("/api/v1/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()

    first = await websocket.receive_json()
    if first.get("type") != "auth":
        await websocket.close(code=4001)
        return

    try:
        user = verify_access_token(first["token"])
    except Exception:
        await websocket.close(code=4003)
        return

    await websocket.send_json({"type": "auth_ok"})

    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg.get("type") == "subscribe":
                await websocket.send_json({
                    "type": "subscribed",
                    "device_id": msg["device_id"],
                })
    except WebSocketDisconnect:
        pass
```

This gives a working client-facing socket, but it does not create telemetry. If the handler also polls ThingsBoard, each connected client polls separately. That is acceptable for a demo with a handful of devices, but it is not a scalable fan-out design. It also relies on the Worker isolate staying alive for the duration of the connection; the runtime can evict it, so Flutter's reconnect logic still matters.

### 7.4 Level 3 — Durable Object (recommended for real-time)

A Durable Object is the right home for a long-lived socket and shared telemetry state.

```text
Flutter
  -> GET /api/v1/ws?device_id=...   (Upgrade: websocket)
  -> API Worker verifies JWT
  -> env.DEVICE_ROOM.getByName(device_id)
  -> DeviceRoom Durable Object accepts the socket
  -> DO alarm every 5s: pyfetch ThingsBoard latest telemetry
  -> DO broadcasts one JSON message to all sockets in the room
```

The DO replaces the current echo handler. It can be Python (supported) or TypeScript. A Python DO keeps the API Worker in one language; a TypeScript DO is a good fit if the Auth Worker is already Hono/TS. Either way, the API Worker verifies the JWT before forwarding the request to the DO; the DO is never exposed directly to Flutter.

```python
from workers import DurableObject, Response
from js import WebSocketPair

class DeviceRoom(DurableObject):
    def __init__(self, state, env):
        super().__init__(state, env)
        self.ctx = state

    async def fetch(self, request):
        client, server = WebSocketPair.new().object_values()
        self.ctx.acceptWebSocket(server)
        # Start the telemetry alarm on first connection.
        self.ctx.storage.setAlarm(__import__("js").Date.now() + 1000)
        return Response(None, status=101, web_socket=client)

    async def webSocketMessage(self, ws, message):
        # Optional client commands (ping, subscribe).
        ws.send(message)

    async def alarm(self):
        # TODO: pyfetch ThingsBoard latest telemetry for this device,
        # then broadcast to self.ctx.get_web_sockets().
        self.ctx.storage.setAlarm(__import__("js").Date.now() + 5000)
```

```jsonc
"durable_objects": {
  "bindings": [{ "name": "DEVICE_ROOM", "class_name": "DeviceRoom" }]
},
"migrations": [
  { "tag": "v1", "new_sqlite_classes": ["DeviceRoom"] }
]
```

For the telemetry source, polling ThingsBoard REST from the DO alarm is the simplest reliable option. The Python `websockets` library is not suitable because it expects raw TCP; a DO can use the Workers WebSocket/fetch APIs instead, but then you must implement ThingsBoard's auth and subscription protocol. That is level 4 and should be attempted only if the thesis requires it.

### 7.5 WebSocket authentication rules

- Do not put the access token in the query string; it leaks into logs and browser history.
- Use the first message (`{"type":"auth","token":...}`) or an Authorization header.
- Verify the JWT before subscribing to a device room.
- Check that the device belongs to the authenticated user before forwarding to the DO.
- Send a short-lived access token; do not use the refresh token for WebSocket auth.
- Keep Flutter's reconnect with backoff; Workers can evict an isolate.

### 7.6 Recommendation

> **For the FYP:** ship level 1 first — drop the socket and poll REST. The dashboard is still hardcoded, so there is no real-time feature to preserve. If real-time is explicitly required by the thesis, implement level 3 with one Durable Object per device and alarm-based ThingsBoard REST polling. Do not spend time on level 4 unless the requirements demand a direct ThingsBoard WebSocket.

---

## 8. Full Workers Migration

This section is the concrete migration guide. The target is two Workers: a Hono Auth Worker and a lightweight Python API Worker, both with D1. ThingsBoard stays external.

### 8.1 What moves and what stays

| Component | Action | Notes |
|---|---|---|
| Flutter mobile app | Stays a client | No Cloudflare deploy; point to Worker URLs. |
| Supabase Auth | Replaced or kept | Own auth Worker + D1, or keep Supabase free. |
| FastAPI API | Moves to a Python Worker | FastAPI + `workers.asgi`. |
| Postgres `user_devices` | Moves to D1 | One table; raw SQL. |
| ThingsBoard | Stays external | REST API; MQTT broker remains on VPS. |
| WebSocket relay | Drop initially | Dashboard is hardcoded; add DO later if needed. |
| Docker / uvicorn | Removed for production | Workers runtime replaces the container. |
| Sentry | Drop or replace | Use Workers Logs/observability. |

### 8.2 Worker entrypoint

```python
# src/worker.py
from workers import asgi
from app.main import app

Default = asgi.entrypoint(app)
```

The entrypoint imports the FastAPI app. That means every module imported by `app.main` must be import-safe in the Workers runtime:

- No database connection at import time.
- No `sys.exit`.
- No reading of a local `.env` file.

### 8.3 Wrangler configuration

API Worker:

```jsonc
{
  "name": "leaflens-api",
  "main": "src/worker.py",
  "compatibility_date": "2026-11-02",
  "compatibility_flags": ["python_workers"],
  "observability": { "enabled": true },

  "d1_databases": [
    { "binding": "DB", "database_name": "leaflens", "database_id": "<id>" }
  ],

  "vars": {
    "TB_URL": "https://tb.example.com",
    "JWT_ISSUER": "leaflens-auth",
    "JWT_AUDIENCE": "leaflens-app"
  },

  "secrets": {
    "required": ["TB_API_KEY", "JWT_PUBLIC_JWKS"]
  }
}
```

Auth Worker:

```jsonc
{
  "name": "leaflens-auth",
  "main": "src/index.ts",
  "compatibility_date": "2026-11-02",
  "observability": { "enabled": true },

  "d1_databases": [
    { "binding": "DB", "database_name": "leaflens", "database_id": "<id>" }
  ],

  "vars": {
    "JWT_ISSUER": "leaflens-auth",
    "JWT_AUDIENCE": "leaflens-app",
    "GOOGLE_CLIENT_IDS": "web-client-id,android-client-id,ios-client-id"
  },

  "secrets": {
    "required": ["JWT_PRIVATE_KEY", "JWT_PUBLIC_JWKS", "PASSWORD_PEPPER"]
  }
}
```

### 8.4 D1 migrations

Alembic is not used at runtime. D1 has its own migration system:

```bash
# local
uv run pywrangler d1 migrations apply leaflens --local

# remote
uv run pywrangler d1 migrations apply leaflens --remote
```

Keep migrations in `migrations/0001_init.sql`, `0002_....sql`. Never edit an applied migration; add a new one.

### 8.5 Porting the database layer

Remove the SQLAlchemy engine and `asyncpg` connection from the request path. Replace it with D1 queries.

| File | Change |
|---|---|
| `app/db/engine.py` | Delete. Replace with a D1 helper that reads `request.scope['env'].DB`. |
| `app/db/models.py` | Delete or convert to Pydantic/dataclass row models. Schema lives in migrations. |
| `app/routers/devices.py` | Replace SQLAlchemy select/insert with D1 prepare/bind/all/run. |
| `app/main.py` | Remove `init_db()`, `engine.dispose()` and the DB readiness query. |
| `alembic/` | Keep in git for reference, but do not run it in Workers. |

```python
from pyodide.ffi import to_py
from fastapi import Request

async def list_user_devices(request: Request, user_id: str):
    db = request.scope["env"].DB
    result = await db.prepare(
        "SELECT * FROM user_devices WHERE user_id = ?"
    ).bind(user_id).all()
    return to_py(result.results)

async def insert_device(request: Request, row: dict):
    db = request.scope["env"].DB
    await db.prepare(
        """
        INSERT INTO user_devices
          (user_id, tb_device_id, device_name, device_type, mac_address)
        VALUES (?, ?, ?, ?, ?)
        """
    ).bind(
        row["user_id"], row["tb_device_id"], row["device_name"],
        row.get("device_type", "sensor"), row.get("mac_address"),
    ).run()
```

If you prefer to keep Postgres instead of D1 for `user_devices`, Python Workers now support Hyperdrive with `asyncpg`. Create a Hyperdrive binding, connect with the provided host/port/user/password, and close the connection per request. This keeps the Postgres schema but adds a second external dependency. For one table, D1 is simpler.

### 8.6 Porting the ThingsBoard client

The current client creates an `httpx.AsyncClient` with a base URL and an `X-Authorization: ApiKey` header. In Workers, use `pyodide.http.pyfetch`. The method signatures can stay the same, so the routers do not need to change.

```python
from pyodide.http import pyfetch

class ThingsBoardClient:
    def __init__(self, env):
        self.base_url = str(env.TB_URL).rstrip("/")
        self.headers = {"X-Authorization": f"ApiKey {env.TB_API_KEY}"}

    async def _get(self, path: str, params: dict | None = None):
        url = self.base_url + path
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        resp = await pyfetch(url, headers=self.headers)
        if not resp.ok:
            raise RuntimeError(f"ThingsBoard error: {resp.status}")
        return await resp.json()

    async def get_latest_telemetry(self, device_id: str, keys: list[str]):
        raw = await self._get(
            f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
            {"keys": ",".join(keys)},
        )
        return {k: float(v[0]["value"]) for k, v in raw.items() if v}
```

Handle ThingsBoard errors explicitly:

- 401: bad API key.
- 404: device missing.
- 504: RPC timeout (preserve the existing queued response).

### 8.7 Config and environment

The current `app/config.py` uses `pydantic-settings`, a singleton and `sys.exit(1)` for missing variables. In Workers, environment variables are request-scoped bindings, not process environment variables. Refactor to a dependency:

```python
from dataclasses import dataclass
from fastapi import Request

@dataclass(frozen=True)
class Settings:
    tb_url: str
    tb_api_key: str
    jwt_issuer: str
    jwt_audience: str
    jwt_public_jwks: str

def get_settings(request: Request) -> Settings:
    env = request.scope["env"]
    return Settings(
        tb_url=str(env.TB_URL),
        tb_api_key=str(env.TB_API_KEY),
        jwt_issuer=str(env.JWT_ISSUER),
        jwt_audience=str(env.JWT_AUDIENCE),
        jwt_public_jwks=str(env.JWT_PUBLIC_JWKS),
    )
```

- Remove `sys.exit`; return a 500 response or fail the request instead.
- Remove the global `_settings` singleton; it is not safe across requests with different bindings.
- Use `.dev.vars` for local development; never commit it.
- Use `wrangler secret put` or the dashboard for production secrets.

### 8.8 Middleware, logging and Sentry

| Middleware | Action |
|---|---|
| `RequestIDMiddleware` | Keep. Works with the ASGI adapter. |
| `RateLimitMiddleware` | Replace. In-memory dict is per isolate and not reliable. Use a Cloudflare rate-limit binding or a D1 attempts table. |
| `CORSMiddleware` | Keep, but set explicit Flutter web origins. Mobile clients do not send `Origin`. |
| Sentry | Remove `sentry_sdk` from the Worker. Use Workers Logs/observability and keep Sentry in Flutter. |
| Logging | Use structured console logs; Workers Logs captures them. Do not log tokens or passwords. |

### 8.9 WebSocket strategy

See [Section 7](#7-websocket-is-it-possible). Short version:

- Drop WS for the first release and poll REST.
- If real-time is required, use a Durable Object per device.
- Do not use the Python `websockets` library.
- Do not put the access token in the query string.

### 8.10 File-by-file change map

| File | Change |
|---|---|
| `auth-worker/` (new) | Hono/TypeScript Auth Worker: `/auth/*`, Argon2 WASM, JOSE, Google, JWKS, D1. |
| `app/main.py` | Remove lifespan DB init, Sentry, `engine.dispose`; keep routers and CORS. |
| `app/config.py` | Request-scoped settings; remove `sys.exit` and singleton. |
| `app/db/engine.py` | Delete; D1 helper. |
| `app/db/models.py` | Delete or convert to row models; schema in migrations. |
| `app/routers/devices.py` | D1 queries; remove SQLAlchemy. |
| `app/routers/health.py` | D1 `SELECT 1` for readiness; `pyfetch` for ThingsBoard check. |
| `app/routers/telemetry.py` | No logic change; TB client signature unchanged. |
| `app/routers/rpc.py` | No logic change; TB client signature unchanged. |
| `app/clients/thingsboard.py` | `httpx` → `pyfetch`; request-scoped env. |
| `app/auth/jwks.py` | Verify own JWT: RS256, issuer, audience, JWKS. |
| `app/auth/dependencies.py` | Rename to `get_current_user`; same Bearer extraction. |
| `app/routers/ws.py` | Drop or rewrite with DO; fix auth handshake if kept. |
| `app/clients/tb_ws.py` | Delete; unused. |
| `app/middleware.py` | Replace in-memory rate limit; keep request ID. |
| `app/sentry.py` | Remove or no-op. |
| `requirements.txt` | Remove `uvicorn`, `asyncpg`, `sqlalchemy`, `alembic`, `websockets`, `dotenv`, `orjson`; add `pyjwt[crypto]`. |
| `Dockerfile` / `docker-compose.yml` | Not used for Workers; keep for local fallback. |

### 8.11 Migration phases and acceptance criteria

| Phase | Work | Acceptance |
|---|---|---|
| 0. Baseline | Freeze a branch; keep the current API running; record current endpoints and responses. | Old API still green. |
| 1. Worker skeleton | Deploy a hello-world FastAPI Worker; verify `/health`. | `curl` returns 200 from `*.workers.dev`. |
| 2. D1 + devices | Create D1, migrations, port devices list/register; local + remote tests. | Device CRUD works against D1. |
| 3. ThingsBoard | Replace `httpx` with `pyfetch`; test latest/history/RPC; check error mapping. | Telemetry and RPC responses match old API. |
| 4. Auth Worker | Register/login/refresh/logout/JWKS; Argon2; rate limit. | Login works; JWT verifies in API Worker. |
| 5. Flutter | Point `AUTH_URL`/`API_URL`; implement refresh; remove Supabase. | Login, signup, logout, refresh, device list pass. |
| 6. Real-time | Drop WS or add DO; wire dashboard polling. | Dashboard updates; no reconnect storm. |
| 7. CI/CD | GitHub Actions checks; Workers Builds; D1 migrations; secrets; domains. | Push to `main` deploys both Workers. |
| 8. Cleanup | Remove Supabase env/deps; update docs; delete old host. | No Supabase calls; old service retired. |

### 8.12 Testing strategy

- **Unit tests:** GHS computation, auth error mapping, linking rules, token claims.
- **Integration tests:** run `pywrangler dev` with local D1; curl register/login/refresh; call telemetry with a real token.
- **Contract tests:** compare old and new API responses for the same device and time window.
- **Load smoke test:** 20–50 logins to see whether Argon2 triggers a CPU error on the deployed free Worker.
- **Security tests:** expired token, wrong audience, revoked refresh token, wrong password, duplicate email, Google token with wrong audience.

---

## 9. Free-Tier Strategy

The free tier is viable for LeafLens because the app has low traffic and a small dataset. The only real risk is CPU time for password hashing.

### 9.1 What is free

| Service | Free allowance | Assessment |
|---|---|---|
| Workers | 100k requests/day; 10 ms CPU/request | Enough requests; CPU is tight for Argon2. |
| D1 | 5M reads/day; 100k writes/day; 5 GB | Ample for auth and device mappings. |
| Durable Objects | 100k requests/day; 5 GB SQL | Optional for real-time. |
| Google OAuth | Free | No per-login cost. |
| Resend / Brevo | Free email tiers | Only needed for OTP, verification or reset. |
| GitHub Actions | Free minutes for public repos; included for private | Enough for lint/test. |

### 9.2 Argon2 on the free tier: test protocol

Do not trust local development. `wrangler dev` and `pywrangler dev` run on your machine and do not enforce the 10 ms CPU limit. Test the deployed Worker.

1. Deploy the auth Worker with Argon2id at 19 MiB, t=2, p=1.
2. Open Cloudflare Dashboard → Workers & Pages → `leaflens-auth` → Metrics → CPU Time.
3. Send 30 login requests with a valid account. Record p50 and p99 CPU time.
4. Check for HTTP 1102 errors or `Worker exceeded CPU time limit` in logs.
5. Repeat after the Worker has been idle for 10 minutes (cold start).
6. If p99 is below 10 ms and there are no 1102 errors, Argon2 fits this workload. Keep it.
7. If there are intermittent 1102 errors, do not lower the hash parameters. Choose a fallback.

> **What "works on my machine" means:** a successful login in local dev proves the code is correct, not that the free plan accepts the CPU cost. The only valid evidence is a deployed Worker with CPU metrics below the limit.

### 9.3 If Argon2 fits

If the deployed test passes, the full free stack is:

- Auth Worker: Hono/TypeScript + `@phi-ag/argon2` + D1.
- API Worker: Python FastAPI with `workers.asgi`, or Hono/TypeScript if Python CPU is too high.
- D1: one database for users, refresh tokens and `user_devices`.
- ThingsBoard: existing VPS/Docker.
- Flutter: email/password + Google login; tokens in secure storage.
- CI/CD: GitHub Actions for checks + Workers Builds for deploy.

Keep the Argon2 WASM instance cached per isolate, keep the login path minimal, and do not add unrelated work (email sending, analytics) to the login request.

### 9.4 If Argon2 does not fit

| Fallback | What it gives | Trade-off |
|---|---|---|
| Keep Supabase Auth | Free, reliable, least work. | Not own auth; Supabase remains a dependency. |
| Email OTP + D1 | Own auth; no password hash; free email tier. | UI change; email deliverability; rate limits. |
| Google OAuth + D1 | Own auth; no password; free. | Google account required; consent screen setup. |
| Clerk / Auth0 free | Email/password UI; free MAU. | External auth; not own auth. |
| Argon2 on external free compute | Keeps email/password. | Two platforms; cold starts; not full Workers. |
| Workers Paid | Keeps Argon2 + full Workers. | $5/month. |

### 9.5 Email OTP fallback

OTP is the closest free alternative to email/password. It avoids Argon2 entirely and is secure when implemented with short expiry, single use and rate limits.

```sql
CREATE TABLE otp_codes (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  used_at INTEGER,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_otp_email ON otp_codes(email);
```

1. `POST /auth/request-code` with email.
2. Generate a 6-digit code with a cryptographically secure random source.
3. Hash it with HMAC-SHA256 and a server pepper; store the hash, expiry and attempt count.
4. Send the code through Resend/Brevo (free tier).
5. `POST /auth/verify-code` with email + code; constant-time compare; max 5 attempts; single use.
6. Create the user if new; issue the same access + refresh tokens as password login.

### 9.6 Google OAuth fallback

Google OAuth is the lowest-friction free option if users have Google accounts. Flutter obtains a Google ID token, the Worker verifies it and issues its own JWT. No password storage, no email sending, no Argon2. The trade-off is that the login UI becomes "Continue with Google".

### 9.7 Cost summary

| Stack | Monthly cost | Notes |
|---|---|---|
| Cloudflare Workers Free + D1 Free | $0 | If Argon2 fits; otherwise password login is unreliable. |
| Cloudflare Workers Paid + D1 Free | $5/month | Removes the CPU concern; simplest paid option. |
| Supabase Auth Free + Workers Free | $0 | Keeps Supabase Auth; API on Workers. |
| OTP/OAuth + Workers Free | $0 | Own auth; no password hash. |

---

## 10. CI/CD and Deployment

CI and CD are separate concerns. CI checks the code; CD publishes it. For LeafLens, use GitHub Actions for checks and Cloudflare Workers Builds for deployment. If you want everything in one place, use GitHub Actions with `cloudflare/wrangler-action` instead.

### 10.1 GitHub Actions for the Flutter repository

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
        with:
          channel: stable
      - run: flutter pub get
      - run: dart run build_runner build --delete-conflicting-outputs
      - run: flutter analyze
      - run: flutter test
      - run: flutter build web --release
```

The web build is optional. If you only ship the mobile app, remove the last step. The mobile app is not deployed by Workers Builds; it is built as an APK/IPA and distributed separately.

### 10.2 GitHub Actions for the API repository

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -r requirements-dev.txt
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy app
      - run: pytest
```

### 10.3 Workers Builds

For each Worker, connect the repository in the Cloudflare dashboard and set:

| Worker | Root directory | Build command | Deploy command |
|---|---|---|---|
| API Worker | Repository root | `uv sync` | `uv run pywrangler deploy` |
| Auth Worker | Repository root (or `auth-worker/`) | `npm ci` | `npx wrangler deploy` |
| D1 migrations | Same repository | Run once or in deploy | `pywrangler d1 migrations apply leaflens --remote` |

If the build image does not include `uv`, use GitHub Actions with `astral-sh/setup-uv` and run `uv run pywrangler deploy`. Workers Builds is simpler when it works; GitHub Actions is more transparent and easier to debug.

### 10.4 Secrets

| Secret | Used by | Purpose |
|---|---|---|
| `JWT_PRIVATE_KEY` | Auth Worker | RS256 private key (PEM or JWK). Never in git. |
| `JWT_PUBLIC_JWKS` | Auth and API Workers | Public JWKS JSON. |
| `PASSWORD_PEPPER` | Auth Worker | HMAC pepper for password hashing. |
| `GOOGLE_CLIENT_IDS` | Auth Worker | Allowed audiences, comma-separated. |
| `TB_API_KEY` | API Worker | ThingsBoard API key. |
| `RESEND_API_KEY` | Auth Worker (optional) | Only for OTP/verification/reset. |

Set secrets with `uv run pywrangler secret put NAME` or via the dashboard. Use separate values for staging and production. Rotate JWT keys with a `kid` (key id) and publish both keys in JWKS during rotation.

### 10.5 Custom domains and CORS

- Use `auth.example.com` and `api.example.com`; Cloudflare provisions TLS.
- Set `CORS_ORIGINS` to the Flutter web origin only. Mobile apps do not need CORS.
- Do not use wildcard CORS with credentials.
- Set `Cache-Control: no-store` on auth responses.

### 10.6 Monitoring

- Enable Workers observability/logs.
- Track login success rate, 401 rate, 429 rate, and Argon2 CPU time.
- Alert on 1102 errors (CPU limit) and 5xx spikes.
- Keep Sentry in Flutter for client crashes; use Workers Logs for server errors.

---

## 11. Flutter Changes

The Flutter auth surface is already wrapped in `LeafLensAuth`. That is the main reason the migration is contained. Keep the public API stable and replace the internals.

### 11.1 File map

| File | Change |
|---|---|
| `lib/features/auth/data/leaf_lens_auth.dart` | Replace Supabase with HTTP calls; add Google; store tokens. |
| `lib/features/auth/data/auth_repository.dart` | Map own error codes instead of Supabase `AuthException` codes. |
| `lib/features/dashboard/data/dashboard_providers.dart` | Replace Supabase auth stream with own auth stream/notifier. |
| `lib/core/config/app_config.dart` | Replace `SUPABASE_URL`/`ANON_KEY` with `AUTH_URL` and `API_URL`. |
| `lib/core/init/leaf_lens_auth_init.dart` | Initialize own auth service; restore session. |
| `lib/core/router/app_router.dart` | Keep `AuthGuard`; use `accessToken`/auth state. |
| `pubspec.yaml` | Remove `supabase_flutter`; add `google_sign_in` and `flutter_secure_storage`. |
| `.env.example` | `AUTH_URL`, `API_URL`, `WS_URL` (optional), `GOOGLE_CLIENT_ID`. |

### 11.2 Token storage and refresh

Supabase automatically restores and refreshes sessions. A custom auth service must do this explicitly.

1. On login/register/Google, store the access token and refresh token in secure storage.
2. On app start, read the refresh token and call `POST /auth/refresh`.
3. If refresh fails, clear storage and route to login.
4. On API 401, attempt refresh once, then retry the original request.
5. On logout, call `POST /auth/logout` and clear storage.
6. Emit an auth state stream so GoRouter and `AuthGuard` react.

> **Common bug:** if you only store the access token and do not implement refresh, users appear logged out after 15 minutes. This is the most common regression when leaving Supabase.

### 11.3 Google Sign-In

Add `google_sign_in`, configure OAuth client IDs, and send the **ID token** to the Auth Worker. Do not send the Google access token, and do not trust the client email on the server.

| Platform | Google Cloud setup | Note |
|---|---|---|
| Android | OAuth client ID with SHA-1; `serverClientId` = web client ID | ID token audience may be the web client ID. |
| iOS | OAuth client ID with bundle ID; `serverClientId` = web client ID | ID token audience may be the web client ID. |
| Web | OAuth client ID with authorized JavaScript origins | Only if Flutter web is used. |
| Consent screen | Add test users while in Testing mode | Otherwise only test users can sign in. |

### 11.4 UI changes

- Login page: email/password fields + a "Continue with Google" button.
- Signup page: same two options.
- Settings: "Link Google" and "Set password" for accounts that need both methods.
- Show a clear message when a password account tries Google login: "This email already has a password. Log in with your password, then link Google."
- Show a clear message when a Google-only account tries password login: "This account uses Google. Continue with Google, then set a password."

### 11.5 Config changes

```dotenv
# .env.example
AUTH_URL=https://leaflens-auth.example.com
API_URL=https://leaflens-api.example.com
WS_URL=wss://leaflens-api.example.com/api/v1/ws   # optional
GOOGLE_SERVER_CLIENT_ID=xxxx.apps.googleusercontent.com
```

Remove `SUPABASE_URL` and `SUPABASE_ANON_KEY` from build configs and CI. Build with `--dart-define-from-file=.env` locally and CI secrets in CI.

---

## 12. Security Checklist

### 12.1 Authentication

- Passwords hashed with Argon2id at the agreed parameters; never plain text or SHA-256 alone.
- Per-user salt; server-side pepper stored as a secret.
- Dummy hash verification for non-existent emails.
- Generic `invalid email or password` errors.
- Login and register rate-limited (per IP and per email).
- Password minimum length and a breached-password check (optional).
- Email normalization: trim and lowercase; D1 unique index with `NOCASE`.

### 12.2 Tokens

- Access token short-lived (15 minutes).
- Refresh token random, hashed in D1, rotated on use, revoked on logout.
- JWT signature verified with the correct algorithm; reject `none`.
- Issuer and audience checked.
- Private key only in the Auth Worker; API Worker has only public keys.
- No tokens in logs, URLs or crash reports.

### 12.3 Google OAuth

- Verify Google ID token server-side.
- Check issuer, audience, expiry and `email_verified`.
- Use Google `sub` as the stable identifier.
- Do not auto-link by email unless email ownership is verified.
- Require a password login before linking Google to an existing password account.

### 12.4 Data and infrastructure

- D1 queries always use bind parameters; never string-concatenate user input.
- CORS restricted to the Flutter web origin; no wildcard with credentials.
- Secrets in Worker secrets or GitHub secrets, never in git.
- Rate-limit and monitor 401/429/5xx.
- D1 Time Travel enabled for recovery.
- Least-privilege Cloudflare API token for CI (Workers + D1 only).
- Dependencies pinned and updated deliberately.

### 12.5 ThingsBoard boundary

- Flutter never talks directly to ThingsBoard.
- ThingsBoard API key stays in the API Worker, not in Flutter.
- Device ownership is checked before telemetry/RPC calls.
- RPC endpoints validate the device belongs to the authenticated user.

---

## 13. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Argon2 exceeds free CPU | Intermittent 1102 on login | Measure deployed; keep Argon2 if p99 < 10 ms; otherwise OTP/OAuth/$5. |
| Python Worker cold start | First request slow (~1 s) | Use Hono for auth; keep API routes lean; accept for FYP. |
| D1 free daily limits | Queries fail after 5M reads / 100k writes | Index queries; auth traffic is tiny; monitor usage. |
| ThingsBoard unavailable | Telemetry/RPC 502 | Health check; clear error; retry policy. |
| WS complexity | Reconnect loops, missed updates | Drop WS; use REST polling for the first release. |
| Email deliverability | OTP/reset not received | Use a verified domain with Resend/Brevo; provide fallback. |
| Google consent screen | Only test users can log in | Add test users; publish when ready. |
| Account linking takeover | Wrong account merged | Require password login before linking; no auto-link by email. |
| D1 vendor lock-in | Migration later | Keep schema portable SQL; export with D1 dump. |
| Scope creep | FYP delayed | Ship auth + devices + telemetry first; WS and email flows later. |

---

## 14. Decision Matrix and Recommendations

### 14.1 Pick the constraint that matters most

| Goal | Stack | Cost | Note |
|---|---|---|---|
| Fastest to demo | Supabase Auth + Workers API | $0 | Lowest code change; not own auth. |
| Own auth, free, password | Hono + Argon2 + D1 (if CPU fits) | $0 | Borderline CPU; test deployed. |
| Own auth, free, no password | Email OTP or Google OAuth + D1 | $0 | UI change; no hash risk. |
| Email/password + Google, free | Hono + Argon2 + Google + D1 | $0 | Argon2 must fit; linking rules. |
| Full Workers, lowest risk | Split Auth/API Workers + D1 | $0 or $5 | Drop WS first; add DO later. |
| Email/password, no CPU risk | Workers Paid + Argon2 | $5/month | Simplest reliable password auth. |

### 14.2 Recommended path for LeafLens FYP

1. **Week 1:** Deploy a hello-world Python API Worker; create D1; port devices list/register. Keep the app thin: D1 binding + `pyfetch`, no SQLAlchemy or global pools.
2. **Week 1–2:** Port the ThingsBoard client to `pyfetch`; verify latest/history/RPC against the old API; measure per-route CPU.
3. **Week 2:** Build the Auth Worker (Hono + Argon2 + D1); register/login/refresh/logout/JWKS; measure CPU deployed.
4. **Week 2–3:** Add Google login; implement linking rules; add set-password.
5. **Week 3:** Update Flutter: `AUTH_URL`/`API_URL`, secure storage, refresh, auth state; remove Supabase.
6. **Week 3–4:** CI/CD, custom domains, CORS, monitoring; drop WS and use polling; final security checklist.

### 14.3 What not to do

- Do not move ThingsBoard or the ESP32 to Workers.
- Do not port the whole backend and auth in one big-bang change.
- Do not use bcrypt thinking it is faster; it is usually slower.
- Do not weaken Argon2 to fit 10 ms.
- Do not auto-link Google by email without verification.
- Do not keep the current WS router as-is; it is not a real relay and its auth handshake mismatches Flutter.

### 14.4 Final recommendation

> **Recommended for the FYP:** build a split architecture — a Hono/TypeScript Auth Worker with Argon2 + Google + D1, and a lightweight Python/FastAPI API Worker with D1 for devices and `pyfetch` for ThingsBoard. Keep the Python request path thin. Drop WebSocket for the first release and poll REST; if real-time is a thesis requirement, add a Durable Object per device. Measure Argon2 on the deployed free Worker; if it fits, the whole stack is $0. If it does not, keep Google login and use OTP as the free passwordless fallback, or upgrade to Workers Paid for email/password.

---

## 15. Appendices

### Appendix A — Complete D1 schema

```sql
-- Users: password and/or Google
CREATE TABLE users (
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

-- Refresh tokens: store a hash, never the raw token
CREATE TABLE refresh_tokens (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at INTEGER NOT NULL,
  revoked_at INTEGER,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_refresh_user ON refresh_tokens(user_id);

-- Device mapping
CREATE TABLE user_devices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  tb_device_id TEXT NOT NULL UNIQUE,
  device_name TEXT NOT NULL,
  device_type TEXT NOT NULL DEFAULT 'leaflens-env',
  mac_address TEXT UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_user_devices_user ON user_devices(user_id);

-- Optional: OTP
CREATE TABLE otp_codes (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  used_at INTEGER,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_otp_email ON otp_codes(email);
```

### Appendix B — Commands

```bash
# Create D1
npx wrangler d1 create leaflens

# Migrations
uv run pywrangler d1 migrations apply leaflens --local
uv run pywrangler d1 migrations apply leaflens --remote

# Local dev (Python)
uv run pywrangler dev

# Deploy (Python)
uv run pywrangler deploy

# Secrets
uv run pywrangler secret put JWT_PRIVATE_KEY
uv run pywrangler secret put JWT_PUBLIC_JWKS
uv run pywrangler secret put PASSWORD_PEPPER

# Flutter
flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter analyze
flutter test
flutter build web --release --dart-define-from-file=.env
```

### Appendix C — Migration checklist

| Area | Check |
|---|---|
| Architecture | Choose one Worker or split auth/API; decide D1 vs Hyperdrive; decide WS drop/DO. |
| D1 | Create database; write migrations; apply local and remote; test queries. |
| API Worker | Entrypoint; config; D1; `pyfetch`; remove SQLAlchemy/asyncpg; health check. |
| Auth Worker | Users/refresh tables; Argon2; JWT/JWKS; rate limit; Google; linking. |
| Flutter | `AUTH_URL`/`API_URL`; secure storage; refresh; auth state; Google; remove Supabase. |
| Security | Argon2 params; pepper; dummy hash; CORS; rate limits; no token logs. |
| CI/CD | GitHub Actions checks; Workers Builds; D1 migrations; secrets; custom domains. |
| Testing | Unit, integration, contract, load smoke, security cases. |
| Cleanup | Remove Supabase env/deps; update README; delete old host; rotate secrets. |

### Appendix D — Glossary

| Term | Meaning |
|---|---|
| Access token | Short-lived JWT sent as a Bearer token. |
| Refresh token | Long-lived opaque token used to obtain new access tokens. |
| Argon2id | Memory-hard password hashing algorithm; recommended for new passwords. |
| Bcrypt | Older password hashing algorithm; CPU-hard, 72-byte limit. |
| D1 | Cloudflare's SQLite database. |
| Durable Object | Stateful Cloudflare object for WebSockets, alarms and coordination. |
| Hyperdrive | Cloudflare connection pool/cache for external Postgres/MySQL. |
| JWKS | JSON Web Key Set; public keys used to verify JWT signatures. |
| Pepper | Server-side secret mixed into a password before hashing; not stored in the database. |
| Salt | Random per-user value stored with the hash to prevent rainbow tables. |
| Workers Builds | Cloudflare's GitHub integration that builds and deploys on push. |
| Pyodide | Python runtime compiled to WebAssembly; used by Python Workers. |

---

*This guide is a technical advisory for the LeafLens final year project. It assumes no production users and no requirement to preserve Supabase accounts. Re-test CPU, D1 limits and Google OAuth configuration against the current Cloudflare and Google documentation before deployment.*
