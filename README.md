# ProjectFitBit

A self-hosted personal health dashboard for Fitbit devices, built on the Google Health API. It syncs your sleep, heart rate, steps and exercise data into a local SQLite database and renders an interactive dashboard with Streamlit. No third-party services, no cloud storage: your health data stays on your machine.

## Architecture

```
Fitbit device --> Fitbit app (phone) --> Google cloud
                                             |
                                   Google Health API (v4)
                                             |
                        ingest.py (cron, every 15 min) --> SQLite
                                             |
                                   app.py (Streamlit dashboard)
```

- `auth.py` runs once and performs the OAuth 2.0 flow against Google, storing a refresh token locally.
- `ingest.py` runs periodically (cron), refreshes the access token automatically and downloads new data points incrementally into `projectfitbit.db`.
- `app.py` is the Streamlit dashboard that reads the database. It never talks to the API.

## Requirements

- A Fitbit device linked to a Google account.
- Python 3.10 or later (3.12 tested) on Linux.
- A Google Cloud project (free tier is enough).

## Step 1: Google Cloud setup

1. Go to https://console.cloud.google.com and create a new project.
2. Open "APIs & Services" > "Library", search for **Google Health API** and click **Enable**. Make sure you enable it in the same project where you will create the credentials.
3. Open "APIs & Services" > "OAuth consent screen". Choose **External**, keep the app in **Testing** mode and add your own Google account as a test user. All Google Health API scopes are classified as Restricted; keeping the app in Testing mode lets you use it with your own account without going through Google's verification review.
4. Open "APIs & Services" > "Credentials" > "Create credentials" > **OAuth client ID**. Select application type **Desktop app**. Download the JSON file from the confirmation dialog.
5. Save the downloaded file as `client_secret.json` in the project root and restrict its permissions:

```bash
chmod 600 client_secret.json
```

Important: do not confuse the OAuth client with a service account. Service account keys (files containing a `private_key` field) will not work here, because the Health API requires user consent.

## Step 2: Installation

```bash
git clone <your-repo-url>
cd ProjectFitBit
python3 -m venv venv
source venv/bin/activate
pip install google-auth google-auth-oauthlib streamlit plotly pandas
```

## Step 3: One-time authorization

```bash
python3 auth.py
```

A browser window opens. Sign in with the Google account linked to your Fitbit, accept the three read-only scopes (sleep, activity and fitness, health metrics and measurements). Because the app is in Testing mode, Google shows an "unverified app" warning: click "Advanced" and continue.

On success the script writes `tokens.json` (permissions 600) containing the refresh token. You should see `Refresh token present: True`. If it prints `False`, revoke the app's access at https://myaccount.google.com/permissions and run it again.

## Step 4: Data ingestion and the database

```bash
python3 ingest.py
```

The first run backfills the last 30 days. The script creates `projectfitbit.db` with three tables:

- `raw_points`: every data point exactly as returned by the API (JSON payload), keyed by data type and timestamp. Sleep sessions keep their full stage breakdown here.
- `cardio`: a flat `(timestamp, bpm)` table for fast heart rate queries.
- `estado`: the last synced timestamp per data type, used for incremental syncs.

Subsequent runs only fetch data newer than the last sync, with a 60 minute overlap window; duplicate points are absorbed by `INSERT OR REPLACE`.

Note on data types: sample types (`heart-rate`) and daily types (`daily-resting-heart-rate`) support server-side time filters. Session types (`sleep`, `exercise`) reject filters on this API version, so they are downloaded in full on each run; their volume (one or a few points per day) makes this negligible.

Schedule it with cron every 15 minutes:

```bash
crontab -e
```

```
*/15 * * * * cd /path/to/ProjectFitBit && ./venv/bin/python3 ingest.py >> ingest.log 2>&1
```

## Step 5: Dashboard

```bash
streamlit run app.py
```

Open http://localhost:8501. The dashboard has four tabs:

- **Sleep**: night selector, per-stage metrics (deep, REM, light, awake) with color-coded cards, a restorative sleep percentage, an interactive hypnogram and a nightly duration trend.
- **Heart rate**: intraday chart with a 1-30 day range slider, average/min/max, and the resting heart rate trend.
- **Activity**: daily step totals and a 30-day average.
- **Exercise**: a table of tracked workout sessions with a raw-detail expander.

Set your time zone in `app.py` (`TZ` constant) before first use.

Optional convenience alias:

```bash
echo "alias fitbit='cd /path/to/ProjectFitBit && ./venv/bin/streamlit run app.py'" >> ~/.bashrc
```
Now you can launch the dashborad with only one command:
```bash
$] fitbit
```

## Security notes

- `client_secret.json`, `tokens.json`, `*.db` and `*.log` are listed in `.gitignore`. Never commit them: the refresh token grants long-lived read access to your health data.
- If a secret ever leaks, reset the client secret in Google Cloud Console and revoke the app at https://myaccount.google.com/permissions, then re-run `auth.py`.
- All scopes requested are read-only.

## Roadmap

- Multi-user support via the same OAuth flow (requires Google's restricted-scope verification).
- Replace cron polling with Health API webhook subscriptions.
- Source reconciliation for step counts using the API's `reconcile` endpoint.

## License

MIT
