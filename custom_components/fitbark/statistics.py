"""Import FitBark hourly activity into Home Assistant's long-term statistics.

activity_series returns a time series over a date range rather than a single
current value, so it doesn't fit the entity/coordinator model the rest of
this integration uses -- it's imported as HA "external statistics" instead
(the same mechanism core integrations like opower use for utility data),
which HA renders in the Statistics/History UI without needing a live entity.

Each HOURLY record carries four metrics (confirmed live): activity_value,
min_play, min_active, min_rest. All four are imported as separate external
statistics from a single shared fetch per dog, one per metric, so the
minute breakdown (e.g. "what proportion of this hour was spent resting")
is available in the same Statistics Graph card style as the headline
activity number.

FitBark caps a single activity_series call to 7 days at HOURLY resolution,
so a wide backfill is chunked into consecutive <=7-day windows and each is
fetched sequentially (rate-limit-conservative, consistent with the rest of
this integration).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
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

# How far back to backfill the first time a dog's statistics are created.
_INITIAL_BACKFILL_DAYS = 42

_RESOLUTION_HOURLY = "HOURLY"


@dataclass(frozen=True)
class _HourlyRecord:
    """One hour's worth of activity_series data for a dog."""

    start: datetime
    activity_value: float
    min_play: float
    min_active: float
    min_rest: float


@dataclass(frozen=True)
class _Metric:
    """One statistic derived from each _HourlyRecord."""

    key: str
    label: str
    unit: str | None
    value_fn: Callable[[_HourlyRecord], float]


_METRICS: tuple[_Metric, ...] = (
    _Metric("activity", "Activity", "BarkPoints", lambda r: r.activity_value),
    _Metric("minutes_play", "Minutes Played", "min", lambda r: r.min_play),
    _Metric("minutes_active", "Minutes Active", "min", lambda r: r.min_active),
    _Metric("minutes_rest", "Minutes Rested", "min", lambda r: r.min_rest),
)


def statistic_id_for_dog(dog_slug: str, metric_key: str = "activity") -> str:
    """Build the external statistic_id for one of a dog's hourly metrics."""
    safe = dog_slug.replace("-", "_").lower()
    return f"{DOMAIN}:{safe}_{metric_key}"


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


def _as_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


async def _async_fetch_hourly_records(
    api: FitBarkApiClient, dog_slug: str, start: datetime, end: datetime, tz
) -> list[_HourlyRecord]:
    """Fetch activity_series(HOURLY) across as many <=7-day windows as needed."""
    records: dict[datetime, _HourlyRecord] = {}
    for date_from, date_to in _iter_hourly_windows(start, end):
        raw_records = await api.async_get_activity_series(
            dog_slug, date_from, date_to, _RESOLUTION_HOURLY
        )
        for raw in raw_records:
            hour_start = _parse_hourly_timestamp(raw.get("date", ""), tz)
            if hour_start is None:
                continue
            records[hour_start] = _HourlyRecord(
                start=hour_start,
                activity_value=_as_float(raw.get("activity_value")),
                min_play=_as_float(raw.get("min_play")),
                min_active=_as_float(raw.get("min_active")),
                min_rest=_as_float(raw.get("min_rest")),
            )
    return sorted(records.values(), key=lambda r: r.start)


async def async_import_dog_activity_statistics(
    hass: HomeAssistant, api: FitBarkApiClient, dog: FitBarkDog
) -> None:
    """Fetch and import one dog's hourly metrics as HA long-term statistics."""
    tz = (
        (await dt_util.async_get_time_zone(dog.tzname))
        if dog.tzname
        else dt_util.DEFAULT_TIME_ZONE
    )
    now = dt_util.now(tz)

    # Each metric tracks its own resume point/running sum independently
    # (a metric added after another already has history won't share one),
    # but they're all fetched from a single shared activity_series call
    # spanning whichever metric is furthest behind.
    resume_points: dict[str, tuple[float | None, float]] = {}
    for metric in _METRICS:
        statistic_id = statistic_id_for_dog(dog.slug, metric.key)
        last_stat = await get_instance(hass).async_add_executor_job(
            get_last_statistics, hass, 1, statistic_id, False, {"sum"}
        )
        if not last_stat:
            resume_points[metric.key] = (None, 0.0)
        else:
            row = last_stat[statistic_id][0]
            resume_points[metric.key] = (row["start"], float(row.get("sum") or 0.0))

    resume_timestamps = [ts for ts, _ in resume_points.values()]
    if any(ts is None for ts in resume_timestamps):
        # At least one metric (e.g. one added after the others already had
        # history) has never been imported -- it needs the full backfill
        # window, not just "since whichever metric already has data".
        start = now - timedelta(days=_INITIAL_BACKFILL_DAYS)
    else:
        start = dt_util.utc_from_timestamp(min(resume_timestamps))

    try:
        records = await _async_fetch_hourly_records(api, dog.slug, start, now, tz)
    except Exception as err:  # noqa: BLE001 - best-effort: must never block sensor setup
        _LOGGER.warning("Failed to fetch activity_series for %s: %s", dog.slug, err)
        return

    if not records:
        _LOGGER.debug("No hourly activity records for %s", dog.slug)
        return

    for metric in _METRICS:
        after_ts, running_sum = resume_points[metric.key]
        stats: list[StatisticData] = []
        for record in records:
            if after_ts is not None and record.start.timestamp() <= after_ts:
                continue
            value = metric.value_fn(record)
            running_sum += value
            stats.append(
                StatisticData(start=record.start, state=value, sum=running_sum)
            )

        if not stats:
            continue

        statistic_id = statistic_id_for_dog(dog.slug, metric.key)
        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"{dog.name} {metric.label}",
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_class=None,
            unit_of_measurement=metric.unit,
        )
        _LOGGER.debug("Adding %d hourly statistics for %s", len(stats), statistic_id)
        async_add_external_statistics(hass, metadata, stats)
