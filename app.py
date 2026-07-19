#!/usr/bin/env python3
import json
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DB = "projectfitbit.db"
TZ = ZoneInfo("Europe/Berlin")

ACCENT = "#2f6fed"
GRID = "rgba(128,134,150,0.25)"

st.set_page_config(page_title="ProjectFitBit", layout="wide")

st.markdown(
    """
    <style>
    #MainMenu, footer {visibility: hidden;}
    .block-container {padding-top: 2.2rem; max-width: 1200px;}
    h1, h2, h3 {font-weight: 600; letter-spacing: -0.01em;}
    [data-testid="stMetric"] {
        border: 1px solid rgba(128,134,150,0.35);
        border-radius: 8px;
        padding: 14px 18px;
    }
    [data-testid="stMetricLabel"] {font-size: 0.8rem;
        text-transform: uppercase; letter-spacing: 0.06em;}
    [data-testid="stMetricValue"] {font-size: 1.6rem;}
    .stTabs [data-baseweb="tab"] {font-size: 0.95rem; font-weight: 500;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("ProjectFitBit")
st.caption("Personal health dashboard - Data synced from the Google Health API")


def q(sql, params=()):
    con = sqlite3.connect(DB)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


def to_local(series_utc):
    s = pd.to_datetime(series_utc, utc=True, format="ISO8601")
    return s.dt.tz_convert(TZ)


def base_layout(fig, height=300):
    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=20, b=20),
        template=None,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c3c9d4", size=13),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, automargin=True)
    return fig


def body_of(p):
    return next(
        (v for k, v in p.items()
         if isinstance(v, dict) and k not in ("dataSource",)),
        {},
    )


tab_sleep, tab_hr, tab_act, tab_ex, tab_ins = st.tabs(
    ["Sleep", "Heart rate", "Activity", "Exercise", "Analysis"]
)

with tab_sleep:
    sleep_rows = q(
        "SELECT ts, payload FROM raw_points WHERE data_type='sleep' "
        "ORDER BY ts DESC"
    )
    if sleep_rows.empty:
        st.info("No sleep data yet.")
    else:
        sessions = []
        for _, row in sleep_rows.iterrows():
            p = json.loads(row["payload"])["sleep"]
            summary = p.get("summary", {})
            sessions.append(
                {
                    "start": row["ts"],
                    "end": p["interval"]["endTime"],
                    "min_asleep": int(summary.get("minutesAsleep", 0)),
                    "min_awake": int(summary.get("minutesAwake", 0)),
                    "stages": p.get("stages", []),
                    "stages_summary": summary.get("stagesSummary", []),
                }
            )

        labels = [
            (to_local(pd.Series([s["start"]]))[0] - timedelta(hours=12))
            .strftime("Night of %Y-%m-%d")
            for s in sessions
        ]
        sel = st.selectbox("Night", range(len(sessions)),
                           format_func=lambda i: labels[i])
        ses = sessions[sel]

        mins = {d["type"]: int(d["minutes"]) for d in ses["stages_summary"]}

        SLEEP_CARD = {
            "asleep": ACCENT,
            "deep": "#27496d",
            "rem": "#5a6acf",
            "light": "#7c98b3",
            "awake": "#c98a5a",
        }
        css = "".join(
            f'''
            .st-key-card_{k} [data-testid="stMetric"] {{
                background: {c}; border: none; border-radius: 8px;
            }}
            .st-key-card_{k} [data-testid="stMetricLabel"] p,
            .st-key-card_{k} [data-testid="stMetricValue"] {{
                color: #f5f7fa !important;
            }}
            '''
            for k, c in SLEEP_CARD.items()
        )
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1.container(key="card_asleep"):
            st.metric("Asleep",
                      f"{ses['min_asleep']//60}h {ses['min_asleep']%60}m")
        with c2.container(key="card_deep"):
            st.metric("Deep", f"{mins.get('DEEP', 0)} min")
        with c3.container(key="card_rem"):
            st.metric("REM", f"{mins.get('REM', 0)} min")
        with c4.container(key="card_light"):
            st.metric("Light", f"{mins.get('LIGHT', 0)} min")
        with c5.container(key="card_awake"):
            st.metric("Awake", f"{ses['min_awake']} min")

        if ses["min_asleep"]:
            quality = round(
                100 * (mins.get("DEEP", 0) + mins.get("REM", 0))
                / ses["min_asleep"]
            )
            st.caption(
                f"Restorative sleep (deep + REM): {quality}% of time asleep"
            )

        LEVEL = {"DEEP": 0, "LIGHT": 1, "REM": 2, "AWAKE": 3}
        COLOR = {"DEEP": "#27496d", "LIGHT": "#7c98b3", "REM": "#5a6acf",
                 "AWAKE": "#c98a5a"}
        fig = go.Figure()
        for stg in ses["stages"]:
            t0 = pd.Timestamp(stg["startTime"]).tz_convert(TZ)
            t1 = pd.Timestamp(stg["endTime"]).tz_convert(TZ)
            lvl = LEVEL[stg["type"]]
            fig.add_trace(
                go.Scatter(
                    x=[t0, t1], y=[lvl, lvl], mode="lines",
                    line=dict(color=COLOR[stg["type"]], width=12),
                    showlegend=False,
                    hovertemplate=f"{stg['type']}<br>%{{x|%H:%M}}"
                                  "<extra></extra>",
                )
            )
        fig.update_yaxes(
            tickvals=[0, 1, 2, 3],
            ticktext=["Deep", "Light", "REM", "Awake"],
        )
        st.plotly_chart(base_layout(fig), width="stretch")

        if len(sessions) > 1:
            st.subheader("Trend")
            df = pd.DataFrame(
                {
                    "night": [(to_local(pd.Series([s["start"]]))[0]
                               - timedelta(hours=12)).date()
                              for s in sessions],
                    "hours": [s["min_asleep"] / 60 for s in sessions],
                }
            ).sort_values("night")
            fig = go.Figure(
                go.Bar(x=df["night"].astype(str), y=df["hours"],
                       marker_color=ACCENT)
            )
            fig.update_yaxes(title="hours asleep")
            st.plotly_chart(base_layout(fig, 260), width="stretch")

with tab_hr:
    days = st.slider("Days to show", 1, 30, 1)
    since = (datetime.now(TZ) - timedelta(days=days)).astimezone(
        ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
    hr = q("SELECT ts, bpm FROM cardio WHERE ts >= ? ORDER BY ts", (since,))

    if hr.empty:
        st.info("No heart rate data in this range.")
    else:
        hr["local"] = to_local(hr["ts"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Average", f"{hr['bpm'].mean():.0f} bpm")
        c2.metric("Minimum", f"{hr['bpm'].min()} bpm")
        c3.metric("Maximum", f"{hr['bpm'].max()} bpm")

        fig = go.Figure(
            go.Scatter(x=hr["local"], y=hr["bpm"], mode="lines",
                       line=dict(color=ACCENT, width=1))
        )
        fig.update_yaxes(title="bpm")
        st.plotly_chart(base_layout(fig), width="stretch")

    rhr_rows = q(
        "SELECT ts, payload FROM raw_points "
        "WHERE data_type='daily-resting-heart-rate' ORDER BY ts"
    )
    if not rhr_rows.empty:
        vals = []
        for _, row in rhr_rows.iterrows():
            body = body_of(json.loads(row["payload"]))
            num = next((int(v) for v in body.values()
                        if isinstance(v, (int, str)) and str(v).isdigit()),
                       None)
            if num:
                vals.append({"date": row["ts"], "rhr": num})
        if vals:
            st.subheader("Resting heart rate")
            df = pd.DataFrame(vals)
            fig = go.Figure(
                go.Scatter(x=df["date"], y=df["rhr"],
                           mode="lines+markers",
                           line=dict(color="#7c98b3", width=2))
            )
            fig.update_yaxes(title="resting bpm")
            st.plotly_chart(base_layout(fig, 240), width="stretch")

with tab_act:
    steps_rows = q(
        "SELECT ts, payload FROM raw_points WHERE data_type='steps' "
        "ORDER BY ts"
    )
    if steps_rows.empty:
        st.info("No step data yet.")
    else:
        recs = []
        for _, row in steps_rows.iterrows():
            p = json.loads(row["payload"])
            src = p.get("dataSource", {})
            if src.get("platform") != "FITBIT":
                continue
            if src.get("device", {}).get("displayName") == "MobileTrack":
                continue
            body = body_of(p)
            count = next((int(v) for k, v in body.items()
                          if k != "interval" and str(v).isdigit()), 0)
            recs.append({"ts": row["ts"], "steps": count})
        df = pd.DataFrame(recs)
        df["day"] = to_local(df["ts"]).dt.date
        daily = df.groupby("day")["steps"].sum().reset_index()
        today = daily.iloc[-1]
        avg = daily["steps"].mean()

        c1, c2 = st.columns(2)
        c1.metric(f"Steps {today['day'].strftime('%Y-%m-%d')}",
                  f"{today['steps']:,}")
        c2.metric("Daily average (30 days)", f"{avg:,.0f}")

        fig = go.Figure(
            go.Bar(x=daily["day"].astype(str), y=daily["steps"],
                   marker_color=ACCENT)
        )
        fig.update_yaxes(title="steps")
        st.plotly_chart(base_layout(fig), width="stretch")

with tab_ex:
    ex_rows = q(
        "SELECT ts, payload FROM raw_points WHERE data_type='exercise' "
        "ORDER BY ts DESC"
    )
    if ex_rows.empty:
        st.info(
            "No exercise sessions yet. Sessions tracked by your device "
            "(walks, runs, workouts) will appear here."
        )
    else:
        recs = []
        for _, row in ex_rows.iterrows():
            body = body_of(json.loads(row["payload"]))
            interval = body.get("interval", {})
            t0 = interval.get("startTime")
            t1 = interval.get("endTime")
            dur = ""
            if t0 and t1:
                delta = (pd.Timestamp(t1) - pd.Timestamp(t0))
                dur = f"{int(delta.total_seconds() // 60)} min"
            name = next(
                (str(v) for k, v in body.items()
                 if isinstance(v, str) and k not in ("createTime",
                                                     "updateTime")),
                "Exercise",
            )
            recs.append(
                {
                    "Date": to_local(pd.Series([row["ts"]]))[0]
                    .strftime("%Y-%m-%d %H:%M"),
                    "Type": name,
                    "Duration": dur,
                    "_raw": body,
                }
            )

        st.metric("Tracked sessions", len(recs))
        table = pd.DataFrame(
            [{k: v for k, v in r.items() if not k.startswith("_")}
             for r in recs]
        )
        st.dataframe(table, width="stretch", hide_index=True)

        with st.expander("Latest session detail"):
            st.json(recs[0]["_raw"])

with tab_ins:

    def daily_frame():
        rows = []
        srows = q("SELECT ts, payload FROM raw_points "
                  "WHERE data_type='sleep' ORDER BY ts")
        for _, r in srows.iterrows():
            p = json.loads(r["payload"])["sleep"]
            summ = p.get("summary", {})
            m = {d["type"]: int(d["minutes"])
                 for d in summ.get("stagesSummary", [])}
            asleep = int(summ.get("minutesAsleep", 0))
            rows.append({
                "day": (to_local(pd.Series([r["ts"]]))[0]
                        - timedelta(hours=12)).date(),
                "sleep_hours": asleep / 60,
                "deep_min": m.get("DEEP", 0),
                "rem_min": m.get("REM", 0),
                "restorative_pct": (
                    100 * (m.get("DEEP", 0) + m.get("REM", 0)) / asleep
                    if asleep else None),
            })
        sleep_df = pd.DataFrame(rows)

        st_rows = q("SELECT ts, payload FROM raw_points "
                    "WHERE data_type='steps' ORDER BY ts")
        recs = []
        for _, r in st_rows.iterrows():
            p = json.loads(r["payload"])
            src = p.get("dataSource", {})
            if src.get("platform") != "FITBIT":
                continue
            if src.get("device", {}).get("displayName") == "MobileTrack":
                continue
            body = body_of(p)
            count = next((int(v) for k, v in body.items()
                          if k != "interval" and str(v).isdigit()), 0)
            recs.append({"ts": r["ts"], "steps": count})
        steps_df = pd.DataFrame(recs)
        if not steps_df.empty:
            steps_df["day"] = to_local(steps_df["ts"]).dt.date
            steps_df = steps_df.groupby("day")["steps"].sum().reset_index()

        rrows = q("SELECT ts, payload FROM raw_points "
                  "WHERE data_type='daily-resting-heart-rate' ORDER BY ts")
        rv = []
        for _, r in rrows.iterrows():
            body = body_of(json.loads(r["payload"]))
            num = next((int(v) for v in body.values()
                        if isinstance(v, (int, str)) and str(v).isdigit()),
                       None)
            if num:
                rv.append({"day": pd.Timestamp(r["ts"]).date(), "rhr": num})
        rhr_df = pd.DataFrame(rv)

        df = sleep_df
        if not steps_df.empty:
            df = df.merge(steps_df, on="day", how="outer")
        if not rhr_df.empty:
            df = df.merge(rhr_df, on="day", how="outer")
        return df.sort_values("day").reset_index(drop=True)

    df = daily_frame()

    st.subheader("Daily score")
    if df.empty or df["sleep_hours"].dropna().empty:
        st.info("Not enough sleep data to compute a score yet.")
    else:
        last = df.dropna(subset=["sleep_hours"]).iloc[-1]
        rhr_base = df["rhr"].dropna().mean() if "rhr" in df else None

        p_duration = min(last["sleep_hours"] / 8, 1) * 30
        p_restorative = min((last["restorative_pct"] or 0) / 40, 1) * 20
        steps_today = last.get("steps") or 0
        p_activity = min(steps_today / 10000, 1) * 25
        if rhr_base and not pd.isna(last.get("rhr")):
            delta = last["rhr"] - rhr_base
            p_heart = 25 if delta <= 0 else max(0, 25 - 5 * delta)
        else:
            p_heart = 12.5
        score = round(p_duration + p_restorative + p_activity + p_heart)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Score", f"{score}/100")
        c2.metric("Sleep duration", f"{p_duration:.0f}/30")
        c3.metric("Restorative sleep", f"{p_restorative:.0f}/20")
        c4.metric("Activity", f"{p_activity:.0f}/25")
        c5.metric("Heart", f"{p_heart:.0f}/25")
        st.progress(score / 100)
        st.caption(
            "Transparent formula: sleep duration (8h = max, 30 pts) + "
            "restorative sleep (40% deep+REM = max, 20 pts) + "
            "steps (10,000 = max, 25 pts) + "
            "resting heart rate vs your historical average (25 pts, "
            "minus 5 pts per bpm above it)."
        )

    st.subheader("Correlations")
    numeric = df.drop(columns=["day"], errors="ignore").select_dtypes("number")
    n_days = len(df.dropna(subset=["sleep_hours"])) if not df.empty else 0
    if n_days < 5:
        st.info(
            f"At least 5 days with sleep data are needed for meaningful "
            f"correlations (currently {n_days}). This section will come "
            "alive on its own as nights accumulate."
        )
    else:
        NAMES = {
            "sleep_hours": "Sleep hours",
            "deep_min": "Deep sleep (min)",
            "rem_min": "REM (min)",
            "restorative_pct": "Restorative sleep (%)",
            "steps": "Steps",
            "rhr": "Resting heart rate",
        }
        cols = [c for c in numeric.columns if c in NAMES]
        cx, cy = st.columns(2)
        x = cx.selectbox("X axis", cols, index=cols.index("steps")
                         if "steps" in cols else 0,
                         format_func=lambda c: NAMES[c])
        y = cy.selectbox("Y axis", cols, index=cols.index("sleep_hours")
                         if "sleep_hours" in cols else 0,
                         format_func=lambda c: NAMES[c])
        pair = df[[x, y]].dropna()
        if len(pair) >= 5 and x != y:
            r = pair[x].corr(pair[y])
            st.metric("Correlation (Pearson r)", f"{r:+.2f}")
            fig = go.Figure(
                go.Scatter(x=pair[x], y=pair[y], mode="markers",
                           marker=dict(color=ACCENT, size=9))
            )
            fig.update_xaxes(title=NAMES[x])
            fig.update_yaxes(title=NAMES[y])
            st.plotly_chart(base_layout(fig), width="stretch")
            st.caption(
                "Guide: |r| > 0.5 strong, 0.3-0.5 moderate, < 0.3 weak. "
                "Correlation is not causation; with few days, treat it as "
                "a hint, not a verdict."
            )
        else:
            st.info("Not enough days with both variables.")

        with st.expander("Full correlation matrix"):
            st.dataframe(
                numeric[cols].corr().round(2).rename(
                    index=NAMES, columns=NAMES),
                width="stretch",
            )

st.caption(
    "Data refreshes automatically every 15 minutes via cron. "
    "The latest night of sleep is available after the morning sync."
)
