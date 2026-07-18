#!/usr/bin/env python3
import json
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

BASE = os.path.dirname(os.path.abspath(__file__))
TOKENS = os.path.join(BASE, "tokens.json")
DB = os.path.join(BASE, "projectfitbit.db")
API = "https://health.googleapis.com/v4/users/me/dataTypes"

BACKFILL_DAYS = 30
OVERLAP_MIN = 60

DATA_TYPES = {
    "heart-rate": "heart_rate.sample_time.physical_time",
    "sleep": None,
    "daily-resting-heart-rate": "daily_resting_heart_rate.date",
    "steps": "steps.interval.start_time",
    "exercise": None,
}


def get_creds():
    creds = Credentials.from_authorized_user_file(TOKENS)
    if not creds.valid:
        creds.refresh(Request())
        with open(TOKENS, "w") as f:
            f.write(creds.to_json())
        os.chmod(TOKENS, 0o600)
    return creds


def api_get(creds, data_type, filter_expr):
    points, page_token = [], None
    while True:
        qs = {"pageSize": "10000"}
        if filter_expr:
            qs["filter"] = filter_expr
        if page_token:
            qs["pageToken"] = page_token
        url = f"{API}/{data_type}/dataPoints?" + urllib.parse.urlencode(qs)
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {creds.token}"}
        )
        try:
            with urllib.request.urlopen(req) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            print(f"[ERROR] {data_type}: HTTP {e.code} {e.read().decode()[:300]}")
            return points
        points.extend(body.get("dataPoints", []))
        page_token = body.get("nextPageToken")
        if not page_token:
            return points


def init_db(con):
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS cardio (
            ts TEXT PRIMARY KEY, bpm INTEGER
        );
        CREATE TABLE IF NOT EXISTS raw_points (
            data_type TEXT, ts TEXT, payload TEXT,
            PRIMARY KEY (data_type, ts)
        );
        CREATE TABLE IF NOT EXISTS estado (
            data_type TEXT PRIMARY KEY, last_ts TEXT
        );
        """
    )
    con.commit()


def last_sync(con, data_type):
    row = con.execute(
        "SELECT last_ts FROM estado WHERE data_type=?", (data_type,)
    ).fetchone()
    if row:
        dt = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        return dt - timedelta(minutes=OVERLAP_MIN)
    return datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)


def point_ts(data_type, p):
    s = json.dumps(p)
    for key in ('"physicalTime"', '"startTime"'):
        idx = s.find(key)
        if idx != -1:
            start = s.find('"', idx + len(key) + 1) + 1
            return s[start : s.find('"', start)]
    body = next((v for k, v in p.items() if isinstance(v, dict)
                 and k not in ("dataSource",)), None)
    d = (body or {}).get("date")
    if isinstance(d, dict) and "year" in d:
        return f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}"
    return None


def ingest(con, creds, data_type, time_field):
    since_dt = last_sync(con, data_type)
    if time_field is None:
        filt = None
        since = "(no filter)"
    elif time_field.endswith(".date"):
        since = since_dt.strftime("%Y-%m-%d")
        filt = f'{time_field} >= "{since}"'
    else:
        since = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        filt = f'{time_field} >= "{since}"'
    points = api_get(creds, data_type, filt)
    max_ts = None
    for p in points:
        ts = point_ts(data_type, p)
        if not ts:
            continue
        con.execute(
            "INSERT OR REPLACE INTO raw_points VALUES (?,?,?)",
            (data_type, ts, json.dumps(p)),
        )
        if data_type == "heart-rate":
            bpm = int(p["heartRate"]["beatsPerMinute"])
            con.execute("INSERT OR REPLACE INTO cardio VALUES (?,?)", (ts, bpm))
        if max_ts is None or ts > max_ts:
            max_ts = ts
    if max_ts:
        con.execute(
            "INSERT OR REPLACE INTO estado VALUES (?,?)", (data_type, max_ts)
        )
    con.commit()
    print(f"[OK] {data_type}: {len(points)} points (since {since})")


def main():
    creds = get_creds()
    con = sqlite3.connect(DB)
    init_db(con)
    for dt, field in DATA_TYPES.items():
        ingest(con, creds, dt, field)
    con.close()
    print(f"[DONE] {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
