# Lextari API Environment Variables

Workers bindings are read from the request scope (`request.scope["env"]`), with
a global `workers.env` fallback for app-level settings such as CORS and docs.
For local FastAPI runs, the same names are read from `.env` / `os.environ`.

Copy `.dev.vars.example` to `.dev.vars` for `pywrangler dev`, or
`.env.example` to `.env` for `uvicorn`. Never commit either file.

---

## Variables

### Supabase (Auth)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| SUPABASE_URL | Yes (prod) | "" | `https://xyz.supabase.co` |
| SUPABASE_JWKS_URL | No | Auto-derived | Override JWKS endpoint |

### ThingsBoard

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| TB_URL | No | http://localhost:8080 | ThingsBoard base URL |
| TB_API_KEY | Yes | "" | API key (Tenant Settings); store as a Worker secret |

### App

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| DEBUG | No | false | Swagger UI + debug logging |
| CORS_ORIGINS | No | http://localhost:3000 | Comma-separated allowed origins |
| WS_POLL_INTERVAL | No | 5 | Seconds between ThingsBoard polls |

### Cloudflare bindings (not env vars)

| Binding | Type | Description |
|---------|------|-------------|
| DB | D1 | `user_devices` and future tables |

---

## Getting Your ThingsBoard API Key

1. ThingsBoard UI -> API Keys (bottom-left sidebar)
2. Add New API Key -> name it `lextari-backend`
3. Copy the key value
4. Set as `TB_API_KEY` (Worker secret in production)

The API key gives full tenant-level access. Keep it secret.

---

## Validation

There is no process-level startup validation in Workers, because bindings are
request-scoped. Endpoints that need auth return `500 Auth not configured` when
`SUPABASE_URL` and `SUPABASE_JWKS_URL` are both empty, and D1-backed endpoints
return `503` when the `DB` binding is missing.
