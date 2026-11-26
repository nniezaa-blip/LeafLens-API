"""FavorIoT client tests against the Agrilink stream shape."""

from typing import Any

import pytest

from app.clients import favoriot as favoriot_client
from app.clients.favoriot import (
    FavorIoTClient,
    _format_created_range,
    _row_timestamp,
)
from app.config import Settings

DEVICE_ID = "Agrilink_1_device@anwarzain"

AGRI_LINK_ROWS: list[dict[str, Any]] = [
    {
        "timestamp": 1_792_114_890_241,
        "stream_created_at": "2026-10-16T01:41:30.241Z",
        "device_developer_id": DEVICE_ID,
        "data": {
            "fanStatus": "OFF",
            "humidity": "73",
            "mistStatus": "OFF",
            "pumpStatus": "ON",
            "soil_moisture": "0",
            "temperature": "22",
        },
    },
    {
        "timestamp": 1_792_114_886_539,
        "stream_created_at": "2026-10-16T01:41:26.539Z",
        "device_developer_id": DEVICE_ID,
        "data": {
            "humidity": "74",
            "soil_moisture": "2",
            "temperature": "21",
        },
    },
]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        favoriot_read_only_api_key="read-key",
        favoriot_read_write_api_key="write-key",
        favoriot_group_id="Agrilink_group@anwarzain",
    )


def test_row_timestamp_prefers_epoch_field() -> None:
    assert _row_timestamp(AGRI_LINK_ROWS[0]) == 1_792_114_890_241


def test_created_range_preserves_milliseconds() -> None:
    assert _format_created_range(1_792_114_886_539, 1_792_114_890_241) == (
        "[2026-10-16T01:41:26.539Z TO 2026-10-16T01:41:30.241Z]"
    )


@pytest.mark.asyncio
async def test_latest_telemetry_reads_agrilink_stream(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_fetch_json(url: str, **kwargs: Any) -> Any:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        return {"statusCode": 200, "numFound": 2, "results": AGRI_LINK_ROWS}

    monkeypatch.setattr(favoriot_client, "fetch_json", fake_fetch_json)

    result = await FavorIoTClient(settings).get_latest_telemetry(
        DEVICE_ID,
        keys=["soil_moisture", "temperature", "humidity", "water_level"],
    )

    assert result == {"soil_moisture": 0.0, "temperature": 22.0, "humidity": 73.0}
    assert "device_developer_id=Agrilink_1_device%40anwarzain" in captured["url"]
    assert "order=desc" in captured["url"]
    assert captured["headers"]["apikey"] == "read-key"


@pytest.mark.asyncio
async def test_latest_readings_keep_the_recording_timestamp(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    async def fake_fetch_json(url: str, **kwargs: Any) -> Any:
        return {"statusCode": 200, "numFound": 2, "results": AGRI_LINK_ROWS}

    monkeypatch.setattr(favoriot_client, "fetch_json", fake_fetch_json)

    result = await FavorIoTClient(settings).get_latest_readings(
        DEVICE_ID,
        keys=["soil_moisture", "temperature", "humidity", "water_level"],
    )

    assert result == {
        "soil_moisture": (0.0, 1_792_114_890_241),
        "temperature": (22.0, 1_792_114_890_241),
        "humidity": (73.0, 1_792_114_890_241),
    }


@pytest.mark.asyncio
async def test_history_uses_iso_range_and_averages_rows(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_fetch_json(url: str, **kwargs: Any) -> Any:
        captured["url"] = url
        return AGRI_LINK_ROWS

    monkeypatch.setattr(favoriot_client, "fetch_json", fake_fetch_json)

    result = await FavorIoTClient(settings).get_telemetry_history(
        DEVICE_ID,
        keys=["humidity"],
        start_ts_ms=1_792_114_886_539,
        end_ts_ms=1_792_114_890_241,
        interval_ms=60_000,
    )

    assert result["humidity"][0]["value"] == 73.5
    assert "created_from_to=%5B2026-10-16T01%3A41%3A26.539Z" in captured["url"]
    assert "order=asc" in captured["url"]


@pytest.mark.asyncio
async def test_command_uses_write_key(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_fetch_json(url: str, **kwargs: Any) -> Any:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["body"] = kwargs["body"]
        return {"statusCode": 201}

    monkeypatch.setattr(favoriot_client, "fetch_json", fake_fetch_json)

    await FavorIoTClient(settings).send_rpc_oneway(
        DEVICE_ID,
        "refill_on",
        {"pump": "tank"},
    )

    assert captured["url"].endswith("/streams")
    assert captured["headers"]["apikey"] == "write-key"
    assert captured["body"] == {
        "device_developer_id": DEVICE_ID,
        "data": {"command": "refill_on", "params": '{"pump": "tank"}'},
    }
