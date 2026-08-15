"""Tests for the FitBark options flow (polling intervals)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant

from custom_components.fitbark.const import CONF_SCAN_INTERVAL, CONF_STATISTICS_SCAN_INTERVAL


async def test_options_flow_updates_coordinator_interval(
    recorder_mock,
    enable_custom_integrations,
    hass: HomeAssistant,
    setup_credentials,
    mock_config_entry,
    mock_fitbark_api,
) -> None:
    """The two-step options flow updates the coordinator's polling interval."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Default interval before any options are set.
    assert mock_config_entry.runtime_data.update_interval == timedelta(hours=1)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_SCAN_INTERVAL: 4}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "statistics"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_STATISTICS_SCAN_INTERVAL: 6}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()

    assert mock_config_entry.options[CONF_SCAN_INTERVAL] == 4
    assert mock_config_entry.options[CONF_STATISTICS_SCAN_INTERVAL] == 6
    assert mock_config_entry.runtime_data.update_interval == timedelta(hours=4)
