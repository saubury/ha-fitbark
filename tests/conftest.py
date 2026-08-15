"""Fixtures for the FitBark integration tests."""

from __future__ import annotations

import json
import pathlib
import time

import pytest

from homeassistant.components.application_credentials import (
    ClientCredential,
    async_import_client_credential,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.fitbark.const import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fitbark.const import API_ROOT

from .const import ACCESS_TOKEN, CLIENT_ID, CLIENT_SECRET, USER_ID

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture from tests/fixtures/."""
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
async def setup_credentials(hass: HomeAssistant) -> None:
    """Register fake application credentials for the FitBark domain."""
    assert await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass,
        DOMAIN,
        ClientCredential(CLIENT_ID, CLIENT_SECRET),
        DOMAIN,
    )


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a MockConfigEntry with a valid, non-expired OAuth2 token."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=USER_ID,
        data={
            "auth_implementation": DOMAIN,
            "token": {
                "access_token": ACCESS_TOKEN,
                "refresh_token": "test-refresh-token",
                "expires_at": time.time() + 3600,
                "type": "Bearer",
            },
        },
    )


@pytest.fixture
def mock_fitbark_api(aioclient_mock):
    """Stub the single dog_relations call with a healthy one-dog account."""
    aioclient_mock.get(
        f"{API_ROOT}/api/v2/dog_relations", json=load_fixture("dogs_list.json")
    )
    return aioclient_mock
