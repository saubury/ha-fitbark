"""Constants for the FitBark integration."""

DOMAIN = "fitbark"

OAUTH2_AUTHORIZE = "https://app.fitbark.com/oauth/authorize"
OAUTH2_TOKEN = "https://app.fitbark.com/oauth/token"
API_ROOT = "https://app.fitbark.com"

# The redirect URI HA sends to FitBark's authorize endpoint for any instance
# that isn't a bare local dev box (see README's "Testing against a local dev
# Home Assistant instance" for the direct-callback exception). Must be
# registered against the user's FitBark app before authorize will succeed --
# see application_credentials.py's async_ensure_redirect_uri_registered,
# which does this automatically.
MY_HOME_ASSISTANT_REDIRECT = "https://my.home-assistant.io/redirect/oauth"

# A full update is a single GET /api/v2/dog_relations call regardless of dog
# count (confirmed live -- see api.py), but the underlying data itself only
# changes as often as the collar syncs (periodic, not continuous) -- polling
# much faster than that just re-fetches unchanged values. User-configurable
# via the options flow (in hours, matching CONF_STATISTICS_SCAN_INTERVAL
# below); these are only the fallback default/bounds. Quarter-hour steps are
# allowed (unlike the statistics interval) since sub-hour polling still has
# some marginal value here, just diminishing.
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL_HOURS = 1
MIN_SCAN_INTERVAL_HOURS = 0.25
MAX_SCAN_INTERVAL_HOURS = 12

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
