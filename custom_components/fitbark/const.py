"""Constants for the FitBark integration."""

from datetime import timedelta

DOMAIN = "fitbark"

OAUTH2_AUTHORIZE = "https://app.fitbark.com/oauth/authorize"
OAUTH2_TOKEN = "https://app.fitbark.com/oauth/token"
API_ROOT = "https://app.fitbark.com"

# A full update is a single GET /api/v2/dog_relations call regardless of dog
# count (confirmed live -- see api.py), but the underlying data itself only
# changes as often as the collar syncs (periodic, not continuous) -- polling
# much faster than that just re-fetches unchanged values. User-configurable
# via the options flow; this is only the fallback default.
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL_MINUTES = 20
MIN_SCAN_INTERVAL_MINUTES = 5
MAX_SCAN_INTERVAL_MINUTES = 120

# How often to import hourly activity_series data into HA's long-term
# statistics (see statistics.py). Hourly data only changes once an hour at
# most, so this runs on its own, slower schedule decoupled from the main
# entity-polling coordinator above.
STATISTICS_SCAN_INTERVAL = timedelta(hours=1)

ATTRIBUTION = "Data provided by FitBark"
MANUFACTURER = "FitBark"
