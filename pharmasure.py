import streamlit as st
import pandas as pd
import random
import time
from datetime import datetime
import plotly.express as px
import math

st.set_page_config(page_title="PharmaSure Simulation", layout="wide")
st.title("💊 PharmaSure - IoT Drug Transport Monitoring Simulation")

# --- Session State Initialization ---
if "records" not in st.session_state:
    st.session_state.records = []          # list of dict rows
if "running" not in st.session_state:
    st.session_state.running = False
if "last_alert_states" not in st.session_state:
    st.session_state.last_alert_states = {"temp": False, "hum": False, "shock": False}
if "point_index" not in st.session_state:
    st.session_state.point_index = 0       # for route simulation

# --- Sidebar Controls ---
st.sidebar.header("Simulation Controls")
col_a, col_b = st.sidebar.columns(2)
if col_a.button("Start"):
    st.session_state.running = True
if col_b.button("Stop"):
    st.session_state.running = False
if st.sidebar.button("Reset"):
    st.session_state.running = False
    st.session_state.records.clear()
    st.session_state.point_index = 0

update_interval = st.sidebar.selectbox("Update interval (s)", [0.5, 1, 2], index=0)
max_points_display = st.sidebar.slider("Points to display (rolling window)", 20, 500, 150, 10)
random_seed = st.sidebar.number_input("Random Seed (optional)", value=0, step=1)
if random_seed:
    random.seed(int(random_seed))

st.sidebar.header("Thresholds")
temp_min = st.sidebar.number_input("Temp Min (°C)", value=2.0, step=0.5)
temp_max = st.sidebar.number_input("Temp Max (°C)", value=8.0, step=0.5)
hum_min = st.sidebar.number_input("Humidity Min (%)", value=30.0, step=1.0)
hum_max = st.sidebar.number_input("Humidity Max (%)", value=50.0, step=1.0)
shock_limit = st.sidebar.number_input("Shock Limit", value=5.0, step=0.5)

# --- Simulation Function ---
def simulate_row(idx: int):
    # Temperature (introduce mild drift)
    base_temp = 5 + math.sin(idx / 15) * 1.2
    temp = round(base_temp + random.uniform(-1.5, 1.5), 2)

    # Humidity (bounded)
    base_hum = 40 + math.sin(idx / 22) * 5
    hum = round(base_hum + random.uniform(-4, 4), 2)
    hum = max(10, min(90, hum))

    # Shock events (mostly low, occasional spike)
    if random.random() < 0.06:
        shock = round(random.uniform(6, 10), 2)
    else:
        shock = round(random.uniform(0, 4), 2)

    # Route simulation (simple circular drift near a center)
    center_lat, center_lon = 28.61, 77.21
    radius = 0.004
    angle = idx / 25
    lat = round(center_lat + radius * math.cos(angle) + random.uniform(-0.0007, 0.0007), 6)
    lon = round(center_lon + radius * math.sin(angle) + random.uniform(-0.0007, 0.0007), 6)

    now = datetime.utcnow()
    return {
        "timestamp": now,
        "Temp": temp,
        "Humidity": hum,
        "Shock": shock,
        "Lat": lat,
        "Lon": lon
    }

# --- Update Loop (single step per rerun) ---
if st.session_state.running:
    # Append one new simulated reading
    row = simulate_row(st.session_state.point_index)
    st.session_state.records.append(row)
    st.session_state.point_index += 1
    # Sleep only when running (keeps UI responsive enough)
    time.sleep(update_interval)

# --- DataFrame Assembly ---
if st.session_state.records:
    df = pd.DataFrame(st.session_state.records)
    df_display = df.tail(max_points_display).copy()
else:
    df = pd.DataFrame(columns=["timestamp", "Temp", "Humidity", "Shock", "Lat", "Lon"])
    df_display = df

# --- KPI Calculations ---
def in_range(val, lo, hi):
    return lo <= val <= hi

if not df.empty:
    latest = df.iloc[-1]
    temp_ok = in_range(latest.Temp, temp_min, temp_max)
    hum_ok = in_range(latest.Humidity, hum_min, hum_max)
    shock_ok = latest.Shock <= shock_limit

    kpi_cols = st.columns(3)
    kpi_cols[0].metric("Temperature (°C)", latest.Temp, None if temp_ok else "⚠")
    kpi_cols[1].metric("Humidity (%)", latest.Humidity, None if hum_ok else "⚠")
    kpi_cols[2].metric("Shock", latest.Shock, None if shock_ok else "⚠")

# --- Layout ---
left, right = st.columns([2, 1])

with left:
    st.subheader("📈 Sensor Trends")
    if not df_display.empty:
        # Melt for multi-series plotting with unified timestamp
        chart_df = df_display.melt(id_vars="timestamp", value_vars=["Temp", "Humidity", "Shock"],
                                   var_name="Metric", value_name="Value")
        fig = px.line(chart_df, x="timestamp", y="Value", color="Metric",
                      title="Recent Sensor Readings", markers=True)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

    st.subheader("🧾 Data (Rolling Window)")
    st.dataframe(df_display.rename(columns={"timestamp": "Time (UTC)"}), use_container_width=True, height=280)

with right:
    st.subheader("🗺️ Route")
    if not df_display.empty:
        # Rename to lowercase for Streamlit's required column names
        map_df = df_display.rename(columns={"Lat": "lat", "Lon": "lon"})
        st.map(map_df[["lat", "lon"]])
    else:
        st.info("No location data.")

    st.subheader("⚠️ Alerts")
    if not df.empty:
        alerts = []
        if not temp_ok:
            alerts.append(f"Temperature out of range: {latest.Temp}°C")
        if not hum_ok:
            alerts.append(f"Humidity out of range: {latest.Humidity}%")
        if not shock_ok:
            alerts.append(f"Shock exceeded: {latest.Shock}")

        if alerts:
            for a in alerts:
                st.error(a)
        else:
            st.success("All conditions normal.")
    else:
        st.info("Waiting for first reading...")

    if not df.empty:
        st.download_button("Download CSV", df.to_csv(index=False), file_name="pharmasure_log.csv", mime="text/csv")

# Auto-rerun while running
if st.session_state.running:
    st.experimental_rerun()
