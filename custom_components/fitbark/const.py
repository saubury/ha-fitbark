"""Constants for the FitBark integration."""

DOMAIN = "fitbark"

OAUTH2_AUTHORIZE = "https://app.fitbark.com/oauth/authorize"
OAUTH2_TOKEN = "https://app.fitbark.com/oauth/token"
API_ROOT = "https://app.fitbark.com"

# A full update is a single GET /api/v2/dog_relations call regardless of dog
# count (confirmed live -- see api.py), but the underlying data itself only
# changes as often as the collar syncs (periodic, not continuous) -- polling
# much faster than that just re-fetches unchanged values. User-configurable
# via the options flow; these are only the fallback default/bounds.
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL_MINUTES = 60
MIN_SCAN_INTERVAL_MINUTES = 5
MAX_SCAN_INTERVAL_MINUTES = 720

# How often to import hourly activity_series data into HA's long-term
# statistics (see statistics.py). Hourly data only changes once an hour at
# most, so 1 hour is the natural floor -- going lower has no benefit since
# FitBark's finest tracked resolution is hourly. Also user-configurable.
CONF_STATISTICS_SCAN_INTERVAL = "statistics_scan_interval"
DEFAULT_STATISTICS_SCAN_INTERVAL_HOURS = 1
MIN_STATISTICS_SCAN_INTERVAL_HOURS = 1
MAX_STATISTICS_SCAN_INTERVAL_HOURS = 24

ATTRIBUTION = "Data provided by FitBark"
MANUFACTURER = "FitBark"
