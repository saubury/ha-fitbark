"""API client for FitBark.

Endpoint paths, HTTP methods, and response field names below are taken
directly from FitBark's official Postman API documentation (v2 public API,
supplied by the developer as FitBarkAPI.pdf) and confirmed against a live
account. GET /api/v2/dog_relations embeds most fields a dashboard needs per
dog -- the goal in effect today, the active/play/rest minute breakdown, and
(though undocumented) a `battery_level` field. Its `activity_value` field is
NOT one of them, despite an earlier version of this client assuming it was
"today's activity points": confirmed live, it diverges wildly from the
purpose-built activity_totals(from=today, to=today) call for the same dog on
the same day (e.g. 2333 vs. 7749) -- it appears to be some other, undocumented
figure, not a daily total. So a full account update is dog_relations plus one
activity_totals call per dog (see async_get_snapshots), not a single call.
The other per-dog endpoints (`async_get_dog_info`, `async_get_daily_goal`,
`async_get_time_breakdown`) are kept for potential future use (e.g. custom
date ranges, historical charts) but are not on the coordinator's hot path.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.util import dt as dt_util

from .const import API_ROOT

_LOGGER = logging.getLogger(__name__)

# Owners can see full history; "friend"/"follower" relations only see the
# last 30 days and are explicitly out of scope for v1.
_OWNER_STATUS = "OWNER"

# Client-credentials scope required to manage OAuth2 redirect URIs -- not
# used for per-user data calls, only for the one-time redirect_urls setup.
REDIRECT_URLS_SCOPE = "fitbark_open_api_2745H78RVS"

# Confirmed live against a real account: present directly on both the
# GET /api/v2/dog_relations and GET /api/v2/dog/{slug} responses, even
# though FitBark's official docs don't document a battery field at all.
_BATTERY_KEY = "battery_level"


class FitBarkApiError(Exception):
    """Generic error talking to the FitBark API."""


class FitBarkAuthError(FitBarkApiError):
    """Raised on 401/403 responses -- token invalid or revoked."""


class FitBarkRateLimitError(FitBarkApiError):
    """Raised on 429 responses."""


@dataclass
class FitBarkDog:
    """A single dog owned by the account."""

    slug: str
    name: str
    breed: str | None = None
    tzname: str | None = None


@dataclass
class FitBarkDogSnapshot:
    """Normalized per-dog data for one coordinator update cycle."""

    dog: FitBarkDog
    activity_points: float | None = None
    activity_goal_percent: float | None = None
    daily_goal: float | None = None
    minutes_active: float | None = None
    minutes_play: float | None = None
    minutes_rest: float | None = None
    battery_level: int | None = None


def _as_float(value: Any) -> float | None:
    """FitBark returns some numeric fields as strings (e.g. "6711.27...")."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dog_snapshot(raw: dict) -> FitBarkDogSnapshot:
    """Build a snapshot directly from one dog_relations `dog` object.

    activity_points/activity_goal_percent are deliberately left unset here --
    dog_relations' `activity_value` field does not represent today's total
    (see this module's docstring), so the caller (async_get_snapshots) fills
    those in from a dedicated activity_totals("today") call instead. daily_goal
    is carried through so that follow-up call can compute the percentage.
    """
    breed = None
    if isinstance(raw.get("breed1"), dict):
        breed = raw["breed1"].get("name")

    dog = FitBarkDog(
        slug=raw["slug"],
        name=raw.get("name", raw["slug"]),
        breed=breed,
        tzname=raw.get("tzname"),
    )

    battery = raw.get(_BATTERY_KEY)
    if battery is None:
        _LOGGER.debug(
            "No '%s' field found for dog %s; FitBark's public API does not "
            "document a battery field",
            _BATTERY_KEY,
            dog.slug,
        )

    return FitBarkDogSnapshot(
        dog=dog,
        daily_goal=_as_float(raw.get("daily_goal")),
        minutes_active=_as_float(raw.get("min_active")),
        minutes_play=_as_float(raw.get("min_play")),
        minutes_rest=_as_float(raw.get("min_rest")),
        battery_level=battery,
    )


class FitBarkApiClient:
    """Thin async client for the FitBark REST API."""

    def __init__(
        self,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
        websession: ClientSession,
    ) -> None:
        self._oauth_session = oauth_session
        self._websession = websession

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        await self._oauth_session.async_ensure_token_valid()
        token = self._oauth_session.token["access_token"]
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"

        try:
            resp = await self._websession.request(
                method, url, headers=headers, **kwargs
            )
        except ClientError as err:
            raise FitBarkApiError(f"Error communicating with FitBark: {err}") from err

        if resp.status in (401, 403):
            raise FitBarkAuthError(f"FitBark auth failed ({resp.status})")
        if resp.status == 429:
            raise FitBarkRateLimitError("FitBark rate limit exceeded")
        try:
            resp.raise_for_status()
        except ClientResponseError as err:
            raise FitBarkApiError(f"FitBark API error: {err}") from err

        text = await resp.text()
        if not text:
            return {}
        return json.loads(text)

    async def async_get_user(self) -> dict:
        """GET /api/v2/user - the logged-in user's profile."""
        data = await self._request("GET", f"{API_ROOT}/api/v2/user")
        return data.get("user", data)

    async def async_get_snapshots(self) -> dict[str, FitBarkDogSnapshot]:
        """Fetch and normalize every owned dog's current data.

        GET /api/v2/dog_relations returns each related dog's goal, minute
        breakdown, and battery inline, but not a usable "today's activity
        points" figure (see this module's docstring) -- that needs one
        activity_totals(from=today, to=today) call per dog, fetched
        sequentially (rate-limit-conservative, consistent with the rest of
        this integration). Only OWNER relations are kept; "friend"/"follower"
        dogs are out of scope for v1.
        """
        data = await self._request("GET", f"{API_ROOT}/api/v2/dog_relations")
        snapshots: dict[str, FitBarkDogSnapshot] = {}
        for relation in data.get("dog_relations", []):
            if relation.get("status") != _OWNER_STATUS:
                continue
            raw = relation.get("dog", {})
            try:
                snapshot = _parse_dog_snapshot(raw)
            except (KeyError, TypeError) as err:
                _LOGGER.warning("Skipping malformed dog record %r: %s", raw, err)
                continue
            snapshots[snapshot.dog.slug] = snapshot

        for snapshot in snapshots.values():
            await self._async_fill_todays_activity(snapshot)

        return snapshots

    async def _async_fill_todays_activity(self, snapshot: FitBarkDogSnapshot) -> None:
        """Fill in activity_points/activity_goal_percent for one dog.

        "Today" is resolved in the dog's own local time (matching
        statistics.py's handling of dog.tzname), not the HA server's --
        otherwise a dog several hours off UTC could get yesterday's or
        tomorrow's total near midnight.
        """
        dog = snapshot.dog
        tz = (
            (await dt_util.async_get_time_zone(dog.tzname))
            if dog.tzname
            else dt_util.DEFAULT_TIME_ZONE
        )
        today = dt_util.now(tz).date().isoformat()
        snapshot.activity_points = await self.async_get_activity_total(
            dog.slug, today, today
        )
        if snapshot.activity_points is not None and snapshot.daily_goal:
            snapshot.activity_goal_percent = round(
                snapshot.activity_points / snapshot.daily_goal * 100, 1
            )

    async def async_get_dog_info(self, dog_slug: str) -> FitBarkDogSnapshot:
        """GET /api/v2/dog/{dog_slug} - one dog's full current snapshot.

        Not used on the coordinator's normal update path (async_get_snapshots
        covers every dog) but kept as a standalone building block. Like
        async_get_snapshots, activity_points/activity_goal_percent are left
        unset here -- callers needing them should follow up with
        async_get_activity_total.
        """
        data = await self._request("GET", f"{API_ROOT}/api/v2/dog/{dog_slug}")
        return _parse_dog_snapshot(data.get("dog", data))

    async def async_get_activity_total(
        self, dog_slug: str, date_from: str, date_to: str
    ) -> float | None:
        """POST /api/v2/activity_totals - summed BarkPoints over a date range."""
        data = await self._request(
            "POST",
            f"{API_ROOT}/api/v2/activity_totals",
            json={"dog": {"slug": dog_slug, "from": date_from, "to": date_to}},
        )
        return _as_float(data.get("activity_value"))

    async def async_get_daily_goal(self, dog_slug: str, today: str) -> float | None:
        """GET /api/v2/daily_goal/{dog_slug} - the goal in effect on `today`.

        FitBark returns a list of goals, each one in effect from its `date`
        until the next entry's date. Pick the most recent entry whose date
        is not after `today`; fall back to the earliest entry if all are in
        the future.
        """
        data = await self._request(
            "GET", f"{API_ROOT}/api/v2/daily_goal/{dog_slug}"
        )
        goals = sorted(
            data.get("daily_goals", []), key=lambda g: g.get("date", "")
        )
        if not goals:
            return None
        applicable = [g for g in goals if g.get("date", "") <= today]
        return _as_float((applicable[-1] if applicable else goals[0]).get("goal"))

    async def async_get_time_breakdown(
        self, dog_slug: str, date_from: str, date_to: str
    ) -> dict:
        """POST /api/v2/time_breakdown - minutes active/play/rest over a date range."""
        data = await self._request(
            "POST",
            f"{API_ROOT}/api/v2/time_breakdown",
            json={"dog": {"slug": dog_slug, "from": date_from, "to": date_to}},
        )
        return data.get("activity_level", {})

    async def async_get_activity_series(
        self, dog_slug: str, date_from: str, date_to: str, resolution: str
    ) -> list[dict]:
        """POST /api/v2/activity_series - historical series data.

        FitBark caps the range per call: 42 days at DAILY resolution, 7 days
        at HOURLY. Each record's `date` is "YYYY-MM-DD" for DAILY or
        "YYYY-MM-DD HH:MM:SS" for HOURLY, in the dog's local time (see
        FitBarkDog.tzname) -- callers requesting a wider range must chunk
        into multiple calls themselves (see statistics.py).
        """
        data = await self._request(
            "POST",
            f"{API_ROOT}/api/v2/activity_series",
            json={
                "activity_series": {
                    "slug": dog_slug,
                    "from": date_from,
                    "to": date_to,
                    "resolution": resolution,
                }
            },
        )
        return data.get("activity_series", {}).get("records", [])
