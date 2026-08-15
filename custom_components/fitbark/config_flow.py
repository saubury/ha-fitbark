"""Config flow for FitBark."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow

from .const import API_ROOT, DOMAIN

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
