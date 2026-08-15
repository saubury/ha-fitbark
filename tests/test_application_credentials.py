"""Tests for automatic FitBark redirect-URI registration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.fitbark.application_credentials import (
    async_ensure_redirect_uri_registered,
)
from custom_components.fitbark.const import API_ROOT, MY_HOME_ASSISTANT_REDIRECT, OAUTH2_TOKEN

from .const import CLIENT_ID, CLIENT_SECRET


async def test_registers_when_not_already_present(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """A fresh app with only FitBark's default gets our redirect appended."""
    aioclient_mock.post(OAUTH2_TOKEN, json={"access_token": "app-token"})
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/redirect_urls",
        json={"redirect_uri": "urn:ietf:wg:oauth:2.0:oob"},
    )
    aioclient_mock.post(f"{API_ROOT}/api/v2/redirect_urls", json={})

    await async_ensure_redirect_uri_registered(hass, CLIENT_ID, CLIENT_SECRET)

    post_calls = [
        call
        for call in aioclient_mock.mock_calls
        if call[0] == "POST" and str(call[1]) == f"{API_ROOT}/api/v2/redirect_urls"
    ]
    assert len(post_calls) == 1
    body = post_calls[0][2]
    assert body["redirect_uri"] == f"urn:ietf:wg:oauth:2.0:oob\r{MY_HOME_ASSISTANT_REDIRECT}"


async def test_noop_when_already_registered(hass: HomeAssistant, aioclient_mock) -> None:
    """Nothing is POSTed if our redirect URI is already registered."""
    aioclient_mock.post(OAUTH2_TOKEN, json={"access_token": "app-token"})
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/redirect_urls",
        json={"redirect_uri": f"urn:ietf:wg:oauth:2.0:oob\r{MY_HOME_ASSISTANT_REDIRECT}"},
    )

    await async_ensure_redirect_uri_registered(hass, CLIENT_ID, CLIENT_SECRET)

    post_calls = [
        call
        for call in aioclient_mock.mock_calls
        if call[0] == "POST" and str(call[1]) == f"{API_ROOT}/api/v2/redirect_urls"
    ]
    assert not post_calls


async def test_failure_is_swallowed(hass: HomeAssistant, aioclient_mock) -> None:
    """A failed registration attempt never raises -- best-effort only."""
    aioclient_mock.post(OAUTH2_TOKEN, status=500)

    # Must not raise.
    await async_ensure_redirect_uri_registered(hass, CLIENT_ID, CLIENT_SECRET)
