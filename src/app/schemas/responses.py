"""Response body models."""

from pydantic import BaseModel


class DeviceResponse(BaseModel):
    """Device listing with latest readings."""

    id: int
    tb_device_id: str
    device_name: str
    device_type: str
    latest_readings: dict[str, float] | None = None


class HealthScoreResponse(BaseModel):
    """Current Growth Health Score."""

    device_id: str
    score: float
    status: str
    components: dict[str, float]


class GHSSummaryResponse(BaseModel):
    """30-day health summary."""

    device_id: str
    mean: float
    std: float
    min: float
    max: float
    trend_slope: float
    trend_r2: float
    trend_p_value: float
    days_optimal: int
    days_danger_or_critical: int
    status_distribution: dict[str, int]
