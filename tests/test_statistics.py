"""Tests for FitBark hourly activity -> HA long-term statistics import."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import get_last_statistics
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.util import dt as dt_util

from custom_components.fitbark.api import FitBarkApiClient, FitBarkDog
from custom_components.fitbark.const import API_ROOT
from custom_components.fitbark.statistics import (
    _iter_hourly_windows,
    _parse_hourly_timestamp,
    async_import_dog_activity_statistics,
    statistic_id_for_dog,
)

from .const import DOG_SLUG


class _FakeOAuth2Session:
    token = {"access_token": "test-access-token"}

    async def async_ensure_token_valid(self) -> None:
        return None


def _build_client(hass: HomeAssistant) -> FitBarkApiClient:
    return FitBarkApiClient(
        _FakeOAuth2Session(), aiohttp_client.async_get_clientsession(hass)
    )


def test_iter_hourly_windows_chunks_wide_range() -> None:
    """A 20-day range is chunked into <=7-day windows with no overlap."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 20, 23, 0, tzinfo=timezone.utc)
    windows = list(_iter_hourly_windows(start, end))
    assert windows == [
        ("2024-01-01", "2024-01-07"),
        ("2024-01-08", "2024-01-14"),
        ("2024-01-15", "2024-01-20"),
    ]


def test_parse_hourly_timestamp() -> None:
    """Valid FitBark HOURLY timestamps parse; malformed ones return None."""
    tz = timezone.utc
    parsed = _parse_hourly_timestamp("2024-01-01 15:00:00", tz)
    assert parsed == datetime(2024, 1, 1, 15, 0, tzinfo=tz)
    assert _parse_hourly_timestamp("not-a-date", tz) is None


async def test_first_time_import_backfills_and_dedups_across_windows(
    recorder_mock, hass: HomeAssistant, aioclient_mock
) -> None:
    """A fresh statistic backfills, and repeated identical records across
    chunked windows collapse into a single point rather than duplicating."""
    dog = FitBarkDog(slug=DOG_SLUG, name="Fido", tzname="UTC")
    aioclient_mock.post(
        f"{API_ROOT}/api/v2/activity_series",
        json={
            "activity_series": {
                "records": [
                    {"date": "2024-06-01 10:00:00", "activity_value": 50},
                    {"date": "2024-06-01 11:00:00", "activity_value": 30},
                ]
            }
        },
    )

    await async_import_dog_activity_statistics(hass, _build_client(hass), dog)
    await hass.async_block_till_done()
    await async_recorder_block_till_done(hass)

    statistic_id = statistic_id_for_dog(DOG_SLUG)
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, False, {"sum", "state"}
    )
    assert last[statistic_id][0]["sum"] == pytest.approx(80.0)
    assert last[statistic_id][0]["state"] == pytest.approx(30.0)


async def test_second_run_only_adds_new_hours(
    recorder_mock, hass: HomeAssistant, aioclient_mock
) -> None:
    """A later import only appends hours after the last recorded point."""
    dog = FitBarkDog(slug=DOG_SLUG, name="Fido", tzname="UTC")
    aioclient_mock.post(
        f"{API_ROOT}/api/v2/activity_series",
        json={
            "activity_series": {
                "records": [{"date": "2024-06-01 10:00:00", "activity_value": 50}]
            }
        },
    )
    await async_import_dog_activity_statistics(hass, _build_client(hass), dog)
    await hass.async_block_till_done()
    await async_recorder_block_till_done(hass)

    aioclient_mock.clear_requests()
    aioclient_mock.post(
        f"{API_ROOT}/api/v2/activity_series",
        json={
            "activity_series": {
                "records": [
                    {"date": "2024-06-01 10:00:00", "activity_value": 999},
                    {"date": "2024-06-01 11:00:00", "activity_value": 20},
                ]
            }
        },
    )
    await async_import_dog_activity_statistics(hass, _build_client(hass), dog)
    await hass.async_block_till_done()
    await async_recorder_block_till_done(hass)

    statistic_id = statistic_id_for_dog(DOG_SLUG)
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, False, {"sum", "state"}
    )
    assert last[statistic_id][0]["state"] == pytest.approx(20.0)
    assert last[statistic_id][0]["sum"] == pytest.approx(70.0)


async def async_recorder_block_till_done(hass: HomeAssistant) -> None:
    """Wait for the recorder's queued import job to finish processing."""
    await get_instance(hass).async_block_till_done()
