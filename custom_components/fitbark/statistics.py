"""Import FitBark hourly activity into Home Assistant's long-term statistics.

activity_series returns a time series over a date range rather than a single
current value, so it doesn't fit the entity/coordinator model the rest of
this integration uses -- it's imported as HA "external statistics" instead
(the same mechanism core integrations like opower use for utility data),
which HA renders in the Statistics/History UI without needing a live entity.

FitBark caps a single activity_series call to 7 days at HOURLY resolution,
so a wide backfill is chunked into consecutive <=7-day windows and each is
fetched sequentially (rate-limit-conservative, consistent with the rest of
this integration).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
import logging

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
from homeassistant.util import dt as dt_util

from .api import FitBarkApiClient, FitBarkDog
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# FitBark's own cap for a single HOURLY-resolution activity_series call.
_MAX_HOURLY_WINDOW_DAYS = 7

# How far back to backfill the first time a dog's statistic is created.
_INITIAL_BACKFILL_DAYS = 42

_RESOLUTION_HOURLY = "HOURLY"


def statistic_id_for_dog(dog_slug: str) -> str:
    """Build the external statistic_id for a dog's hourly activity."""
    safe = dog_slug.replace("-", "_").lower()
    return f"{DOMAIN}:{safe}_activity"


def _iter_hourly_windows(start: datetime, end: datetime) -> Iterator[tuple[str, str]]:
    """Yield (from, to) local-date strings, each within FitBark's 7-day cap."""
    max_span = timedelta(days=_MAX_HOURLY_WINDOW_DAYS - 1)
    cursor = start
    while cursor.date() <= end.date():
        window_end = min(cursor + max_span, end)
        yield cursor.date().isoformat(), window_end.date().isoformat()
        cursor = window_end + timedelta(days=1)


def _parse_hourly_timestamp(date_str: str, tz) -> datetime | None:
    """FitBark HOURLY records use 'YYYY-MM-DD HH:MM:SS' in the dog's local tz."""
    try:
        naive = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        _LOGGER.debug("Unrecognized activity_series timestamp: %s", date_str)
        return None
    return naive.replace(tzinfo=tz)


async def _async_fetch_hourly_records(
    api: FitBarkApiClient, dog_slug: str, start: datetime, end: datetime, tz
) -> list[tuple[datetime, float]]:
    """Fetch activity_series(HOURLY) across as many <=7-day windows as needed."""
    records: dict[datetime, float] = {}
    for date_from, date_to in _iter_hourly_windows(start, end):
        raw_records = await api.async_get_activity_series(
            dog_slug, date_from, date_to, _RESOLUTION_HOURLY
        )
        for raw in raw_records:
            hour_start = _parse_hourly_timestamp(raw.get("date", ""), tz)
            if hour_start is None:
                continue
            try:
                records[hour_start] = float(raw.get("activity_value") or 0)
            except (TypeError, ValueError):
                continue
    return sorted(records.items())


async def async_import_dog_activity_statistics(
    hass: HomeAssistant, api: FitBarkApiClient, dog: FitBarkDog
) -> None:
    """Fetch and import one dog's hourly activity as HA long-term statistics."""
    statistic_id = statistic_id_for_dog(dog.slug)
    metadata = StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name=f"{dog.name} Activity",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_class=None,
        unit_of_measurement="BarkPoints",
    )

    tz = (await dt_util.async_get_time_zone(dog.tzname)) if dog.tzname else dt_util.DEFAULT_TIME_ZONE
    now = dt_util.now(tz)

    last_stat = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, False, {"sum"}
    )

    if not last_stat:
        _LOGGER.debug("First-time statistics import for %s", statistic_id)
        start = now - timedelta(days=_INITIAL_BACKFILL_DAYS)
        running_sum = 0.0
        after_ts: float | None = None
    else:
        row = last_stat[statistic_id][0]
        after_ts = row["start"]
        start = dt_util.utc_from_timestamp(after_ts)
        running_sum = float(row.get("sum") or 0.0)

    try:
        records = await _async_fetch_hourly_records(api, dog.slug, start, now, tz)
    except Exception as err:  # noqa: BLE001 - best-effort: must never block sensor setup
        _LOGGER.warning(
            "Failed to fetch activity_series for %s: %s", dog.slug, err
        )
        return

    stats: list[StatisticData] = []
    for hour_start, activity_value in records:
        if after_ts is not None and hour_start.timestamp() <= after_ts:
            continue
        running_sum += activity_value
        stats.append(
            StatisticData(start=hour_start, state=activity_value, sum=running_sum)
        )

    if not stats:
        _LOGGER.debug("No new hourly activity for %s", statistic_id)
        return

    _LOGGER.debug("Adding %d hourly statistics for %s", len(stats), statistic_id)
    async_add_external_statistics(hass, metadata, stats)
