"""The FitBark integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow

from .api import FitBarkApiClient
from .const import DOMAIN
from .coordinator import FitBarkDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type FitBarkConfigEntry = ConfigEntry[FitBarkDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: FitBarkConfigEntry) -> bool:
    """Set up FitBark from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )
    oauth_session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    api = FitBarkApiClient(oauth_session, aiohttp_client.async_get_clientsession(hass))

    coordinator = FitBarkDataUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FitBarkConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
