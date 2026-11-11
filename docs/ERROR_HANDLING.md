# Lextari API Error Handling

> Structured exceptions + JSON responses + Workers Logs.

---

## Architecture

```
  Request
     │
     v
  FastAPI Router
     │
     ├── LextariError raised ──> lextari_error_handler
     │                                │
     │                                ├── Log (structured JSON)
     │                                └── JSONResponse {error, type, request_id}
     │
     └── Unhandled exception ──> FastAPI default 500 handler
```

---

## Error Hierarchy

| Class | Status | Detail |
|-------|--------|--------|
| `LextariError` | 500 | "Internal server error" |
| `DeviceNotFoundError` | 404 | "Device not found" |
| `ThingsBoardError` | 502 | "ThingsBoard service unavailable" |
| `AuthError` | 401 | "Authentication failed" |

**Rules:**
- Always raise specific subclasses, never `LextariError` directly.
- Every error response includes `request_id` for tracing.
- Never expose internal details (stack traces, DB errors) to clients.

---

## Usage in Routers

```python
from app.utils.errors import DeviceNotFoundError

@router.get("/api/v1/devices/{device_id}")
async def get_device(device_id: str, ...):
    device = await db.get(device_id)
    if device is None:
        raise DeviceNotFoundError()
    return device
```

---

## Middleware Errors

| Middleware | Error | Response |
|-----------|-------|----------|
| RequestIDMiddleware | (never fails) | Adds `X-Request-ID` header |

Rate limiting is not enforced in-process because Workers isolates do not share
memory. Use Cloudflare rate limiting rules at the edge instead.

---

## Upstream Errors

`src/app/clients/http.py` raises `FetchError(status_code, detail)` for any non-2xx
upstream response. Routers translate specific statuses where needed (for
example, ThingsBoard `504` becomes `{"queued": true}` for RPC). Observability
comes from Workers Logs / the `observability` setting in `wrangler.jsonc`.
