"""Application credentials platform for FitBark."""

from homeassistant.components.application_credentials import AuthorizationServer
from homeassistant.core import HomeAssistant

from .const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return FitBark's OAuth2 authorization server endpoints."""
    return AuthorizationServer(
        authorize_url=OAUTH2_AUTHORIZE,
        token_url=OAUTH2_TOKEN,
    )


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Extra text shown on the Add Application Credential dialog.

    Per FitBark's official API docs, the redirect URI must be pre-registered
    via POST https://app.fitbark.com/api/v2/redirect_urls, authenticated with
    an app-level (not per-user) token obtained via a client_credentials grant
    using the special scope "fitbark_open_api_2745H78RVS" -- see
    REDIRECT_URLS_SCOPE in api.py. This is a one-time manual step (e.g. via
    curl) using your client_id/client_secret, done before adding this
    integration. Register https://my.home-assistant.io/redirect/oauth as
    that URI -- it works for any Home Assistant instance regardless of local
    network setup.
    """
    return {
        "redirect_url": "https://my.home-assistant.io/redirect/oauth",
        "more_info_url": "https://www.fitbark.com/dev/",
    }
