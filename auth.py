#!/usr/bin/env python3
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
]

BASE = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.path.join(BASE, "client_secret.json")
TOKENS = os.path.join(BASE, "tokens.json")


def main():
    if not os.path.exists(CLIENT_SECRET):
        raise SystemExit(f"ERROR: {CLIENT_SECRET} not found")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(
        port=8765,
        access_type="offline",
        prompt="consent",
        open_browser=True,
    )

    with open(TOKENS, "w") as f:
        f.write(creds.to_json())
    os.chmod(TOKENS, 0o600)

    print(f"OK: tokens saved to {TOKENS}")
    print(f"Refresh token present: {bool(creds.refresh_token)}")
    if not creds.refresh_token:
        print("WARNING: no refresh token. Revoke access at "
              "myaccount.google.com/permissions and run again.")


if __name__ == "__main__":
    main()
