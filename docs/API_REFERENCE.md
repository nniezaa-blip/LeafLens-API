# Lextari API Reference

All endpoints are prefixed with `/api/v1`. Auth endpoints use `Authorization: Bearer <jwt>` header.

---

## Health Probes

No auth. Rate limiting is handled by Cloudflare edge rules.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Liveness probe |
| GET | `/api/v1/ready` | Readiness probe (DB + TB) |

### GET /api/v1/health

```
Response: 200
{
  "status": "ok",
  "version": "1.0.0"
}
```

### GET /api/v1/ready

```
Response: 200 (all healthy)
{
  "status": "ready",
  "checks": {
    "database": true,
    "thingsboard": true
  }
}

Response: 503 (degraded)
{
  "status": "degraded",
  "checks": {
    "database": true,
    "thingsboard": false
  }
}
```

---

## Devices

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/devices/register` | ESP32 token | Register new device |
| GET | `/api/v1/devices` | JWT | List user devices |
| GET | `/api/v1/devices/{device_id}` | JWT | Device detail + readings |

### POST /api/v1/devices/register

Called by ESP32 after BLE onboarding. Creates TB device, saves mapping.

```
Request:
{
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "user_id": "uuid-from-supabase",
  "device_name": "Living Room Plant"
}

Response: 200
{
  "thingsboard_token": "auto-generated-mqtt-token",
  "device_id": "tb-uuid-device-id"
}
```

### GET /api/v1/devices

```
Response: 200
[
  {
    "id": 1,
    "tb_device_id": "abc-123",
    "device_name": "Living Room Plant",
    "device_type": "lextari-env",
    "latest_readings": {
      "soil_moisture": 55.0,
      "temperature": 24.0,
      "humidity": 65.0,
      "water_level": 80.0
    }
  }
]
```

### GET /api/v1/devices/{device_id}

```
Response: 200
{
  "id": 1,
  "tb_device_id": "abc-123",
  "device_name": "Living Room Plant",
  "device_type": "lextari-env",
  "latest_readings": {
    "soil_moisture": 55.0,
    "temperature": 24.0,
    "humidity": 65.0,
    "water_level": 80.0
  }
}
```

---

## Telemetry

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/telemetry/{id}/latest` | JWT | Latest sensor readings |
| GET | `/api/v1/telemetry/{id}/history` | JWT | 30-day historical data |

### GET /api/v1/telemetry/{device_id}/latest

```
Response: 200
{
  "device_id": "abc-123",
  "readings": {
    "soil_moisture": 55.0,
    "temperature": 24.0,
    "humidity": 65.0,
    "water_level": 80.0
  }
}
```

### GET /api/v1/telemetry/{device_id}/history

Query params: `days` (int, 1-90, default 30)

```
Response: 200
{
  "device_id": "abc-123",
  "history": {
    "soil_moisture": [
      {"ts": 1716800000000, "value": "55.0"},
      {"ts": 1716803600000, "value": "54.5"}
    ],
    "temperature": [...],
    "humidity": [...]
  }
}
```

Aggregation: 1-hour AVG intervals. Timestamps in milliseconds.

---

## Health Score

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/health/{id}` | JWT | Current GHS |
| GET | `/api/v1/health/{id}/summary` | JWT | 30-day summary |

### GET /api/v1/health/{device_id}

```
Response: 200
{
  "device_id": "abc-123",
  "score": 85.5,
  "status": "Optimal",
  "components": {
    "soil_moisture": 100.0,
    "temperature": 80.0,
    "humidity": 70.0
  }
}
```

### GET /api/v1/health/{device_id}/summary

Query params: `days` (int, 7-90, default 30)

```
Response: 200
{
  "device_id": "abc-123",
  "mean": 78.3,
  "std": 12.1,
  "min": 45.0,
  "max": 100.0,
  "trend_slope": -0.05,
  "trend_r2": 0.82,
  "trend_p_value": 0.001,
  "days_optimal": 22,
  "days_danger_or_critical": 2,
  "status_distribution": {
    "Optimal": 22,
    "Warning": 6,
    "Danger": 1,
    "Critical": 1
  }
}
```

---

## RPC

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/rpc/{device_id}` | JWT | Send command to ESP32 |

### POST /api/v1/rpc/{device_id}

```
Request:
{
  "method": "triggerWatering",
  "params": {"duration": 30},
  "twoway": false,
  "timeout": 5000
}

Response: 200 (one-way)
{
  "device_id": "abc-123",
  "method": "triggerWatering",
  "sent": true
}

Response: 200 (two-way)
{
  "device_id": "abc-123",
  "method": "getStatus",
  "result": {"water_level": 80, "pump_active": false}
}

Response: 200 (device offline, command queued)
{
  "device_id": "abc-123",
  "method": "triggerWatering",
  "queued": true
}
```

---

## WebSocket

| Protocol | Path | Auth | Description |
|----------|------|------|-------------|
| WS | `/ws` or `/api/v1/ws?token=<jwt>` | JWT (query param or first message) | Real-time telemetry |

Close codes: `4001` (missing token), `4003` (invalid token)

### Messages

The server polls ThingsBoard every `WS_POLL_INTERVAL` seconds and pushes changes.

```
Client -> Server:
  {"type": "auth", "token": "<supabase_jwt>"}
  {"type": "subscribe", "device_id": "abc-123"}
  {"type": "ping"}

Server -> Client:
  {"type": "auth_ok"}
  {"type": "subscribed", "device_id": "abc-123"}
  {"type": "pong"}
  {"type": "telemetry", "soilMoisture": 55.0, "temperature": 23.0, "humidity": 65.0}
  {"type": "ghs", "score": 100.0, "status": "Optimal"}
```

`auth` is only required when the token is not supplied as a query parameter.
On connect the server auto-subscribes to the user's first linked device and
sends an initial telemetry snapshot plus the current health score.

---

## Error Responses

All errors follow the same shape:

```json
{
  "error": "Human-readable message",
  "type": "ErrorClassName",
  "request_id": "abc123-def456"
}
```

| Status | Type | When |
|--------|------|------|
| 401 | AuthError | Invalid or expired JWT |
| 404 | DeviceNotFoundError | Device not found |
| 500 | LextariError | Auth not configured |
| 502 | ThingsBoardError | TB unavailable |
| 503 | ReadyResponse | Health check failed |

---

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 401 | Unauthorized (bad/missing JWT) |
| 404 | Not found |
| 429 | Rate limited |
| 500 | Internal server error |
| 502 | Upstream (ThingsBoard) error |
| 503 | Service degraded |
