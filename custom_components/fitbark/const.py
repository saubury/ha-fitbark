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

# How often to import hourly activity_series data into HA's long-term
# statistics (see statistics.py). Hourly data only changes once an hour at
# most, so this runs on its own, slower schedule decoupled from the main
# entity-polling coordinator above.
STATISTICS_SCAN_INTERVAL = timedelta(hours=1)

ATTRIBUTION = "Data provided by FitBark"
MANUFACTURER = "FitBark"
