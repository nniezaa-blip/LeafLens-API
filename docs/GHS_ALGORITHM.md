# Lextari Growth Health Score Algorithm

> Weighted composite of soil moisture, temperature, and humidity against species-specific thresholds.

---

## Formula

```
GHS = (soil_score x 0.5) + (temp_score x 0.3) + (humidity_score x 0.2)
```

| Metric | Weight | Optimal Range (default) |
|--------|--------|------------------------|
| Soil Moisture | 50% | 40.0 - 80.0 |
| Temperature | 30% | 18.0 - 30.0 |
| Humidity | 20% | 40.0 - 80.0 |

---

## Scoring

Each metric is scored 0-100:

- **Within optimal range:** 100.0
- **Outside range:** Linear decay. Full range deviation = 0 score.

```python
def _compute_component_score(value: float, optimal_range: tuple[float, float]) -> float:
    low, high = optimal_range
    if low <= value <= high:
        return 100.0
    deviation = low - value if value < low else value - high
    full_range = high - low
    penalty_per_unit = 100.0 / (full_range * 0.8)
    return max(0.0, 100.0 - deviation * penalty_per_unit)
```

---

## Status Thresholds

| Score | Status | Color |
|-------|--------|-------|
| >= 80 | Optimal | Green |
| >= 60 | Warning | Yellow |
| >= 40 | Danger | Orange |
| < 40 | Critical | Red |

---

## Missing Sensors

When a sensor is unavailable (None), its component score defaults to 50.0 (neutral). This prevents a missing sensor from tanking the overall score, while still reflecting reduced confidence.

---

## API

```python
from app.services.ghs import compute_health_score, GHSStatus

score, status, components = compute_health_score(
    soil_moisture=55.0,
    temperature=23.0,
    humidity=65.0,
    species="default",
)

# score = 85.5
# status = GHSStatus.OPTIMAL
# components = {"soil_moisture": 100.0, "temperature": 80.0, "humidity": 70.0}
```

---

## Adding Species

Add to `_DEFAULT_THRESHOLDS` in `src/app/services/ghs.py`:

```python
_DEFAULT_THRESHOLDS = {
    "default": {
        "soil_moisture": (40.0, 80.0),
        "temperature": (18.0, 30.0),
        "humidity": (40.0, 80.0),
    },
    "cactus": {
        "soil_moisture": (10.0, 30.0),
        "temperature": (20.0, 35.0),
        "humidity": (20.0, 50.0),
    },
}
