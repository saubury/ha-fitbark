"""Tests for the standalone (non-coordinator-path) FitBarkApiClient methods."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from custom_components.fitbark.api import FitBarkApiClient
from custom_components.fitbark.const import API_ROOT

from .conftest import load_fixture
from .const import DOG_SLUG


class _FakeOAuth2Session:
    token = {"access_token": "test-access-token"}

    async def async_ensure_token_valid(self) -> None:
        return None


def _build_client(hass: HomeAssistant) -> FitBarkApiClient:
    return FitBarkApiClient(
        _FakeOAuth2Session(), aiohttp_client.async_get_clientsession(hass)
    )


async def test_async_get_dog_info(hass: HomeAssistant, aioclient_mock) -> None:
    """GET /api/v2/dog/{slug} normalizes into a FitBarkDogSnapshot."""
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/dog/{DOG_SLUG}", json=load_fixture("dog_info.json")
    )
    snapshot = await _build_client(hass).async_get_dog_info(DOG_SLUG)
    assert snapshot.dog.slug == DOG_SLUG
    assert snapshot.dog.breed == "Labrador"
    assert snapshot.battery_level == 76


async def test_async_get_activity_total(hass: HomeAssistant, aioclient_mock) -> None:
    """POST /api/v2/activity_totals returns the numeric activity_value."""
    aioclient_mock.post(
        f"{API_ROOT}/api/v2/activity_totals", json=load_fixture("activity_total.json")
    )
    value = await _build_client(hass).async_get_activity_total(
        DOG_SLUG, "2024-01-01", "2024-01-01"
    )
    assert value == 452


async def test_async_get_daily_goal_picks_applicable_entry(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """The goal entry with the latest date <= today is selected."""
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/daily_goal/{DOG_SLUG}",
        json={
            "daily_goals": [
                {"goal": 300, "date": "2024-01-01"},
                {"goal": 500, "date": "2024-06-01"},
                {"goal": 900, "date": "2099-01-01"},
            ]
        },
    )
    goal = await _build_client(hass).async_get_daily_goal(DOG_SLUG, "2024-07-15")
    assert goal == 500


async def test_async_get_time_breakdown(hass: HomeAssistant, aioclient_mock) -> None:
    """POST /api/v2/time_breakdown unwraps the activity_level object."""
    aioclient_mock.post(
        f"{API_ROOT}/api/v2/time_breakdown", json=load_fixture("time_breakdown.json")
    )
    breakdown = await _build_client(hass).async_get_time_breakdown(
        DOG_SLUG, "2024-01-01", "2024-01-01"
    )
    assert breakdown == {"min_active": 63, "min_play": 21, "min_rest": 540}
