# Lextari API Coding Conventions

---

## Linting & Type Checking

Enforced via ruff (27 rule sets) + mypy strict. Zero warnings, zero errors.

| Tool | Config Location | Run Command |
|------|----------------|-------------|
| ruff | pyproject.toml `[tool.ruff]` | `ruff check .` |
| ruff format | pyproject.toml `[tool.ruff.format]` | `ruff format .` |
| mypy | pyproject.toml `[tool.mypy]` | `mypy src/app` |
| pre-commit | .pre-commit-config.yaml | `uv run pre-commit run --all-files` |

**Rule sets enabled:** E, W, F, I, N, UP, B, A, C4, SIM, TCH, RUF, S, PTH, ERA, PGH, FBT, ICN, PIE, PT, RSE, RET, SLF, T20, PL, PERF, FURB

**Rules ignored (with reason):**
- B008 — FastAPI `Depends()` in function signatures (standard pattern)
- PLW0603 — `global` for singletons (standard pattern)
- PLC0415 — conditional imports (httpx fallback, pyodide)
- PLR2004 — magic values in tests and thresholds
- E501 — line length (formatter handles this)

---

## Naming

| Element | Convention | Example |
|---------|-----------|---------|
| File | snake_case | `thingsboard.py` |
| Class | PascalCase | `ThingsBoardClient` |
| Function | snake_case | `get_health_score()` |
| Constant | UPPER_SNAKE | `_TELEMETRY_KEYS` |
| Private | Leading underscore | `_jwt_token` |
| DB table | snake_case | `user_devices` |
| API path | kebab-case | `/api/v1/devices/{id}` |
| Query param | snake_case | `?days=30` |

---

## Code Style

**Imports:** Sorted by ruff (isort-compatible). Never manually reorder.

```python
# GOOD — stdlib, third-party, first-party
import asyncio
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.clients.thingsboard import get_tb_client
```

**Type annotations:** Required on all functions. Use modern syntax.

```python
# GOOD
def compute_score(values: list[float]) -> tuple[float, str]:
    ...

# BAD — missing annotations
def compute_score(values):
    ...
```

**Pydantic models:** Use `model_config` dict, not `class Config`.

```python
# GOOD
class DeviceResponse(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}

# BAD
class DeviceResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
```

**Error handling:** Never bare `except:`. Always catch specific exceptions.

```python
# GOOD
try:
    result = await tb.get_device(device_id)
except httpx.HTTPStatusError as exc:
    if exc.response.status_code == 404:
        raise DeviceNotFoundError()

# BAD
try:
    result = await tb.get_device(device_id)
except:
    pass
```

---

## Router Rules

1. **Handlers are thin.** Validate request -> call service -> return response.
2. **No business logic in routers.** Business logic lives in `src/app/services/`.
3. **No direct httpx calls.** Use injected `ThingsBoardClient` via `Depends()`.
4. **No raw dicts as responses.** Use Pydantic response models.
5. **Auth via dependency.** `user: dict = Depends(get_current_user)`.

---

## Conventional Commits

Format: `type(scope): description`

| Type | Use For |
|------|---------|
| feat | New feature |
| fix | Bug fix |
| chore | Maintenance, config |
| refactor | Code restructuring |
| docs | Documentation only |
| style | Formatting, linting |
| test | Adding tests |
| build | Build system |
| ci | CI config |
| perf | Performance |

Examples:
```
feat(rpc): add two-way RPC relay with timeout handling
fix(ghs): correct humidity weight calculation
chore(deps): bump fastapi to 0.115.0
```
