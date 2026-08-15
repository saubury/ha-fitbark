"""Constants for the FitBark integration."""

from datetime import timedelta

DOMAIN = "fitbark"

OAUTH2_AUTHORIZE = "https://app.fitbark.com/oauth/authorize"
OAUTH2_TOKEN = "https://app.fitbark.com/oauth/token"
API_ROOT = "https://app.fitbark.com"

# A full update is a single GET /api/v2/dog_relations call regardless of dog
# count (confirmed live -- see api.py), so this can be more aggressive than
# the original N+1-calls-per-cycle design called for. FitBark's device sync
# cadence is itself periodic, so sub-5-minute polling mostly wouldn't return
# new data anyway. Still conservative relative to undocumented rate limits.
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

ATTRIBUTION = "Data provided by FitBark"
MANUFACTURER = "FitBark"
