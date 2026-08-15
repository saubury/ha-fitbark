"""Tests for FitBark integration setup/unload."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.fitbark.const import API_ROOT, DOMAIN

from .const import DOG_SLUG


async def test_setup_and_unload(
    recorder_mock,
    enable_custom_integrations,
    hass: HomeAssistant,
    setup_credentials,
    mock_config_entry,
    mock_fitbark_api,
) -> None:
    """A config entry with reachable endpoints loads and unloads cleanly."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED

    state = hass.states.get(f"sensor.fido_battery")
    assert state is not None

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_entry_not_ready_on_api_error(
    recorder_mock,
    enable_custom_integrations,
    hass: HomeAssistant,
    setup_credentials,
    mock_config_entry,
    aioclient_mock,
) -> None:
    """A network failure on first refresh leaves the entry in SETUP_RETRY."""
    aioclient_mock.get(f"{API_ROOT}/api/v2/dog_relations", status=500)
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
