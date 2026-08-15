"""API client for FitBark.

Endpoint paths, HTTP methods, and response field names below are taken
directly from FitBark's official Postman API documentation (v2 public API),
supplied by the developer as FitBarkAPI.pdf. Two items remain genuinely
unconfirmed even against that document and are called out explicitly where
relevant: a per-dog `breed` field on the dog-list response, and any collar
battery field at all (the official docs do not document one -- see
`async_get_dog_info`).
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
import logging
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from homeassistant.helpers import config_entry_oauth2_flow

from .const import API_ROOT

_LOGGER = logging.getLogger(__name__)

# Owners can see full history; "friend"/"follower" relations only see the
# last 30 days and are explicitly out of scope for v1.
_OWNER_STATUS = "OWNER"

# Client-credentials scope required to manage OAuth2 redirect URIs -- not
# used for per-user data calls, only for the one-time redirect_urls setup.
REDIRECT_URLS_SCOPE = "fitbark_open_api_2745H78RVS"

# Likely key names for a collar battery indicator on the Get Dog Info
# response. NOT part of FitBark's documented schema -- the official docs do
# not show a battery field at all. Probed defensively; if none of these are
# present, async_get_dog_info returns None for battery and callers should
# treat the battery sensor as unavailable rather than erroring.
_BATTERY_KEYS = ("battery_level", "battery_percentage", "battery")


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


@dataclass
class FitBarkDogSnapshot:
    """Normalized per-dog data for one coordinator update cycle."""

    dog: FitBarkDog
    activity_points: float | None = None
    activity_goal_percent: float | None = None
    minutes_active: float | None = None
    minutes_play: float | None = None
    minutes_rest: float | None = None
    battery_level: int | None = None


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

    async def async_get_dogs(self) -> list[FitBarkDog]:
        """List dogs owned (not just followed/"friended") by the account.

        GET /api/v2/dog_relations returns every dog related to the user with
        a `status` of OWNER or FRIEND; only OWNER entries are kept.
        """
        data = await self._request("GET", f"{API_ROOT}/api/v2/dog_relations")
        dogs = []
        for relation in data.get("dog_relations", []):
            if relation.get("status") != _OWNER_STATUS:
                continue
            raw = relation.get("dog", {})
            dogs.append(FitBarkDog(slug=raw["slug"], name=raw.get("name", raw["slug"])))
        return dogs

    async def async_get_dog_info(self, dog_slug: str) -> dict:
        """GET /api/v2/dog/{dog_slug} - name, breed, and (opportunistically) battery.

        Breed is nested under `breed1.name`. No battery field is documented
        by FitBark; `battery_level` on the returned dict is a best-effort
        probe across a few plausible key names and may be None.
        """
        data = await self._request("GET", f"{API_ROOT}/api/v2/dog/{dog_slug}")
        dog = data.get("dog", data)

        breed = None
        if isinstance(dog.get("breed1"), dict):
            breed = dog["breed1"].get("name")

        battery = None
        for key in _BATTERY_KEYS:
            if key in dog:
                battery = dog[key]
                break
        if battery is None:
            _LOGGER.debug(
                "No battery field found on dog %s info response (checked %s); "
                "FitBark's public API does not document one",
                dog_slug,
                _BATTERY_KEYS,
            )

        return {"breed": breed, "battery_level": battery}

    async def async_get_activity_total(
        self, dog_slug: str, date_from: str, date_to: str
    ) -> float | None:
        """POST /api/v2/activity_totals - summed BarkPoints over a date range."""
        data = await self._request(
            "POST",
            f"{API_ROOT}/api/v2/activity_totals",
            json={"dog": {"slug": dog_slug, "from": date_from, "to": date_to}},
        )
        return data.get("activity_value")

    async def async_get_daily_goal(
        self, dog_slug: str, today: str
    ) -> float | None:
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
        return (applicable[-1] if applicable else goals[0]).get("goal")

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

    async def async_get_dog_snapshot(self, dog: FitBarkDog) -> FitBarkDogSnapshot:
        """Fetch and normalize all per-dog data for one update cycle."""
        today = dt.date.today().isoformat()

        info = await self.async_get_dog_info(dog.slug)
        activity_points = await self.async_get_activity_total(dog.slug, today, today)
        goal = await self.async_get_daily_goal(dog.slug, today)
        breakdown = await self.async_get_time_breakdown(dog.slug, today, today)

        goal_percent = None
        if activity_points is not None and goal:
            goal_percent = round(activity_points / goal * 100, 1)

        dog.breed = info["breed"]
        return FitBarkDogSnapshot(
            dog=dog,
            activity_points=activity_points,
            activity_goal_percent=goal_percent,
            minutes_active=breakdown.get("min_active"),
            minutes_play=breakdown.get("min_play"),
            minutes_rest=breakdown.get("min_rest"),
            battery_level=info["battery_level"],
        )
