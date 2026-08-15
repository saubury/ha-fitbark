"""Application credentials platform for FitBark."""

from __future__ import annotations

import logging

from homeassistant.components.application_credentials import AuthorizationServer
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .api import REDIRECT_URLS_SCOPE
from .const import API_ROOT, MY_HOME_ASSISTANT_REDIRECT, OAUTH2_AUTHORIZE, OAUTH2_TOKEN

_LOGGER = logging.getLogger(__name__)


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return FitBark's OAuth2 authorization server endpoints."""
    return AuthorizationServer(
        authorize_url=OAUTH2_AUTHORIZE,
        token_url=OAUTH2_TOKEN,
    )


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Extra text shown on the Add Application Credential dialog."""
    return {
        "redirect_url": MY_HOME_ASSISTANT_REDIRECT,
        "more_info_url": "https://www.fitbark.com/dev/",
    }


async def async_ensure_redirect_uri_registered(
    hass: HomeAssistant, client_id: str, client_secret: str
) -> None:
    """Best-effort: register our OAuth redirect URI with FitBark automatically.

    Per FitBark's docs, /oauth/authorize will reject a redirect_uri that
    isn't pre-registered for the app -- a fresh developer app only has
    FitBark's own default (urn:ietf:wg:oauth:2.0:oob) registered, not ours.
    Rather than requiring every user to run a manual curl command (as
    documented in the README as a fallback), do it here using an app-level
    client_credentials token, merging with whatever's already registered so
    we never clobber another integration reusing the same FitBark app.

    Called from config_flow.py right before generating the authorize URL.
    Never raises -- a failure here just means the subsequent authorize step
    fails with FitBark's own error, exactly as it would have without this
    automation, so this is purely additive.
    """
    websession = aiohttp_client.async_get_clientsession(hass)
    try:
        token_resp = await websession.post(
            OAUTH2_TOKEN,
            json={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": REDIRECT_URLS_SCOPE,
            },
        )
        token_resp.raise_for_status()
        app_token = (await token_resp.json())["access_token"]
        headers = {"Authorization": f"Bearer {app_token}"}

        current_resp = await websession.get(
            f"{API_ROOT}/api/v2/redirect_urls", headers=headers
        )
        current_resp.raise_for_status()
        current = (await current_resp.json()).get("redirect_uri") or ""
        registered = [uri for uri in current.split("\r") if uri]

        if MY_HOME_ASSISTANT_REDIRECT in registered:
            return

        registered.append(MY_HOME_ASSISTANT_REDIRECT)
        update_resp = await websession.post(
            f"{API_ROOT}/api/v2/redirect_urls",
            headers=headers,
            json={"redirect_uri": "\r".join(registered)},
        )
        update_resp.raise_for_status()
        _LOGGER.debug("Registered %s as a FitBark redirect URI", MY_HOME_ASSISTANT_REDIRECT)
    except Exception as err:  # noqa: BLE001 - best-effort, must never block the OAuth flow
        _LOGGER.warning(
            "Could not automatically register the FitBark redirect URI (%s); "
            "if authorization fails next, register it manually -- see the README",
            err,
        )
