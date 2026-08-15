"""Tests for the FitBark sensor platform."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.fitbark.sensor import SENSOR_DESCRIPTIONS


async def test_sensor_entities_created_per_dog(
    hass: HomeAssistant, setup_credentials, mock_config_entry, mock_fitbark_api
) -> None:
    """One entity per SENSOR_DESCRIPTIONS entry is created for each dog."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry_states = [
        state for state in hass.states.async_all("sensor") if state.entity_id.startswith("sensor.fido_")
    ]
    assert len(entity_registry_states) == len(SENSOR_DESCRIPTIONS)


async def test_battery_sensor_state_matches_fixture(
    hass: HomeAssistant, setup_credentials, mock_config_entry, mock_fitbark_api
) -> None:
    """The battery sensor reports the value from the mocked API response."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.fido_battery")
    assert state is not None
    assert state.state == "76"
