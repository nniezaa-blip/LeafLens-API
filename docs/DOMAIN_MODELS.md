# Lextari API Domain Models

---

## Database Models

**File:** `src/app/db/models.py`

### UserDevice

Maps Supabase users to ThingsBoard devices.

| Column | Type | Constraints |
|--------|------|------------|
| id | int | PK, autoincrement |
| user_id | str(36) | indexed |
| tb_device_id | str(36) | unique, indexed |
| device_name | str(100) | |
| device_type | str(50) | default="lextari-env" |
| mac_address | str(17) | unique, nullable |
| created_at | int (unix seconds) | default `unixepoch()` |

---

## Request Schemas

**File:** `src/app/schemas/requests.py`

### DeviceRegisterRequest

| Field | Type | Description |
|-------|------|-------------|
| mac_address | str | ESP32 MAC address |
| user_id | str | Supabase user UUID |
| device_name | str | Human-readable name |

### RPCRequest

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| method | str | required | RPC method name |
| params | dict | None | Method parameters |
| twoway | bool | False | Wait for response? |
| timeout | int | 5000 | Response timeout (ms) |

---

## Response Schemas

**File:** `src/app/schemas/responses.py`

### DeviceResponse

| Field | Type | Description |
|-------|------|-------------|
| id | int | DB primary key |
| tb_device_id | str | ThingsBoard device UUID |
| device_name | str | Human-readable name |
| device_type | str | Device type |
| latest_readings | dict | {key: value} or null |

### HealthScoreResponse

| Field | Type | Description |
|-------|------|-------------|
| device_id | str | ThingsBoard device UUID |
| score | float | 0-100 GHS score |
| status | str | Optimal/Warning/Danger/Critical |
| components | dict | Per-metric scores |

### GHSSummaryResponse

| Field | Type | Description |
|-------|------|-------------|
| device_id | str | ThingsBoard device UUID |
| mean | float | Average GHS over period |
| std | float | Standard deviation |
| min | float | Lowest score |
| max | float | Highest score |
| trend_slope | float | Linear regression slope |
| trend_r2 | float | R-squared value |
| trend_p_value | float | Statistical significance |
| days_optimal | int | Days with score >= 80 |
| days_danger_or_critical | int | Days with score < 40 |
| status_distribution | dict | {status: count} |

---

## Enums

**File:** `src/app/schemas/ws_messages.py`

### WSMessageType

| Value | Description |
|-------|-------------|
| subscribe | Subscribe to device telemetry |
| telemetry | Incoming telemetry data |
| attribute | Attribute update |
| ping | Keepalive |
| pong | Keepalive response |

**File:** `src/app/services/ghs.py`

### GHSStatus

| Value | Score Range |
|-------|------------|
| Optimal | >= 80 |
| Warning | >= 60 |
| Danger | >= 40 |
| Critical | < 40 |

---

## Configuration

**File:** `src/app/config.py`

### Settings

| Field | Type | Default | Required |
|-------|------|---------|----------|
| supabase_url | str | "" | Yes (prod) |
| supabase_jwks_url | str | "" | No (auto-derived) |
| tb_url | str | http://localhost:8080 | No |
| tb_api_key | str | "" | Yes |
| debug | bool | False | No |
| cors_origins | tuple[str, ...] | ("http://localhost:3000",) | No |
| ws_poll_interval | int | 5 | No |
