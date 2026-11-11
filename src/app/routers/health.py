"""Health Score endpoints - GHS computation."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_current_user
from app.clients.thingsboard import ThingsBoardClient, get_tb_client
from app.db.d1 import get_db
from app.schemas.responses import GHSSummaryResponse, HealthScoreResponse
from app.services.devices import resolve_user_device
from app.services.ghs import compute_health_score

router = APIRouter()


@router.get("/api/v1/health/{device_id}", response_model=HealthScoreResponse)
async def get_health_score(
    device_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    tb: ThingsBoardClient = Depends(get_tb_client),
) -> HealthScoreResponse:
    """Current Growth Health Score - computed from latest telemetry."""
    readings = await tb.get_latest_telemetry(
        device_id,
        keys=["soil_moisture", "temperature", "humidity"],
    )
    score, status, components = compute_health_score(
        soil_moisture=readings.get("soil_moisture"),
        temperature=readings.get("temperature"),
        humidity=readings.get("humidity"),
    )
    return HealthScoreResponse(
        device_id=device_id,
        score=score,
        status=status.value,
        components=components,
    )


@router.get("/api/health-score")
async def get_health_score_for_user(
    user: dict[str, Any] = Depends(get_current_user),
    db: Any = Depends(get_db),
    tb: ThingsBoardClient = Depends(get_tb_client),
) -> dict[str, object]:
    """Current GHS for the authenticated user's linked device."""
    device = await resolve_user_device(user["sub"], db)
    readings = await tb.get_latest_telemetry(
        device.tb_device_id,
        keys=["soil_moisture", "temperature", "humidity"],
    )
    score, status, components = compute_health_score(
        soil_moisture=readings.get("soil_moisture"),
        temperature=readings.get("temperature"),
        humidity=readings.get("humidity"),
    )
    return {
        "score": score,
        "status": status.value,
        "component_scores": components,
        "computed_at": datetime.now(UTC).isoformat(),
    }


@router.get("/api/v1/health/{device_id}/summary")
async def get_health_summary(
    device_id: str,
    days: int = Query(default=30, ge=7, le=90),
    user: dict[str, Any] = Depends(get_current_user),
    tb: ThingsBoardClient = Depends(get_tb_client),
) -> GHSSummaryResponse:
    """30-day health summary for thesis methodology."""
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    telemetry = await tb.get_telemetry_history(
        device_id,
        keys=["soil_moisture", "temperature", "humidity"],
        start_ts_ms=int(start.timestamp() * 1000),
        end_ts_ms=int(end.timestamp() * 1000),
        agg="AVG",
        interval_ms=3_600_000,
    )

    scores: list[float] = []
    for key, entries in telemetry.items():
        for entry in entries:
            value = float(entry["value"])
            if key == "soil_moisture":
                score, _, _ = compute_health_score(soil_moisture=value)
            elif key == "temperature":
                score, _, _ = compute_health_score(temperature=value)
            elif key == "humidity":
                score, _, _ = compute_health_score(humidity=value)
            else:
                continue
            scores.append(score)

    avg_score = sum(scores) / len(scores) if scores else 0.0

    return GHSSummaryResponse(
        device_id=device_id,
        mean=round(avg_score, 1),
        std=0.0,
        min=round(min(scores), 1) if scores else 0.0,
        max=round(max(scores), 1) if scores else 0.0,
        trend_slope=0.0,
        trend_r2=0.0,
        trend_p_value=0.0,
        days_optimal=sum(1 for score in scores if score >= 80),
        days_danger_or_critical=sum(1 for score in scores if score < 40),
        status_distribution={},
    )
