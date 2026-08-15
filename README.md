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

## How it works

Endpoint paths, HTTP methods, and field names are taken from FitBark's official v2
Postman API documentation and confirmed against a live account. A single
`GET /api/v2/dog_relations` call returns every owned dog's current snapshot in one
shot -- activity points, the goal in effect today, the active/play/rest minute
breakdown, and a `battery_level` field -- so a full update cycle is exactly one HTTP
request regardless of how many dogs are on the account. This isn't documented by
FitBark (the official docs show battery nowhere at all), but has been verified live.

The daily-goal percentage shown by `activity_goal_percent` is computed client-side
(`activity_value / daily_goal * 100`), since FitBark's own response doesn't include a
percentage directly.

### Hourly activity history (long-term statistics)

In addition to the current-snapshot sensors above, each dog's hourly activity is
imported into Home Assistant's long-term statistics (the same mechanism used by energy
and utility integrations), visible under **Developer Tools → Statistics** or in a
Statistics Graph card, as `FitBark: <dog name> Activity`. This uses
`POST /api/v2/activity_series` at `HOURLY` resolution, which FitBark caps to a 7-day
range per call, so a wide backfill (42 days on first setup) is split into consecutive
7-day windows automatically. After the initial backfill, it refreshes hourly on its own
schedule, independent of the 5-minute sensor polling. This isn't a regular entity --
external statistics aren't tied to one -- so it won't appear in Developer Tools →
States. The Developer Tools → Statistics page is a management table, not a chart, so
add a **Statistics Graph** card to a dashboard to actually see the history:

```yaml
type: statistics-graph
title: <Dog name> Activity
stat_types:
  - change
chart_type: bar
entities:
  - fitbark:<dog_slug_with_underscores>_activity
```

Use `change` (not `sum`) as the stat type -- `sum` is the raw cumulative running total
(an ever-climbing odometer, matching how HA stores the data internally), while `change`
shows the actual per-period amount as bars, which reads far more naturally for activity
data. Find your dog's exact statistic ID in Developer Tools → Statistics.

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

### Testing against a local dev Home Assistant instance

If you run `hass` locally (e.g. `hass -c ./dev_config`) rather than through
`my.home-assistant.io`-reachable remote access, the account-linking step will fail with
*"Invalid state. Is My Home Assistant configured to go to the right instance?"* This
happens because `default_config:` hard-depends on the `my` integration, which always
routes the OAuth callback through `my.home-assistant.io` -- and that service has no way
to bounce a browser back to a bare `localhost` instance it's never seen before.

Fix: don't use `default_config:` in your dev `configuration.yaml`; load only what you
need instead (this avoids pulling in `my`):

```yaml
frontend:
config:
http:
application_credentials:
```

Then also register the direct local callback with FitBark, alongside your other
redirect URIs (see the `curl` snippet above, adding
`http://localhost:8123/auth/external/callback` to the `redirect_uri` string).
