"""Tests for the FitBark config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from custom_components.fitbark.const import DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN, API_ROOT

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
    assert result["type"] == "external"
    assert result["url"].startswith(OAUTH2_AUTHORIZE)
    assert f"client_id={CLIENT_ID}" in result["url"]

    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200

    aioclient_mock.post(
        OAUTH2_TOKEN,
        json={
            "refresh_token": "mock-refresh-token",
            "access_token": ACCESS_TOKEN,
            "type": "Bearer",
            "expires_in": 60,
        },
    )
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

    aioclient_mock.post(
        OAUTH2_TOKEN,
        json={
            "refresh_token": "mock-refresh-token",
            "access_token": ACCESS_TOKEN,
            "type": "Bearer",
            "expires_in": 60,
        },
    )
    aioclient_mock.get(f"{API_ROOT}/api/v2/user", json=load_fixture("user.json"))

    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
