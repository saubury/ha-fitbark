"""DataUpdateCoordinator for FitBark."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FitBarkApiClient, FitBarkAuthError, FitBarkApiError, FitBarkDogSnapshot
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class FitBarkDataUpdateCoordinator(DataUpdateCoordinator[dict[str, FitBarkDogSnapshot]]):
    """Coordinates fetching FitBark data for every dog on one account."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: FitBarkApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, FitBarkDogSnapshot]:
        try:
            dogs = await self.api.async_get_dogs()
        except FitBarkAuthError as err:
            raise ConfigEntryAuthFailed from err
        except FitBarkApiError as err:
            raise UpdateFailed(f"Error fetching FitBark dog list: {err}") from err

        snapshots: dict[str, FitBarkDogSnapshot] = {}
        errors = 0

        for dog in dogs:
            try:
                snapshots[dog.slug] = await self.api.async_get_dog_snapshot(dog)
            except FitBarkAuthError as err:
                raise ConfigEntryAuthFailed from err
            except FitBarkApiError as err:
                errors += 1
                _LOGGER.warning(
                    "Failed to update FitBark data for dog %s: %s", dog.slug, err
                )
                previous = self.data.get(dog.slug) if self.data else None
                if previous is not None:
                    snapshots[dog.slug] = previous

        if dogs and errors == len(dogs):
            raise UpdateFailed("Failed to update any dog on this FitBark account")

        return snapshots
