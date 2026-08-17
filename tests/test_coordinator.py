"""Tests for the FitBark DataUpdateCoordinator."""

from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.fitbark.api import FitBarkApiClient
from custom_components.fitbark.const import API_ROOT, CONF_SCAN_INTERVAL
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


async def test_snapshot_uses_activity_totals_not_dog_relations_field(
    hass: HomeAssistant, mock_config_entry, aioclient_mock
) -> None:
    """activity_points/activity_goal_percent come from a follow-up
    activity_totals("today") call, not dog_relations' own activity_value --
    regression test for that field not actually reflecting today's total
    (confirmed live: it can diverge wildly, e.g. 2333 vs. 7749 for the same
    dog on the same day). Only owned dogs get a follow-up call."""
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
    aioclient_mock.post(
        f"{API_ROOT}/api/v2/activity_totals", json={"activity_value": 150}
    )

    coordinator = await _build_coordinator(hass, mock_config_entry)
    await coordinator.async_refresh()

    assert set(coordinator.data) == {DOG_SLUG}
    # One dog_relations GET plus exactly one activity_totals POST -- the
    # FRIEND relation must not trigger its own follow-up call.
    assert len(aioclient_mock.mock_calls) == 2
    snapshot = coordinator.data[DOG_SLUG]
    assert snapshot.activity_points == 150
    assert snapshot.activity_goal_percent == 75.0
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
    aioclient_mock.post(
        f"{API_ROOT}/api/v2/activity_totals", json={"activity_value": 42}
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


async def test_midnight_triggers_refresh_regardless_of_scan_interval(
    hass: HomeAssistant, mock_config_entry, aioclient_mock
) -> None:
    """A refresh fires shortly after local midnight even with a long
    scan_interval -- regression test for activity_points_today (a "today"
    total, see api.py) showing yesterday's frozen value for hours after
    midnight when scan_interval is set high (e.g. the 12h max), since the
    next *scheduled* poll might not land until well into the new day."""
    await hass.config.async_set_time_zone("UTC")
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_SCAN_INTERVAL: 12}
    )
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/dog_relations",
        json={"dog_relations": [{"status": "OWNER", "dog": {"slug": DOG_SLUG, "name": "Fido"}}]},
    )
    aioclient_mock.post(f"{API_ROOT}/api/v2/activity_totals", json={"activity_value": 1})

    coordinator = await _build_coordinator(hass, mock_config_entry)
    await coordinator.async_refresh()
    assert len(aioclient_mock.mock_calls) == 2

    # Nothing else should poll again on its own -- scan_interval is 12h.
    next_midnight = (dt_util.utcnow() + timedelta(days=1)).replace(
        hour=0, minute=2, second=0, microsecond=0
    )
    async_fire_time_changed(hass, next_midnight)
    await hass.async_block_till_done()

    assert len(aioclient_mock.mock_calls) == 4
