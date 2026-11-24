# Lextari API

<img src="https://img.shields.io/badge/version-1.0.0-5BC0DE?style=flat-square" alt="Version">&nbsp;
<img src="https://img.shields.io/badge/Python-3.13-5BC0DE?style=flat-square&logo=python&logoColor=white" alt="Python">&nbsp;
<img src="https://img.shields.io/badge/FastAPI-0.115-5BC0DE?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">&nbsp;
<img src="https://img.shields.io/badge/Cloudflare-Workers-F38020?style=flat-square&logo=cloudflare&logoColor=white" alt="Cloudflare Workers">&nbsp;
<img src="https://img.shields.io/badge/FavorIoT-IoT-5BC0DE?style=flat-square" alt="FavorIoT">&nbsp;
<img src="https://img.shields.io/badge/Supabase-Auth-5BC0DE?style=flat-square" alt="Supabase">

**FastAPI Backend for Lextari Plant Health Monitoring System**

Part of Final Year Project — Bachelor of Computer Science, IIUM
**Supervisor:** Ts. Dr. Ahmad Anwar bin Zainuddin

---

## Overview

Lextari API is the backend gateway for the Lextari plant health monitoring
system. It sits between the Flutter mobile app and FavorIoT, handling
authentication, telemetry proxying, device management, and Growth Health Score
computation.

**What it does:**
- Verifies Lextari auth JWTs (via JWKS) — never issues tokens, only validates
- Reads FavorIoT device and stream data — Flutter never talks to FavorIoT directly
- Writes one-way command streams for actuator firmware to consume
- Computes Growth Health Score (GHS) — weighted composite of sensor readings
- WebSocket relay — polls FavorIoT streams and pushes telemetry changes to Flutter

**What it does NOT do:**
- Does not store sensor data (FavorIoT handles that)
- Does not manage user accounts (the Lextari auth Worker handles that)
- Does not talk to ESP32 directly (commands are published as FavorIoT streams)

---

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              Cloudflare Workers             │
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

Full architecture details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Documentation

| Doc | Description |
|-----|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design, data flows, tech stack |
| [API Reference](docs/API_REFERENCE.md) | All endpoints with request/response examples |
| [Conventions](docs/CONVENTIONS.md) | Coding standards, lint rules, commit format |
| [Project Structure](docs/PROJECT_STRUCTURE.md) | Directory layout, where to put code |
| [Error Handling](docs/ERROR_HANDLING.md) | Error hierarchy, Workers logging |
| [Testing](docs/TESTING.md) | How to run and write tests |
| [GHS Algorithm](docs/GHS_ALGORITHM.md) | Growth Health Score formula and thresholds |
| [Domain Models](docs/DOMAIN_MODELS.md) | DB models, schemas, enums |
| [Environment](docs/ENVIRONMENT.md) | All env vars with descriptions |
| [Deployment](docs/DEPLOYMENT.md) | Local Workers, D1, and CI/CD setup |

---

## Prerequisites

- **Python 3.13+** and **uv 0.13.4+**
- **Node.js 22+** (for local `pywrangler`)
- **Cloudflare account** with Workers + D1
- **FavorIoT account** with read-only and read/write API keys
- **Lextari auth Worker** (JWKS endpoint for token verification)

---

## Getting Started

### 1. Clone and install

```bash
cd ~/Personal/Dev/lextari-api

# Python + Node versions (via mise)
mise install
eval "$(mise activate zsh)"

# Dependencies
uv sync

# Pre-commit hooks
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
```

### 2. Configure

```bash
cp .dev.vars.example .dev.vars
# Edit .dev.vars with your FavorIoT keys and AUTH_JWKS_URL.
```

### 3. Run

```bash
# Cloudflare Workers runtime (recommended)
uv run pywrangler dev

# Plain FastAPI fallback (uses the httpx client fallback)
uv run uvicorn app.main:app --app-dir src --reload --port 8000
```

### 4. Verify

```bash
# Health probe
curl http://localhost:8787/api/v1/health

# Swagger UI (debug mode only)
open http://localhost:8787/docs
```

---

## Running Tests

```bash
DEBUG=true FAVORIOT_READ_ONLY_API_KEY=test-read-key FAVORIOT_READ_WRITE_API_KEY=test-write-key uv run pytest
```

### Test summary

```
tests/test_auth.py          — 1 test  (health probe)
tests/test_client_compat.py — 5 tests (Flutter-facing routes)
tests/test_devices.py       — 1 test  (device list)
tests/test_favoriot_client.py — 5 tests (Agrilink stream mapping)
tests/test_ghs.py           — 3 tests (GHS computation)
tests/test_health.py        — 1 test  (health endpoint)
tests/test_ws.py            — 1 test  (WebSocket contract)
                            ─────────
                            17 passed
```

---

## Project Structure

```
lextari-api/
├── src/
│   ├── worker.py           # Cloudflare Workers entrypoint
│   └── app/
│       ├── main.py         # App factory + health probes
│       ├── config.py       # Request-scoped Settings
│       ├── middleware.py   # Request ID + access logging
│       ├── auth/           # JWKS verification
│       ├── clients/        # pyfetch HTTP + FavorIoT REST
│       ├── db/             # D1 helpers + row models
│       ├── routers/        # API endpoints
│       ├── schemas/        # Pydantic request/response
│       ├── services/       # GHS computation
│       └── utils/          # Error hierarchy
├── tests/                  # pytest async tests + fakes
├── docs/                   # Documentation
├── migrations/             # D1 migrations
├── .github/workflows/      # CI + Cloudflare deploy
├── wrangler.jsonc          # Worker config (lextari-api)
├── pyproject.toml          # deps + ruff + mypy + pytest config
└── .pre-commit-config.yaml # Git hooks
```

Full layout: [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)

---

## Linting & Type Checking

```bash
# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
uv run mypy src/app

# All pre-commit hooks
uv run pre-commit run --all-files
```

**27 rule sets enabled.** Zero warnings, zero errors.

Full conventions: [docs/CONVENTIONS.md](docs/CONVENTIONS.md)

---

## Pre-commit Hooks

| Hook | What it does |
|------|-------------|
| ruff | Lint + auto-fix staged .py files |
| ruff-format | Format staged .py files |
| conventional-pre-commit | Enforce `type(scope): description` format |
| trailing-whitespace | Remove trailing spaces |
| end-of-file-fixer | Ensure newline at EOF |
| check-yaml / check-toml | Validate config files |
| check-added-large-files | Block files >500KB |
| check-merge-conflict | Detect unresolved merges |
| debug-statements | Block pdb/breakpoint in prod |

**Commit format:**
```
feat(backend): add WebSocket relay
fix(ghs): correct humidity weight
docs(api): update endpoint specs
```

Allowed scopes: `backend`, `auth`, `api`, `db`, `ghs`, `rpc`, `ws`, `docker`, `ci`, `deps`, `config`, `tests`, `middleware`

---

## Growth Health Score (GHS)

Weighted composite of sensor readings:

| Metric | Weight | Optimal Range |
|--------|--------|---------------|
| Soil Moisture | 50% | 40.0 - 80.0 |
| Temperature | 30% | 18.0 - 30.0 |
| Humidity | 20% | 40.0 - 80.0 |

| Score | Status |
|-------|--------|
| >= 80 | Optimal |
| >= 60 | Warning |
| >= 40 | Danger |
| < 40 | Critical |

Full algorithm: [docs/GHS_ALGORITHM.md](docs/GHS_ALGORITHM.md)

---

## Cloudflare Workers (CI/CD)

Pushes to `main` run CI (`ruff`, `mypy`, `pytest`) and then deploy the
**`lextari-api`** Worker to Cloudflare using GitHub Actions and `pywrangler`.

```bash
# Local Worker development
uv sync
cp .dev.vars.example .dev.vars
uv run pywrangler dev
```

Setup, required secrets and the D1 database name are documented in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#cloudflare-workers-cicd).

---

## Hardware

This backend supports the Lextari dual-ESP32 system:

| Sensor | Reading | Key |
|--------|---------|-----|
| Soil Moisture | Capacitive probe | `soil_moisture` |
| Temperature | DHT22 | `temperature` |
| Humidity | DHT22 | `humidity` |
| Water Level | Ultrasonic | `water_level` |

| Actuator | Control |
|----------|---------|
| Water Pump | RPC `triggerWatering` |
| Mist Maker | RPC `triggerMisting` |
| Solenoid Valve | RPC `openRefill` |

---

## Related Repositories

| Repository | Description |
|-----------|-------------|
| [Lextari](https://github.com/mishoshup/Lextari) | Flutter mobile app |
| Lextari API | FastAPI backend (this repo) |
| [FavorIoT](https://platform.favoriot.com/tutorial/v2/) | IoT platform and stream API |

---

## License

This project is part of a Bachelor of Computer Science FYP at IIUM.
Internal use only — not licensed for distribution.
