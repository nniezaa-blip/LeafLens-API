# Lextari API Architecture

> FastAPI backend for Lextari. Proxies ThingsBoard, verifies Supabase JWT, computes Growth Health Score.
> Part of Bachelor of Computer Science FYP at IIUM.

---

## System Position

```
                    ┌─────────────────────────────────────────────┐
                    │                 Cloud / VPS                 │
                    │                                             │
  ┌──────────┐     │  ┌───────────┐     ┌──────────────────┐     │     ┌──────────┐
  │  ESP32   │─────┼─>│ ThingsBoard│<────│  lextari-api    │<────┼─────│  Flutter  │
  │ (MQTT)   │     │  │  :8080    │     │ (Workers)        │     │     │   App    │
  └──────────┘     │  └───────────┘     └──────────────────┘     │     └──────────┘
       │           │         ▲                    │               │          │
       │           │         │                    │               │          │
  Sensors +        │    TB REST API          DB + Auth            │     REST + WS
  Actuators        │    TB REST poll         GHS Compute          │     JWT
                    │                                             │
                    │  ┌───────────┐     ┌──────────────────┐     │
                    │  │    D1     │     │    Supabase      │     │
                    │  │ (SQLite)  │     │  (Auth only)     │     │
                    │  └───────────┘     └──────────────────┘     │
                    └─────────────────────────────────────────────┘
```

**Rules:**
- Flutter NEVER talks to ThingsBoard directly. Always through lextari-api.
- lextari-api is the ONLY service that holds TB_API_KEY.
- Flutter holds Supabase JWT (via SDK). lextari-api verifies it.

---

## Request Flow

### 1. Authenticated Request (Flutter -> API)

```
Flutter                    lextari-api                 ThingsBoard
  │                            │                            │
  │  GET /api/v1/devices       │                            │
  │  Authorization: Bearer jwt │                            │
  │ ──────────────────────────>│                            │
  │                            │  verify JWT (cached JWKS)  │
  │                            │  ── extract user_id ──     │
  │                            │                            │
  │                            │  GET /api/device           │
  │                            │  X-Authorization: ApiKey   │
  │                            │ ──────────────────────────>│
  │                            │ <──────────────────────────│
  │                            │                            │
  │  200 {devices: [...]}      │                            │
  │ <──────────────────────────│                            │
```

### 2. Device Provisioning (ESP32 -> API)

```
ESP32                       lextari-api                 ThingsBoard
  │                            │                            │
  │  POST /api/v1/devices/     │                            │
  │       register             │                            │
  │  {mac_address, user_id,    │                            │
  │   device_name}             │                            │
  │ ──────────────────────────>│                            │
  │                            │  POST /api/device          │
  │                            │ ──────────────────────────>│
  │                            │ <──────────────────────────│
  │                            │  GET /credentials          │
  │                            │ ──────────────────────────>│
  │                            │ <──────────────────────────│
  │                            │  INSERT user_devices       │
  │                            │                            │
  │  {thingsboard_token,       │                            │
  │   device_id}               │                            │
  │ <──────────────────────────│                            │
  │                            │                            │
  │  ─── ESP32 stores token, connects via MQTT ───          │
```

### 3. RPC Command (Flutter -> ESP32)

```
Flutter                    lextari-api             ThingsBoard          ESP32
  │                            │                        │                  │
  │  POST /api/v1/rpc/{id}     │                        │                  │
  │  {method: "water"}         │                        │                  │
  │ ──────────────────────────>│                        │                  │
  │                            │  POST /api/rpc/oneway  │                  │
  │                            │ ──────────────────────>│                  │
  │                            │                        │  MQTT publish    │
  │                            │                        │ ────────────────>│
  │                            │                        │                  │
  │  200 {sent: true}          │                        │                  │
  │ <──────────────────────────│                        │                  │
```

---

## Data Split

| Data | Stored Where | Why |
|------|-------------|-----|
| Sensor telemetry | ThingsBoard | Time-series optimized, MQTT ingestion |
| Device-to-user mapping | D1 (`user_devices`) | Relational, queried by user_id |
| User accounts | Supabase | Auth provider, JWT issuance |
| GHS score | Computed on-demand | No storage needed, derived from telemetry |
| Actuator state | ThingsBoard shared attributes | Real-time, synced to ESP32 |

---

## Technology Stack

| Layer | Technology | Role |
|-------|-----------|------|
| API Framework | FastAPI 0.115+ | Async HTTP/WebSocket server |
| Auth | Supabase JWT + JWKS | Token verification (not issuance) |
| Database | Cloudflare D1 | Device-user mapping |
| Migrations | `wrangler d1 migrations` | Schema versioning |
| HTTP Client | `pyodide.http.pyfetch` | ThingsBoard REST proxy |
| WebSocket | FastAPI + TB REST polling | Telemetry relay to Flutter |
| Config | Request-scoped dataclass | Workers bindings + env fallback |
| Runtime | Cloudflare Workers (Python) | Production deployment |
| Linting | ruff (27 rules) + mypy strict | Code quality |
| Testing | pytest + pytest-asyncio | Async test support |
