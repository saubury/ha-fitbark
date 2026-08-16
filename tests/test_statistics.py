"""Tests for FitBark hourly activity -> HA long-term statistics import."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.util import dt as dt_util

from custom_components.fitbark.api import FitBarkApiClient, FitBarkDog
from custom_components.fitbark.const import API_ROOT, DOMAIN
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


async def test_minute_breakdown_metrics_are_imported(
    recorder_mock, hass: HomeAssistant, aioclient_mock
) -> None:
    """min_play/min_active/min_rest are imported as their own statistics."""
    dog = FitBarkDog(slug=DOG_SLUG, name="Fido", tzname="UTC")
    aioclient_mock.post(
        f"{API_ROOT}/api/v2/activity_series",
        json={
            "activity_series": {
                "records": [
                    {
                        "date": "2024-06-01 10:00:00",
                        "activity_value": 50,
                        "min_play": 5,
                        "min_active": 20,
                        "min_rest": 35,
                    }
                ]
            }
        },
    )

    await async_import_dog_activity_statistics(hass, _build_client(hass), dog)
    await hass.async_block_till_done()
    await async_recorder_block_till_done(hass)

    for metric_key, expected in (
        ("minutes_play", 5.0),
        ("minutes_active", 20.0),
        ("minutes_rest", 35.0),
    ):
        statistic_id = statistic_id_for_dog(DOG_SLUG, metric_key)
        last = await get_instance(hass).async_add_executor_job(
            get_last_statistics, hass, 1, statistic_id, False, {"sum", "state"}
        )
        assert last[statistic_id][0]["state"] == pytest.approx(expected)
        assert last[statistic_id][0]["sum"] == pytest.approx(expected)


async def test_new_metric_backfills_fully_despite_sibling_having_history(
    recorder_mock, hass: HomeAssistant, aioclient_mock
) -> None:
    """A metric with no prior history gets the full backfill, even if a
    sibling metric (e.g. from before this metric existed) already has
    recent history -- regression test for a bug where the shared fetch
    window was bounded by the metric that already had data, silently
    starving metrics that had none."""
    dog = FitBarkDog(slug=DOG_SLUG, name="Fido", tzname="UTC")
    activity_statistic_id = statistic_id_for_dog(DOG_SLUG, "activity")

    # Seed only the "activity" statistic with a single recent point, as if
    # it were imported hours ago while "minutes_play" never has been.
    recent_start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    async_add_external_statistics(
        hass,
        StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name="Fido Activity",
            source=DOMAIN,
            statistic_id=activity_statistic_id,
            unit_class=None,
            unit_of_measurement="BarkPoints",
        ),
        [StatisticData(start=recent_start, state=10.0, sum=10.0)],
    )
    await hass.async_block_till_done()
    await async_recorder_block_till_done(hass)

    # Two records: one old (well outside a "since recent_start" window) and
    # one at recent_start itself.
    old_date = (recent_start - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    aioclient_mock.post(
        f"{API_ROOT}/api/v2/activity_series",
        json={
            "activity_series": {
                "records": [
                    {
                        "date": old_date,
                        "activity_value": 1,
                        "min_play": 7,
                        "min_active": 0,
                        "min_rest": 0,
                    },
                    {
                        "date": recent_start.strftime("%Y-%m-%d %H:%M:%S"),
                        "activity_value": 2,
                        "min_play": 9,
                        "min_active": 0,
                        "min_rest": 0,
                    },
                ]
            }
        },
    )

    await async_import_dog_activity_statistics(hass, _build_client(hass), dog)
    await hass.async_block_till_done()
    await async_recorder_block_till_done(hass)

    play_statistic_id = statistic_id_for_dog(DOG_SLUG, "minutes_play")
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 2, play_statistic_id, False, {"sum", "state"}
    )
    # Both the old and the recent record must have been imported for the
    # previously-history-less metric -- sum should reflect both (7 + 9).
    assert last[play_statistic_id][0]["sum"] == pytest.approx(16.0)


async def test_resume_run_uses_dog_local_date_not_utc_date(
    recorder_mock, hass: HomeAssistant, aioclient_mock
) -> None:
    """A resumed (non-first-time) import computes its activity_series
    date_from in the dog's local timezone, not UTC -- regression test for a
    bug where get_last_statistics' bare UTC epoch timestamp was used as-is
    without converting to the dog's tz, unlike the first-run backfill path."""
    tzname = "Etc/GMT-10"  # fixed UTC+10, no DST, so the test is deterministic
    dog = FitBarkDog(slug=DOG_SLUG, name="Fido", tzname=tzname)

    # 2024-06-02 00:00:00 local (Etc/GMT-10) == 2024-06-01 14:00:00 UTC, so a
    # naive UTC-date read of this timestamp would incorrectly say "2024-06-01".
    # (Statistic start times must be exactly on the hour.)
    seed_local = datetime(2024, 6, 2, 0, 0, tzinfo=ZoneInfo(tzname))
    # All four metrics need a resume point, or "any metric has no history"
    # forces the full 42-day backfill path instead of the resume path this
    # test is targeting.
    for metric_key in ("activity", "minutes_play", "minutes_active", "minutes_rest"):
        async_add_external_statistics(
            hass,
            StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name=f"Fido {metric_key}",
                source=DOMAIN,
                statistic_id=statistic_id_for_dog(DOG_SLUG, metric_key),
                unit_class=None,
                unit_of_measurement="BarkPoints",
            ),
            [StatisticData(start=seed_local, state=1.0, sum=1.0)],
        )
    await hass.async_block_till_done()
    await async_recorder_block_till_done(hass)

    aioclient_mock.post(
        f"{API_ROOT}/api/v2/activity_series", json={"activity_series": {"records": []}}
    )

    await async_import_dog_activity_statistics(hass, _build_client(hass), dog)

    request_bodies = [
        call[2]
        for call in aioclient_mock.mock_calls
        if call[0] == "POST" and str(call[1]) == f"{API_ROOT}/api/v2/activity_series"
    ]
    assert request_bodies
    assert request_bodies[0]["activity_series"]["from"] == "2024-06-02"


async def async_recorder_block_till_done(hass: HomeAssistant) -> None:
    """Wait for the recorder's queued import job to finish processing."""
    await get_instance(hass).async_block_till_done()
