#!/usr/bin/env bash
cd "$(dirname "$0")"

./venv/bin/python3 ingest.py

( while true; do
    sleep 900
    ./venv/bin/python3 ingest.py >> ingest.log 2>&1
  done ) &
LOOP_PID=$!
trap "kill $LOOP_PID 2>/dev/null" EXIT

./venv/bin/streamlit run app.py
