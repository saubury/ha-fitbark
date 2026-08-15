"""Config flow for FitBark."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    API_ROOT,
    CONF_SCAN_INTERVAL,
    CONF_STATISTICS_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_STATISTICS_SCAN_INTERVAL_HOURS,
    DOMAIN,
    MAX_SCAN_INTERVAL_HOURS,
    MAX_STATISTICS_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
    MIN_STATISTICS_SCAN_INTERVAL_HOURS,
)

_LOGGER = logging.getLogger(__name__)


class FitBarkOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle FitBark OAuth2 authentication."""

    DOMAIN = DOMAIN

    @property
    def logger(self) -> logging.Logger:
        """Return the logger."""
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra query params for the authorize URL.

        FitBark's /oauth/authorize (per official docs) only needs
        response_type/client_id/redirect_uri, all already supplied by the
        base OAuth2 flow -- no extra scope parameter required.
        """
        return {}

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create the config entry, deduping on the FitBark account."""
        token = data["token"]["access_token"]
        websession = aiohttp_client.async_get_clientsession(self.hass)
        resp = await websession.get(
            f"{API_ROOT}/api/v2/user",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        payload = await resp.json()
        user = payload.get("user", payload)
        user_id = str(user.get("slug"))

        await self.async_set_unique_id(user_id)
        if self.source != "reauth":
            self._abort_if_unique_id_configured()
        else:
            self._abort_if_unique_id_mismatch()

        title = user.get("name") or user.get("username") or "FitBark"

        if self.source == "reauth":
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data=data
            )
        return self.async_create_entry(title=title, data=data)

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication triggered by ConfigEntryAuthFailed."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth, then run the standard OAuth2 implementation picker."""
        return await self.async_step_pick_implementation(
            user_input={"implementation": self._get_reauth_entry().data["auth_implementation"]}
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FitBarkOptionsFlowHandler:
        """Return the options flow for adjusting the polling interval."""
        return FitBarkOptionsFlowHandler()


class FitBarkOptionsFlowHandler(OptionsFlowWithReload):
    """Handle FitBark options -- the sensor and statistics polling intervals.

    Two sequential steps rather than one combined form, so each interval gets
    its own title/description positioned directly above its field (HA's
    plain schema-based options form only supports one shared description for
    the whole step, not per-field).
    """

    _scan_interval: float | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: sensor polling interval."""
        if user_input is not None:
            self._scan_interval = user_input[CONF_SCAN_INTERVAL]
            return await self.async_step_statistics()

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL_HOURS
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_HOURS,
                        max=MAX_SCAN_INTERVAL_HOURS,
                        step=0.25,
                        unit_of_measurement="h",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                options_schema, self.config_entry.options
            ),
        )

    async def async_step_statistics(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: statistics import interval."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: self._scan_interval,
                    CONF_STATISTICS_SCAN_INTERVAL: user_input[
                        CONF_STATISTICS_SCAN_INTERVAL
                    ],
                }
            )

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_STATISTICS_SCAN_INTERVAL,
                    default=DEFAULT_STATISTICS_SCAN_INTERVAL_HOURS,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_STATISTICS_SCAN_INTERVAL_HOURS,
                        max=MAX_STATISTICS_SCAN_INTERVAL_HOURS,
                        step=1,
                        unit_of_measurement="h",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="statistics",
            data_schema=self.add_suggested_values_to_schema(
                options_schema, self.config_entry.options
            ),
        )
