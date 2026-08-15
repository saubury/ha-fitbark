# FitBark for Home Assistant

A HACS-installable custom integration that exposes [FitBark](https://www.fitbark.com/)
dog activity tracker data as Home Assistant sensors.

**Not affiliated with or endorsed by FitBark.**

## What this does (and doesn't)

Per dog, this integration exposes:

- Activity points earned today, and progress toward the daily goal
- Active / play / rest minute breakdown
- Collar battery level

It does **not** expose location, sleep score, or FitBark's computed health index --
these are not available through the public developer API.

## Known limitations

Endpoint paths, HTTP methods, and field names in this integration are taken from
FitBark's official v2 Postman API documentation. One important gap: **the official docs
do not document a collar battery field anywhere.** `api.py`'s `async_get_dog_info`
opportunistically probes the Get Dog Info response for a few plausible key names
(`battery_level`, `battery_percentage`, `battery`); if your account's real response
doesn't contain any of them, the battery sensor will simply stay `unavailable`. Please
open an issue with your dog's raw `GET /api/v2/dog/{dog_slug}` response (redact the
`slug`) if you find the real field name, so it can be added to the probe list.

The daily-goal percentage is computed client-side (today's `activity_totals` divided by
the goal in effect today from `daily_goal`), since FitBark's totals endpoint doesn't
return a percentage directly.

## Prerequisites (manual, one-time)

1. Register a developer app at the [FitBark developer portal](https://www.fitbark.com/dev/)
   to get a `client_id` and `client_secret`.
2. Register `https://my.home-assistant.io/redirect/oauth` as your app's redirect URI.
   This fixed URL works for any Home Assistant instance regardless of local network
   setup -- it's a Nabu Casa-hosted page that bounces your browser back to your own
   instance's `/auth/external/callback`. Register it by getting an app-level token and
   posting the URI, per FitBark's docs:

   ```bash
   TOKEN=$(curl -s -X POST -H "Content-Type: application/json" -d '{
     "grant_type": "client_credentials",
     "client_id": "YOUR_CLIENT_ID",
     "client_secret": "YOUR_CLIENT_SECRET",
     "scope": "fitbark_open_api_2745H78RVS"
   }' "https://app.fitbark.com/oauth/token" | jq -r .access_token)

   curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
     "redirect_uri": "https://my.home-assistant.io/redirect/oauth"
   }' "https://app.fitbark.com/api/v2/redirect_urls"
   ```

   Note this **replaces** any existing registered redirect URIs (they're one string,
   `\r`-separated) -- if you already use this app for something else with its own
   redirect URI, `GET` the current value first and include it in the new string.

## Installation

1. Add this repository to HACS as a custom repository (category: Integration).
2. Install "FitBark" via HACS, then restart Home Assistant.
3. Go to **Settings → Devices & Services → Application Credentials → Add**, choose
   FitBark, and enter your `client_id` / `client_secret` from the prerequisite step.
4. Go to **Settings → Devices & Services → Add Integration**, search for FitBark, and
   complete the browser-based FitBark login/authorize step.

Each dog on your account appears as a separate device with the sensors listed above.

## Development

```bash
pip install -r requirements_test.txt
pytest tests/
```
