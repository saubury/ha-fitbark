"""Tests for the FitBark DataUpdateCoordinator."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.fitbark.api import FitBarkApiClient
from custom_components.fitbark.const import API_ROOT
from custom_components.fitbark.coordinator import FitBarkDataUpdateCoordinator

from .const import DOG_SLUG


class _FakeOAuth2Session:
    """Minimal stand-in exposing the interface FitBarkApiClient needs."""

    token = {"access_token": "test-access-token"}

    async def async_ensure_token_valid(self) -> None:
        return None


async def _build_coordinator(hass: HomeAssistant, entry) -> FitBarkDataUpdateCoordinator:
    api = FitBarkApiClient(_FakeOAuth2Session(), aiohttp_client.async_get_clientsession(hass))
    return FitBarkDataUpdateCoordinator(hass, entry, api)


def _mock_healthy_dog(aioclient_mock, slug: str) -> None:
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/dog/{slug}",
        json={"dog": {"slug": slug, "name": slug, "breed1": {"name": "Mixed"}}},
    )
    aioclient_mock.post(
        f"{API_ROOT}/api/v2/activity_totals", json={"activity_value": 100}
    )
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/daily_goal/{slug}",
        json={"daily_goals": [{"goal": 200, "date": "2020-01-01"}]},
    )
    aioclient_mock.post(
        f"{API_ROOT}/api/v2/time_breakdown",
        json={"activity_level": {"min_active": 10, "min_play": 5, "min_rest": 100}},
    )


async def test_multi_dog_partial_failure_keeps_previous_snapshot(
    hass: HomeAssistant, mock_config_entry, aioclient_mock
) -> None:
    """One dog failing to update doesn't blank out a previously-good snapshot."""
    mock_config_entry.add_to_hass(hass)
    other_slug = "rex-5678"

    aioclient_mock.get(
        f"{API_ROOT}/api/v2/dog_relations",
        json={
            "dog_relations": [
                {"status": "OWNER", "dog": {"slug": DOG_SLUG, "name": "Fido"}},
                {"status": "OWNER", "dog": {"slug": other_slug, "name": "Rex"}},
            ]
        },
    )
    _mock_healthy_dog(aioclient_mock, DOG_SLUG)
    _mock_healthy_dog(aioclient_mock, other_slug)

    coordinator = await _build_coordinator(hass, mock_config_entry)
    await coordinator.async_refresh()
    assert set(coordinator.data) == {DOG_SLUG, other_slug}
    first_cycle_rex = coordinator.data[other_slug]

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/dog_relations",
        json={
            "dog_relations": [
                {"status": "OWNER", "dog": {"slug": DOG_SLUG, "name": "Fido"}},
                {"status": "OWNER", "dog": {"slug": other_slug, "name": "Rex"}},
            ]
        },
    )
    _mock_healthy_dog(aioclient_mock, DOG_SLUG)
    aioclient_mock.get(f"{API_ROOT}/api/v2/dog/{other_slug}", status=500)

    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert coordinator.data[DOG_SLUG].minutes_active == 10
    assert coordinator.data[other_slug] is first_cycle_rex


async def test_all_dogs_failing_raises_update_failed(
    hass: HomeAssistant, mock_config_entry, aioclient_mock
) -> None:
    """If every dog fails to update, the coordinator update fails outright."""
    mock_config_entry.add_to_hass(hass)
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/dog_relations",
        json={"dog_relations": [{"status": "OWNER", "dog": {"slug": DOG_SLUG, "name": "Fido"}}]},
    )
    aioclient_mock.get(f"{API_ROOT}/api/v2/dog/{DOG_SLUG}", status=500)

    coordinator = await _build_coordinator(hass, mock_config_entry)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
