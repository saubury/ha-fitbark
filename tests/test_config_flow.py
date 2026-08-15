"""Tests for the FitBark config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from custom_components.fitbark.const import (
    API_ROOT,
    DOMAIN,
    MY_HOME_ASSISTANT_REDIRECT,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)

from .conftest import load_fixture
from .const import ACCESS_TOKEN, CLIENT_ID


async def test_full_flow(
    recorder_mock,
    enable_custom_integrations,
    hass: HomeAssistant,
    hass_client_no_auth,
    aioclient_mock,
    current_request_with_host,
    setup_credentials,
) -> None:
    """A fresh OAuth2 flow creates a config entry keyed on the FitBark user id."""
    # Registration of our redirect URI happens automatically, before the
    # authorize URL is even generated -- see application_credentials.py. This
    # single OAUTH2_TOKEN mock covers both that app-level client_credentials
    # call and the later user authorization_code exchange further down (only
    # the first-registered mock for a given URL/method ever matches, so a
    # second registration for the same endpoint would silently be ignored).
    aioclient_mock.post(
        OAUTH2_TOKEN,
        json={
            "access_token": ACCESS_TOKEN,
            "refresh_token": "mock-refresh-token",
            "type": "Bearer",
            "expires_in": 60,
        },
    )
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/redirect_urls",
        json={"redirect_uri": "urn:ietf:wg:oauth:2.0:oob"},
    )
    aioclient_mock.post(f"{API_ROOT}/api/v2/redirect_urls", json={})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    redirect_registration_calls = [
        call
        for call in aioclient_mock.mock_calls
        if call[0] == "POST" and str(call[1]) == f"{API_ROOT}/api/v2/redirect_urls"
    ]
    assert len(redirect_registration_calls) == 1
    assert MY_HOME_ASSISTANT_REDIRECT in redirect_registration_calls[0][2]["redirect_uri"]

    state = config_entry_oauth2_flow._encode_jwt(
        hass,
        {
            "flow_id": result["flow_id"],
            "redirect_uri": "https://example.com/auth/external/callback",
        },
    )
    assert result["type"] == "external"
    assert result["url"].startswith(OAUTH2_AUTHORIZE)
    assert f"client_id={CLIENT_ID}" in result["url"]

    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200

    aioclient_mock.get(f"{API_ROOT}/api/v2/user", json=load_fixture("user.json"))

    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] == "create_entry"
    assert result["title"] == "Test User"
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].unique_id == "9999"


async def test_duplicate_account_aborts(
    recorder_mock,
    enable_custom_integrations,
    hass: HomeAssistant,
    hass_client_no_auth,
    aioclient_mock,
    current_request_with_host,
    setup_credentials,
    mock_config_entry,
) -> None:
    """Re-adding the same FitBark account aborts as already_configured."""
    mock_config_entry.add_to_hass(hass)

    aioclient_mock.post(
        OAUTH2_TOKEN,
        json={
            "access_token": ACCESS_TOKEN,
            "refresh_token": "mock-refresh-token",
            "type": "Bearer",
            "expires_in": 60,
        },
    )
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/redirect_urls",
        json={"redirect_uri": "urn:ietf:wg:oauth:2.0:oob"},
    )
    aioclient_mock.post(f"{API_ROOT}/api/v2/redirect_urls", json={})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    state = config_entry_oauth2_flow._encode_jwt(
        hass,
        {
            "flow_id": result["flow_id"],
            "redirect_uri": "https://example.com/auth/external/callback",
        },
    )
    client = await hass_client_no_auth()
    await client.get(f"/auth/external/callback?code=abcd&state={state}")
    aioclient_mock.get(f"{API_ROOT}/api/v2/user", json=load_fixture("user.json"))

    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
