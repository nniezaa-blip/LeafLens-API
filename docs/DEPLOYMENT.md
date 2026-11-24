# Lextari API Deployment

## Local development

Prerequisites: Python 3.13, uv 0.13.4 or newer, and Node.js 22 or newer.

```bash
cd ~/Personal/Dev/lextari-api
mise install
uv sync

cp .dev.vars.example .dev.vars
# Add both FavorIoT keys to .dev.vars. It is gitignored.

uv run pywrangler dev
```

The local Worker listens on `http://localhost:8787`. Swagger UI is available at
`http://localhost:8787/docs` when `DEBUG=true`.

For a plain FastAPI process without the Workers runtime:

```bash
cp .env.example .env
uv run uvicorn app.main:app --app-dir src --reload --port 8000
```

## Test and quality gates

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/app
uv run pytest
uv run pywrangler deploy --dry-run
```

## Cloudflare Workers setup

The Worker is named `lextari-api`. It uses the D1 database `lextari` and the
custom domain `lextari-api.danialsanusi.com`. The route and D1 binding are in
`wrangler.jsonc`.

One-time setup:

```bash
npx wrangler d1 create lextari
# Copy the returned database_id into wrangler.jsonc.

uv sync
uv run pywrangler sync
uv run pywrangler secret put FAVORIOT_READ_ONLY_API_KEY
uv run pywrangler secret put FAVORIOT_READ_WRITE_API_KEY
```

The `user_devices` schema changed with the FavorIoT migration. Recreate the
existing dev database so it matches `migrations/0001_init.sql`:

```bash
npx wrangler d1 execute lextari --remote --command "DROP TABLE IF EXISTS user_devices"
uv run pywrangler d1 migrations apply lextari --remote
```

Device mappings are rebuilt when devices are registered again.

`FAVORIOT_READ_ONLY_API_KEY` is used for `GET /streams` and `GET /devices`.
`FAVORIOT_READ_WRITE_API_KEY` is used for device creation and command streams.
Both keys are required secrets. They are declared in `wrangler.jsonc` under
`secrets.required`, so deployment fails when either is missing. Do not put
either key in `vars`, `.env.example`, or source code.

Local development uses `.dev.vars` instead of remote secrets. Remote secrets are
encrypted bindings and cannot be read back from Wrangler or the dashboard.

## Deploy

```bash
uv run pywrangler d1 migrations apply lextari --remote
uv run pywrangler deploy
```

Pushes to `main` run CI and then the deploy workflow. The workflow applies D1
migrations from the auth Worker, deploys both Workers, and updates the two
FavorIoT secrets from GitHub repository secrets named
`FAVORIOT_READ_ONLY_API_KEY` and `FAVORIOT_READ_WRITE_API_KEY`.

## Required configuration

| Name | Location | Purpose |
|------|----------|---------|
| `FAVORIOT_URL` | `wrangler.jsonc` vars | FavorIoT v2 base URL |
| `FAVORIOT_GROUP_ID` | `wrangler.jsonc` vars | Group used when creating devices |
| `FAVORIOT_READ_ONLY_API_KEY` | Worker secret | Stream and device reads |
| `FAVORIOT_READ_WRITE_API_KEY` | Worker secret | Device creation and command streams |
| `AUTH_JWKS_URL` | `wrangler.jsonc` vars | JWKS endpoint of the auth Worker |
| `AUTH_ISSUER` | `wrangler.jsonc` vars | Expected JWT issuer |
| `AUTH_AUDIENCE` | `wrangler.jsonc` vars | Expected JWT audience |
| `DEBUG` | `wrangler.jsonc` vars | Enables Swagger UI |
| `CORS_ORIGINS` | `wrangler.jsonc` vars | Comma-separated browser origins |
| `WS_POLL_INTERVAL` | `wrangler.jsonc` vars | Seconds between FavorIoT polls |
| `DB` | D1 binding | `user_devices` table |

## Verify the deployed Worker

```bash
curl https://lextari-api.danialsanusi.com/api/v1/health
curl https://lextari-api.danialsanusi.com/api/v1/ready
```

`/api/v1/ready` reports `{"favoriot": true}` when the read-only key is valid.
A valid JWT from the auth Worker is required for device, telemetry, health,
command, and WebSocket routes.
