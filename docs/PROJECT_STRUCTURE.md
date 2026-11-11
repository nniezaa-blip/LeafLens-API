# Lextari API Project Structure

---

## Directory Layout

```
lextari-api/
├── src/
│   ├── worker.py                 # Cloudflare Workers entrypoint
│   └── app/
│       ├── __init__.py
│       ├── py.typed              # PEP 561 marker
│       ├── main.py               # App factory + health probes
│       ├── config.py             # Request-scoped Settings
│       ├── logging_config.py     # JSON structured logging
│       ├── middleware.py         # Request ID + access logging
│       ├── auth/
│       │   ├── jwks.py           # Supabase JWT verify (cached JWKS)
│       │   └── dependencies.py   # get_current_user FastAPI dep
│       ├── clients/
│       │   ├── http.py           # pyfetch + httpx fallback
│       │   └── thingsboard.py    # TB REST client
│       ├── db/
│       │   ├── d1.py             # D1 query helpers + binding deps
│       │   └── models.py         # UserDevice row model
│       ├── routers/
│       │   ├── devices.py        # POST register, GET list, GET detail
│       │   ├── telemetry.py      # GET latest, GET history
│       │   ├── health.py         # GET GHS score, GET summary
│       │   ├── rpc.py            # POST relay to ESP32
│       │   └── ws.py             # WebSocket telemetry poller
│       ├── schemas/
│       │   ├── requests.py       # DeviceRegisterRequest, RPCRequest
│       │   ├── responses.py      # DeviceResponse, HealthScoreResponse
│       │   └── ws_messages.py    # WSMessageType enum
│       ├── services/
│       │   ├── devices.py        # Resolve user -> device
│       │   └── ghs.py            # Growth Health Score algorithm
│       └── utils/
│           └── errors.py         # LextariError hierarchy + handler
├── tests/
│   ├── conftest.py               # Shared fixtures (client)
│   ├── fakes.py                  # FakeD1 + FakeThingsBoard
│   ├── test_auth.py              # Health probe
│   ├── test_client_compat.py     # Flutter-facing routes
│   ├── test_devices.py           # Device list
│   ├── test_ghs.py               # GHS unit tests
│   ├── test_health.py            # Health endpoint
│   └── test_ws.py                # WebSocket contract
├── docs/                         # This directory
├── migrations/                   # D1 migrations
├── .github/workflows/            # CI + Cloudflare deploy
├── .pre-commit-config.yaml       # Git hooks
├── pyproject.toml                # deps + ruff + mypy + pytest
├── uv.lock                       # Locked local dependencies
├── pylock.toml                   # Locked Worker/Pyodide dependencies
├── wrangler.jsonc                # Worker + D1 config
├── docker-compose.yml            # Local ThingsBoard stack
├── .gitignore
├── .gitattributes
├── .dev.vars.example             # Workers local template
└── .env.example                  # Plain FastAPI template
```

---

## Where to Put Code

| Type | Location | Example |
|------|----------|---------|
| New endpoint | `src/app/routers/` | `src/app/routers/alerts.py` |
| New DB row model | `src/app/db/models.py` | Add class to existing file |
| New SQL helper | `src/app/db/d1.py` | Add function |
| New schema | `src/app/schemas/` | `src/app/schemas/alerts.py` |
| Business logic | `src/app/services/` | `src/app/services/alerts.py` |
| External API client | `src/app/clients/` | `src/app/clients/email.py` |
| Custom error | `src/app/utils/errors.py` | Add subclass to existing file |
| Config field | `src/app/config.py` | Add to Settings class |
| Test | `tests/` | `test_alerts.py` |

---

## Tooling

| Package | Version | Role |
|---------|---------|------|
| ruff | 0.17+ | Linting + formatting |
| mypy | 2.4+ | Static type checking |
| pre-commit | 4.0+ | Git hook manager |
| commitizen | 4.0+ | Conventional commits |
| pytest | 9.0+ | Test runner |
| pytest-asyncio | 1.4+ | Async test support |
| workers-py | 1.17+ | `pywrangler` CLI + Workers runtime |
