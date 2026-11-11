"""Growth Health Score computation service.

Weighted composite: soil moisture (50%), temperature (30%), humidity (20%).
Species-specific thresholds applied via config or default values.
"""

from enum import StrEnum


class GHSStatus(StrEnum):
    OPTIMAL = "Optimal"
    WARNING = "Warning"
    DANGER = "Danger"
    CRITICAL = "Critical"


# Default thresholds for common indoor plants
_DEFAULT_THRESHOLDS: dict[str, dict[str, tuple[float, float]]] = {
    "default": {
        "soil_moisture": (40.0, 80.0),
        "temperature": (18.0, 30.0),
        "humidity": (40.0, 80.0),
    },
}


def _compute_component_score(value: float, optimal_range: tuple[float, float]) -> float:
    """Score a single metric against its optimal range (0-100)."""
    low, high = optimal_range
    if low <= value <= high:
        return 100.0

    deviation = low - value if value < low else value - high

    # Full range deviation allowed before hitting 0
    full_range = high - low
    penalty_per_unit = 100.0 / (full_range * 0.8)
    return max(0.0, 100.0 - deviation * penalty_per_unit)


def compute_health_score(
    soil_moisture: float | None = None,
    temperature: float | None = None,
    humidity: float | None = None,
    species: str = "default",
) -> tuple[float, GHSStatus, dict[str, float]]:
    """Compute weighted Growth Health Score.

    Returns (score, status, component_scores).
    """
    thresholds = _DEFAULT_THRESHOLDS.get(species, _DEFAULT_THRESHOLDS["default"])

    components: dict[str, float] = {}
    weights: dict[str, float] = {
        "soil_moisture": 0.5,
        "temperature": 0.3,
        "humidity": 0.2,
    }

    for key in weights:
        val = locals()[key]
        if val is None:
            components[key] = 50.0  # neutral default when sensor missing
        else:
            components[key] = _compute_component_score(val, thresholds[key])

    score = sum(components[k] * weights[k] for k in weights)

    # Determine status
    if score >= 80:
        status = GHSStatus.OPTIMAL
    elif score >= 60:
        status = GHSStatus.WARNING
    elif score >= 40:
        status = GHSStatus.DANGER
    else:
        status = GHSStatus.CRITICAL

    return round(score, 1), status, components
