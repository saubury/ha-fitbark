"""DataUpdateCoordinator for FitBark."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FitBarkApiClient, FitBarkApiError, FitBarkAuthError, FitBarkDogSnapshot
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class FitBarkDataUpdateCoordinator(DataUpdateCoordinator[dict[str, FitBarkDogSnapshot]]):
    """Coordinates fetching FitBark data for every dog on one account.

    A full update is GET /api/v2/dog_relations (goal, minutes, battery for
    every dog in one call) plus one POST /api/v2/activity_totals call per dog
    for today's activity points -- dog_relations' own activity_value field
    doesn't reflect today's total (see api.py). All of this happens inside
    FitBarkApiClient.async_get_snapshots, so there's still no per-dog fan out
    here to isolate failures for -- a failure on any one dog's activity_totals
    call fails the whole update, same as a dog_relations failure always did.
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: FitBarkApiClient
    ) -> None:
        hours = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(hours=hours),
        )
        self.api = api

        # scan_interval can be as long as 12h, which would otherwise leave
        # activity_points_today (see api.py) showing yesterday's frozen
        # total for hours after midnight -- the next *scheduled* poll may
        # not land until well into the new day. Force an extra refresh
        # shortly after midnight regardless of scan_interval so "today"
        # catches up promptly no matter how the interval is configured.
        # This fires on HA's local midnight, a practical approximation --
        # a dog whose own tz (see api.py's per-dog "today" resolution)
        # differs from HA's could still see a short lag, bounded by
        # scan_interval.
        entry.async_on_unload(
            async_track_time_change(
                hass, self._async_midnight_refresh, hour=0, minute=2, second=0
            )
        )

    async def _async_midnight_refresh(self, _now=None) -> None:
        """Force a refresh shortly after local midnight (see __init__)."""
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, FitBarkDogSnapshot]:
        try:
            return await self.api.async_get_snapshots()
        except FitBarkAuthError as err:
            raise ConfigEntryAuthFailed from err
        except FitBarkApiError as err:
            raise UpdateFailed(f"Error fetching FitBark data: {err}") from err
