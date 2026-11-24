# Lextari API Architecture

> FastAPI backend for Lextari. Reads FavorIoT streams, verifies Lextari auth
> JWTs, and computes Growth Health Score.
> Part of Bachelor of Computer Science FYP at IIUM.

## System position

```
                     ┌─────────────────────────────────────────────┐
                     │            Cloudflare Workers              │
                     │                                             │
  ┌──────────┐     │  ┌───────────┐     ┌──────────────────┐     │     ┌──────────┐
  │  ESP32   │─────┼─>│ FavorIoT  │<────│  lextari-api    │<────┼─────│  Flutter  │
  │ (streams)│     │  │  REST v2  │     │  (FastAPI)       │     │     │   App    │
  └──────────┘     │  └───────────┘     └──────────────────┘     │     └──────────┘
       │           │         ▲                    │               │          │
       │           │         │                    │               │          │
  Sensors +        │  FavorIoT streams       D1 + Auth            │     REST + WS
  Actuators        │                         GHS Compute          │     JWT
                     │                                             │
                     │  ┌───────────┐     ┌──────────────────┐     │
                     │  │    D1     │     │ Auth Worker JWKS │     │
                     │  │ (SQLite)  │     │                  │     │
                     │  └───────────┘     └──────────────────┘     │
                     └─────────────────────────────────────────────┘
```

Rules:

- Flutter never talks to FavorIoT directly. It always goes through lextari-api.
- lextari-api is the only service that holds the FavorIoT API keys.
- The read-only key is used for GET requests. The read-write key is used for
  POST requests.
- Flutter holds the Lextari access token. lextari-api verifies it against the
  auth Worker JWKS.

## Request flow

### Authenticated request

```text
Flutter                    lextari-api                 FavorIoT
  │                            │                            │
  │  GET /api/devices          │                            │
  │  Authorization: Bearer jwt │                            │
  │ ──────────────────────────>│                            │
  │                            │  verify JWT against JWKS   │
  │                            │  read user_devices from D1 │
  │                            │                            │
  │                            │  GET /v2/streams?device_   │
  │                            │    developer_id=...        │
  │                            │  apikey: read-only key     │
  │                            │ ──────────────────────────>│
  │                            │ <──────────────────────────│
  │                            │  normalise data object     │
  │  200 {devices: [...]}      │                            │
  │ <──────────────────────────│                            │
```

### Device provisioning

```text
Caller                      lextari-api                 FavorIoT
  │                            │                            │
  │  POST /api/v1/devices/     │                            │
  │       register             │                            │
  │  {mac_address, user_id,    │                            │
  │   device_name}             │                            │
  │ ──────────────────────────>│                            │
  │                            │  POST /v2/devices          │
  │                            │  apikey: read-write key    │
  │                            │ ──────────────────────────>│
  │                            │ <──────────────────────────│
  │                            │  INSERT user_devices       │
  │                            │                            │
  │  {device_access_token,     │                            │
  │   device_id}               │                            │
  │ <──────────────────────────│                            │
```

### Command flow

```text
Flutter                    lextari-api                 FavorIoT          ESP32
  │                            │                            │              │
  │  POST /api/rpc             │                            │              │
  │  {method: "refill_on"}     │                            │              │
  │ ──────────────────────────>│                            │              │
  │                            │  POST /v2/streams          │              │
  │                            │  {command, params}         │              │
  │                            │  apikey: read-write key    │              │
  │                            │ ──────────────────────────>│              │
  │                            │                            │  firmware    │
  │                            │                            │  reads       │
  │                            │                            │  stream      │
  │                            │                            │ ────────────>│
  │  200 {sent: true}          │                            │              │
  │ <──────────────────────────│                            │              │
```

FavorIoT REST does not provide a two-way RPC channel. Two-way calls return
`501`. The one-way path writes a `command` stream, so the ESP32 firmware must
read that stream or subscribe to an equivalent FavorIoT channel for commands to
take effect.

## Data split

| Data | Stored where | Why |
|------|--------------|-----|
| Sensor telemetry | FavorIoT streams | Existing device ingestion path |
| Device-to-user mapping | D1 (`user_devices`) | Relational, queried by user ID |
| User accounts | Auth Worker D1 | Identity provider |
| GHS score | Computed on demand | Derived from telemetry |
| Command records | FavorIoT streams | Device-visible command delivery |

## Technology stack

| Layer | Technology | Role |
|-------|-----------|------|
| API framework | FastAPI | Async HTTP and WebSocket routes |
| Auth | Lextari JWT and JWKS | Token verification, not issuance |
| Database | Cloudflare D1 | Device-user mapping |
| Migrations | `wrangler d1 migrations` | Schema versioning |
| HTTP client | `pyodide.http.pyfetch` | FavorIoT REST calls |
| WebSocket | FastAPI plus FavorIoT REST polling | Telemetry relay to Flutter |
| Config | Request-scoped dataclass | Workers bindings and env fallback |
| Runtime | Cloudflare Workers with Python | Production deployment |
| Linting | ruff and mypy | Code quality |
| Testing | pytest and pytest-asyncio | Async test support |
