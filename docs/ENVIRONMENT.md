# Lextari API Environment Variables

Workers bindings are read from the request scope (`request.scope["env"]`). For
local FastAPI runs the same names are read from `.env` or `os.environ`.

Copy `.dev.vars.example` to `.dev.vars` for `pywrangler dev`, or
`.env.example` to `.env` for `uvicorn`. Never commit either file.

## FavorIoT

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FAVORIOT_URL` | No | `https://apiv2.favoriot.com/v2` | FavorIoT v2 base URL |
| `FAVORIOT_READ_ONLY_API_KEY` | Yes | "" | API key for stream and device reads; Worker secret |
| `FAVORIOT_READ_WRITE_API_KEY` | Yes | "" | API key for device creation and command streams; Worker secret |
| `FAVORIOT_GROUP_ID` | No | "" | Group developer ID used when creating devices |

The read-only key is sent as the `apikey` header on `GET` requests. The
read-write key is sent on `POST` requests. Both are JWTs from FavorIoT and must
stay out of source control.

## Auth

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AUTH_JWKS_URL` | Yes | "" | JWKS endpoint of the Lextari auth Worker |
| `AUTH_ISSUER` | No | `lextari-auth` | Expected JWT issuer |
| `AUTH_AUDIENCE` | No | `lextari-app` | Expected JWT audience |

## App

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEBUG` | No | `false` | Swagger UI and debug logging |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated allowed origins |
| `WS_POLL_INTERVAL` | No | `5` | Seconds between FavorIoT stream polls |

## Cloudflare bindings

| Binding | Type | Description |
|---------|------|-------------|
| `DB` | D1 | `user_devices` table |

## Validation

There is no process-level startup validation in Workers because bindings are
request-scoped. D1-backed routes return `503` when the `DB` binding is missing.
FavorIoT routes return `503` when the matching API key secret is missing.
`/api/v1/ready` checks the D1 binding and the FavorIoT read-only key.
