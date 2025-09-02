import streamlit as st
import pandas as pd
import random
import time
from datetime import datetime, timedelta
import math
import json
from pathlib import Path
import pydeck as pdk
from statistics import mean, pstdev
from plotly.subplots import make_subplots
import plotly.graph_objects as go

# --- Constants / Config ---
PERSIST_FILE = Path("pharmasure_session.csv")
AUTOSAVE_EVERY = 25
MAX_HISTORY = 5000

st.set_page_config(page_title="PharmaSure Simulation", layout="wide")
st.title("💊 PharmaSure - IoT Drug Transport Monitoring Simulation")

# --- State Init ---
if "records" not in st.session_state:
    if PERSIST_FILE.exists():
        st.session_state.records = pd.read_csv(PERSIST_FILE, parse_dates=["timestamp"]).to_dict("records")
    else:
        st.session_state.records = []
if "running" not in st.session_state:
    st.session_state.running = False
if "point_index" not in st.session_state:
    st.session_state.point_index = len(st.session_state.records)
if "last_alert_flags" not in st.session_state:
    st.session_state.last_alert_flags = (True, True, True)
if "new_points_since_save" not in st.session_state:
    st.session_state.new_points_since_save = 0
if "config_loaded" not in st.session_state:
    st.session_state.config_loaded = False
if "anomaly_baseline" not in st.session_state:
    st.session_state.anomaly_baseline = {"Temp": [], "Humidity": [], "Shock": []}
if "last_sample_time" not in st.session_state:
    st.session_state.last_sample_time = None
if "next_sample_time" not in st.session_state:
    st.session_state.next_sample_time = None

# --- Sidebar Controls ---
st.sidebar.header("Simulation Controls")
c1, c2, c3 = st.sidebar.columns(3)
if c1.button("Start"):
    st.session_state.running = True
    if st.session_state.last_sample_time is None:
        # Force immediate first sample
        st.session_state.next_sample_time = datetime.utcnow()
if c2.button("Stop"):
    st.session_state.running = False
if c3.button("Reset"):
    st.session_state.running = False
    st.session_state.records.clear()
    st.session_state.point_index = 0
    st.session_state.last_sample_time = None
    st.session_state.next_sample_time = None
    st.session_state.anomaly_baseline = {"Temp": [], "Humidity": [], "Shock": []}
    if PERSIST_FILE.exists():
        PERSIST_FILE.unlink()

sampling_interval = st.sidebar.selectbox("Sampling interval (seconds)", [5, 10, 30], index=0)
max_points_display = st.sidebar.slider("Rolling window points", 50, 1000, 300, 25)
random_seed = st.sidebar.number_input("Random Seed (0=off)", value=0, step=1)
if random_seed:
    random.seed(int(random_seed))

# Add (optional) UI refresh smoothing: adaptive poll interval (ms)
# Faster refresh for shorter sampling intervals without heavy redraw spam
poll_interval_ms = {5: 1000, 10: 1500, 30: 2500}[sampling_interval]

# Trigger lightweight periodic reruns ONLY while running (replaces time.sleep + st.rerun)
if st.session_state.running:
    # Key stable so autorefresh keeps firing; interval can change when sampling interval changes
    st.autorefresh(interval=poll_interval_ms, key="rt_autorefresh")

st.sidebar.header("Thresholds")
temp_min = st.sidebar.number_input("Temp Min (°C)", value=2.0, step=0.5)
temp_max = st.sidebar.number_input("Temp Max (°C)", value=8.0, step=0.5)
hum_min = st.sidebar.number_input("Humidity Min (%)", value=30.0, step=1.0)
hum_max = st.sidebar.number_input("Humidity Max (%)", value=50.0, step=1.0)
shock_limit = st.sidebar.number_input("Shock Limit", value=5.0, step=0.5)

st.sidebar.header("Advanced")
simulate_dropout = st.sidebar.checkbox("Simulate sensor dropouts", value=False)
enable_anomaly = st.sidebar.checkbox("Anomaly flags (z>2.5)", value=True)
audible_alert = st.sidebar.checkbox("Audible alert", value=False)

with st.sidebar.expander("Config Import / Export"):
    ec1, ec2 = st.columns(2)
    if ec1.button("Export JSON"):
        cfg = {
            "temp_min": temp_min, "temp_max": temp_max,
            "hum_min": hum_min, "hum_max": hum_max,
            "shock_limit": shock_limit,
            "sampling_interval": sampling_interval
        }
        st.download_button("Download config.json",
                           data=json.dumps(cfg, indent=2),
                           file_name="config.json",
                           mime="application/json",
                           use_container_width=True)
    up = ec2.file_uploader("Import", type=["json"])
    if up and not st.session_state.config_loaded:
        data = json.load(up)
        temp_min = data.get("temp_min", temp_min)
        temp_max = data.get("temp_max", temp_max)
        hum_min = data.get("hum_min", hum_min)
        hum_max = data.get("hum_max", hum_max)
        shock_limit = data.get("shock_limit", shock_limit)
        # sampling_interval re-applied next rerun (selectbox fixed list)
        st.session_state.config_loaded = True
        st.success("Configuration imported.")

# --- Simulation Functions ---
def simulate_row(idx: int):
    base_temp = 5 + math.sin(idx / 18) * 1.2
    temp = round(base_temp + random.uniform(-1.2, 1.2), 2)
    base_hum = 40 + math.sin(idx / 27) * 6
    hum = round(base_hum + random.uniform(-4.5, 4.5), 2)
    hum = max(5, min(95, hum))
    if random.random() < 0.05:
        shock = round(random.uniform(6, 11), 2)
    else:
        shock = round(random.uniform(0, 4.5), 2)
    if simulate_dropout and random.random() < 0.02: temp = None
    if simulate_dropout and random.random() < 0.02: hum = None
    center_lat, center_lon = 28.61, 77.21
    radius = 0.004
    angle = idx / 24
    lat = round(center_lat + radius * math.cos(angle) + random.uniform(-0.0007, 0.0007), 6)
    lon = round(center_lon + radius * math.sin(angle) + random.uniform(-0.0007, 0.0007), 6)
    return {
        "timestamp": datetime.utcnow(),
        "Temp": temp,
        "Humidity": hum,
        "Shock": shock,
        "lat": lat,
        "lon": lon
    }

def anomaly_flags(row):
    if not enable_anomaly: return {}
    out = {}
    for k in ["Temp", "Humidity", "Shock"]:
        v = row[k]
        if v is None:
            out[k] = False
            continue
        baseline = st.session_state.anomaly_baseline[k]
        if len(baseline) >= 30:
            mu = mean(baseline)
            sd = pstdev(baseline) or 1e-6
            out[k] = abs((v - mu) / sd) > 2.5
        else:
            out[k] = False
        baseline.append(v)
        if len(baseline) > 300:
            baseline.pop(0)
    return out

def compute_kpis(df: pd.DataFrame):
    if df.empty: return None
    latest = df.iloc[-1]
    temp_ok = (latest.Temp is not None) and temp_min <= latest.Temp <= temp_max
    hum_ok = (latest.Humidity is not None) and hum_min <= latest.Humidity <= hum_max
    shock_ok = latest.Shock <= shock_limit
    temp_series = df["Temp"].dropna()
    hum_series = df["Humidity"].dropna()
    comp_temp = temp_series.between(temp_min, temp_max).mean()*100 if len(temp_series) else None
    comp_hum = hum_series.between(hum_min, hum_max).mean()*100 if len(hum_series) else None
    comp_shock = df["Shock"].le(shock_limit).mean()*100 if len(df) else None
    return {
        "latest": latest,
        "flags": (temp_ok, hum_ok, shock_ok),
        "compliance": (comp_temp, comp_hum, comp_shock)
    }

# --- Sampling (interval driven) ---
now = datetime.utcnow()
if st.session_state.running:
    # Initialize schedule if needed
    if st.session_state.next_sample_time is None:
        st.session_state.next_sample_time = now
    # Produce sample(s) if we've passed schedule (catch up if server lagged)
    produced = False
    while now >= st.session_state.next_sample_time:
        row = simulate_row(st.session_state.point_index)
        st.session_state.point_index += 1
        af = anomaly_flags(row)
        for k, v in af.items():
            row[f"Anomaly{k}"] = v
        st.session_state.records.append(row)
        st.session_state.last_sample_time = row["timestamp"]
        st.session_state.next_sample_time += timedelta(seconds=sampling_interval)
        produced = True
        if len(st.session_state.records) > MAX_HISTORY:
            st.session_state.records = st.session_state.records[-(MAX_HISTORY//2):]
        st.session_state.new_points_since_save += 1
        if st.session_state.new_points_since_save >= AUTOSAVE_EVERY:
            pd.DataFrame(st.session_state.records).to_csv(PERSIST_FILE, index=False)
            st.session_state.new_points_since_save = 0
        # Limit catch-up to avoid long loop
        if (now - st.session_state.last_sample_time).total_seconds() > sampling_interval*3:
            break

# --- Data Prep ---
df = pd.DataFrame(st.session_state.records) if st.session_state.records else pd.DataFrame(
    columns=["timestamp","Temp","Humidity","Shock","lat","lon"])
df_display = df.tail(max_points_display).copy()

# --- Header Status Bar ---
status_cols = st.columns(5)
status_cols[0].markdown(f"**Running:** {'🟢' if st.session_state.running else '🔴'}")
status_cols[1].markdown(f"**Samples:** {len(df)}")
if st.session_state.last_sample_time:
    status_cols[2].markdown(f"**Last:** {st.session_state.last_sample_time.strftime('%H:%M:%S')}")
else:
    status_cols[2].markdown("**Last:** —")
if st.session_state.next_sample_time and st.session_state.running:
    status_cols[3].markdown(f"**Next:** {st.session_state.next_sample_time.strftime('%H:%M:%S')}")
else:
    status_cols[3].markdown("**Next:** —")
status_cols[4].markdown(f"**Interval:** {sampling_interval}s")

# --- KPIs & Alerts ---
kpi = compute_kpis(df)
alert_placeholder = st.empty()
if kpi:
    latest = kpi["latest"]
    temp_ok, hum_ok, shock_ok = kpi["flags"]
    comp_t, comp_h, comp_s = kpi["compliance"]
    colk = st.columns(4)
    colk[0].metric("Temp (°C)", latest.Temp if latest.Temp is not None else "—", None if temp_ok else "⚠")
    colk[1].metric("Humidity (%)", latest.Humidity if latest.Humidity is not None else "—", None if hum_ok else "⚠")
    colk[2].metric("Shock", latest.Shock, None if shock_ok else "⚠")
    comp_txt = f"T:{comp_t:.1f}% H:{comp_h:.1f}% S:{comp_s:.1f}%" if comp_t is not None else "—"
    colk[3].metric("Compliance", comp_txt)

    prev = st.session_state.last_alert_flags
    curr = (temp_ok, hum_ok, shock_ok)
    if curr != prev:
        msgs = []
        if not temp_ok: msgs.append(f"Temp {latest.Temp}°C out of range")
        if not hum_ok: msgs.append(f"Humidity {latest.Humidity}% out of range")
        if not shock_ok: msgs.append(f"Shock {latest.Shock} > {shock_limit}")
        if msgs:
            alert_placeholder.error(" | ".join(msgs))
            if audible_alert:
                st.audio("https://actions.google.com/sounds/v1/alarms/beep_short.ogg")
        else:
            alert_placeholder.success("All conditions normal")
        st.session_state.last_alert_flags = curr

# --- Layout: Charts & Table ---
left, right = st.columns([2.1, 1])

with left:
    st.subheader("📈 Sensor Trends")
    if not df_display.empty:
        temp_trace = df_display[["timestamp","Temp"]].dropna()
        hum_trace = df_display[["timestamp","Humidity"]].dropna()
        shock_trace = df_display[["timestamp","Shock"]]
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        if not temp_trace.empty:
            fig.add_trace(go.Scatter(x=temp_trace.timestamp, y=temp_trace.Temp, mode="lines+markers",
                                     name="Temp", line=dict(color="#ff7f0e")), secondary_y=False)
        if not hum_trace.empty:
            fig.add_trace(go.Scatter(x=hum_trace.timestamp, y=hum_trace.Humidity, mode="lines+markers",
                                     name="Humidity", line=dict(color="#1f77b4")), secondary_y=False)
        fig.add_trace(go.Scatter(x=shock_trace.timestamp, y=shock_trace.Shock, mode="lines+markers",
                                 name="Shock", line=dict(color="#2ca02c")), secondary_y=True)
        fig.add_hrect(y0=temp_min, y1=temp_max, fillcolor="orange", opacity=0.08, line_width=0)
        fig.add_hrect(y0=hum_min, y1=hum_max, fillcolor="blue", opacity=0.06, line_width=0)
        fig.add_shape(type="rect", xref="x", yref="y2",
                      x0=shock_trace.timestamp.min() if len(shock_trace) else 0,
                      x1=shock_trace.timestamp.max() if len(shock_trace) else 1,
                      y0=0, y1=shock_limit, fillcolor="green", opacity=0.05, line_width=0)
        fig.update_yaxes(title_text="Temp °C / Humidity %", secondary_y=False)
        fig.update_yaxes(title_text="Shock", secondary_y=True)
        fig.update_layout(height=420, margin=dict(l=40,r=40,t=40,b=40),
                          legend=dict(orientation="h", y=1.02, x=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

    st.subheader("🧾 Data (Rolling Window)")
    st.dataframe(df_display, use_container_width=True, height=280)

with right:
    st.subheader("🗺️ Live Route")
    if not df_display.empty:
        latest_point = df_display.tail(1)
        layer_path = pdk.Layer(
            "PathLayer",
            data=[{"path": df_display[["lon","lat"]].to_dict("records")}],
            get_path="path",
            get_color=[0,122,255],
            width_scale=1,
            width_min_pixels=2
        )
        layer_points = pdk.Layer(
            "ScatterplotLayer",
            data=df_display,
            get_position='[lon, lat]',
            get_radius=40,
            get_fill_color=[255,140,0,150]
        )
        layer_latest = pdk.Layer(
            "ScatterplotLayer",
            data=latest_point,
            get_position='[lon, lat]',
            get_radius=120,
            get_fill_color=[255,0,0,220]
        )
        midpoint = [df_display.lat.mean(), df_display.lon.mean()]
        deck = pdk.Deck(
            layers=[layer_path, layer_points, layer_latest],
            initial_view_state=pdk.ViewState(latitude=midpoint[0], longitude=midpoint[1], zoom=13),
            tooltip={"text":"Live Route"}
        )
        st.pydeck_chart(deck)
    else:
        st.info("No location data.")

    st.subheader("⚠️ Current Status")
    if kpi:
        temp_ok, hum_ok, shock_ok = kpi["flags"]
        st.write(f"Temperature: {'OK' if temp_ok else 'BREACH'}")
        st.write(f"Humidity: {'OK' if hum_ok else 'BREACH'}")
        st.write(f"Shock: {'OK' if shock_ok else 'BREACH'}")
    if enable_anomaly and not df_display.empty:
        anomaly_cols = [c for c in df_display.columns if c.startswith("Anomaly")]
        if anomaly_cols:
            counts = {c: int(df_display[c].sum()) for c in anomaly_cols}
            st.caption(f"Anomalies (window): {counts}")
    if not df.empty:
        st.download_button("Download Full CSV", df.to_csv(index=False), "pharmasure_log.csv", "text/csv")

# --- Auto refresh loop (light polling every 1s while running) ---