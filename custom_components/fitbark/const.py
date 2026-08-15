"""Constants for the FitBark integration."""

from datetime import timedelta

DOMAIN = "fitbark"

OAUTH2_AUTHORIZE = "https://app.fitbark.com/oauth/authorize"
OAUTH2_TOKEN = "https://app.fitbark.com/oauth/token"
API_ROOT = "https://app.fitbark.com"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=20)

ATTRIBUTION = "Data provided by FitBark"
MANUFACTURER = "FitBark"
