"""DataUpdateCoordinator for FitBark."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FitBarkApiClient, FitBarkApiError, FitBarkAuthError, FitBarkDogSnapshot
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES, DOMAIN

_LOGGER = logging.getLogger(__name__)


class FitBarkDataUpdateCoordinator(DataUpdateCoordinator[dict[str, FitBarkDogSnapshot]]):
    """Coordinates fetching FitBark data for every dog on one account.

    A full update is a single GET /api/v2/dog_relations call -- FitBark
    embeds every dog's current snapshot (activity, goal, minutes, battery)
    directly in that response, confirmed live -- so there's no per-dog fan
    out here to isolate failures for.
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: FitBarkApiClient
    ) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=minutes),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, FitBarkDogSnapshot]:
        try:
            return await self.api.async_get_snapshots()
        except FitBarkAuthError as err:
            raise ConfigEntryAuthFailed from err
        except FitBarkApiError as err:
            raise UpdateFailed(f"Error fetching FitBark data: {err}") from err
