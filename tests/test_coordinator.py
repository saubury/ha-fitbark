"""Tests for the FitBark DataUpdateCoordinator."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
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


async def test_single_call_returns_all_dogs(
    hass: HomeAssistant, mock_config_entry, aioclient_mock
) -> None:
    """One dog_relations call is enough to populate every owned dog."""
    mock_config_entry.add_to_hass(hass)
    other_slug = "rex-5678"
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/dog_relations",
        json={
            "dog_relations": [
                {
                    "status": "OWNER",
                    "dog": {
                        "slug": DOG_SLUG,
                        "name": "Fido",
                        "activity_value": "100",
                        "daily_goal": "200",
                        "min_active": 10,
                        "min_play": 5,
                        "min_rest": 100,
                        "battery_level": 80,
                    },
                },
                {
                    "status": "FRIEND",
                    "dog": {"slug": other_slug, "name": "NotMine"},
                },
            ]
        },
    )

    coordinator = await _build_coordinator(hass, mock_config_entry)
    await coordinator.async_refresh()

    assert set(coordinator.data) == {DOG_SLUG}
    assert len(aioclient_mock.mock_calls) == 1
    snapshot = coordinator.data[DOG_SLUG]
    assert snapshot.activity_points == 100
    assert snapshot.activity_goal_percent == 50.0
    assert snapshot.battery_level == 80


async def test_malformed_dog_record_is_skipped(
    hass: HomeAssistant, mock_config_entry, aioclient_mock
) -> None:
    """A malformed record for one dog doesn't blank out the others."""
    mock_config_entry.add_to_hass(hass)
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/dog_relations",
        json={
            "dog_relations": [
                {"status": "OWNER", "dog": {"name": "Missing slug entirely"}},
                {"status": "OWNER", "dog": {"slug": DOG_SLUG, "name": "Fido"}},
            ]
        },
    )

    coordinator = await _build_coordinator(hass, mock_config_entry)
    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert set(coordinator.data) == {DOG_SLUG}


async def test_api_failure_raises_update_failed(
    hass: HomeAssistant, mock_config_entry, aioclient_mock
) -> None:
    """A failed dog_relations call fails the whole update."""
    mock_config_entry.add_to_hass(hass)
    aioclient_mock.get(f"{API_ROOT}/api/v2/dog_relations", status=500)

    coordinator = await _build_coordinator(hass, mock_config_entry)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_auth_failure_raises_config_entry_auth_failed(
    hass: HomeAssistant, mock_config_entry, aioclient_mock
) -> None:
    """A 401 from FitBark surfaces as a reauth-triggering error."""
    mock_config_entry.add_to_hass(hass)
    aioclient_mock.get(f"{API_ROOT}/api/v2/dog_relations", status=401)

    coordinator = await _build_coordinator(hass, mock_config_entry)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
