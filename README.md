# PharmaSure Monitoring Simulation

A Streamlit-based demo for simulated cold‑chain / pharma shipment telemetry: temperature, humidity, shock, and route (lat/lon). Two Python apps included:

- `pharmasure.py` – simple incremental simulation (basic prototype).
- `pharmas.py` – advanced real-time interval scheduler with persistence, anomalies, compliance metrics, and improved map.

---

## 1. File Overview

### 1.1 pharmasure.py (Basic)
Purpose: Minimal looping simulation that appends a new random row every rerun while "Start" is active.

Key traits:
- Immediate for-loop style: each rerun adds exactly one sample and sleeps (`time.sleep(update_interval)`).
- Uses `st.experimental_rerun()` (deprecated in newer Streamlit; replace with `st.rerun()` if needed).
- Single Plotly line chart (Temp, Humidity, Shock on same y-axis).
- `st.map` for points (renames Lat/Lon → lat/lon each refresh).
- Hard real-time interval accuracy is approximate (blocked by sleep).
- Alerts only reflect last sample; no persistence.
- No persistence to disk.

### 1.2 pharmas.py (Advanced Real-Time)
Purpose: More production-like structure with precise sampling at fixed intervals (5s / 10s / 30s) independent of UI redraw speed.

Enhancements:
- Interval scheduler: next sample time tracked (`next_sample_time`). Multiple samples created if UI lagged (catch-up).
- Non-blocking refresh: uses `st.autorefresh()` (adaptive polling) instead of long sleeps.
- Adjustable sampling interval (5, 10, 30 seconds).
- Persistence: autosaves every N samples to `pharmasure_session.csv`; reloads on startup.
- Compliance KPIs (% in-range for each metric).
- Debounced alerts (only on state change) + optional audible signal.
- Anomaly detection (rolling z-score > 2.5) with per-metric baselines.
- Rolling window limit + hard cap to control memory (`MAX_HISTORY`).
- Route rendered with PyDeck Path + points + highlighted latest point.
- Config import/export (JSON).
- Simulated sensor dropout (optional).
- Cleaner status bar: Running flag, sample counts, last/next timestamps.
- No deprecated API calls.

---

## 2. Core Concepts

| Concept                | Basic (`pharmasure.py`)     | Advanced (`pharmas.py`)                          |
|------------------------|-----------------------------|--------------------------------------------------|
| Sampling timing        | Sleep-based per rerun       | Scheduled timestamps (accurate intervals)        |
| Refresh mechanism      | Blocking sleep + rerun      | `st.autorefresh()` adaptive polling              |
| Persistence            | None                        | CSV autosave / reload                            |
| Alerts                 | Immediate only              | Debounced + optional sound                       |
| Anomalies              | No                          | Z-score flags                                    |
| Map                    | Static scatter              | Path + points + highlighted live point           |
| Config portability     | No                          | JSON export/import                               |
| Multiple metrics scale | Single axis                 | Dual y-axis                                      |

---

## 3. Installation & Environment (Windows)

From project root (`C:\Users\HP\ps`):

```powershell
# 1. Create and activate virtual environment
py -m venv .venv
.\.venv\Scripts\activate

# 2. Upgrade pip
python -m pip install --upgrade pip

# 3. Install dependencies
pip install streamlit pandas plotly pydeck
```

(If you plan to extend with MQTT later: `pip install paho-mqtt`.)

Check versions:
```powershell
python -c "import streamlit, pandas, plotly; print(streamlit.__version__)"
```

---

## 4. Running the Apps

Basic prototype:
```powershell
python -m streamlit run pharmasure.py
```

Advanced real-time version:
```powershell
python -m streamlit run pharmas.py
```

Then open the local URL (usually http://localhost:8501).

---

## 5. Using pharmas.py (Advanced)

1. Click Start:
   - First sample generated immediately (if none yet).
   - Next sample scheduled at now + interval (5/10/30 s).
2. While running:
   - UI auto-refreshes (poll interval depends on chosen sampling interval).
   - If the app stalls and misses a slot, the loop catches up (bounded).
3. Stop:
   - Scheduler halts (next time stays frozen until Start resumes).
4. Reset:
   - Clears in-memory records, CSV persistence, baselines, indices.
5. Adjust thresholds:
   - Temp/Humidity/Shock ranges immediately affect KPIs and alerts.
6. Toggle anomaly detection / dropout simulation as needed.
7. Export config (JSON) or import one to reuse settings.
8. Download full CSV anytime (includes anomaly flags if enabled).

---

## 6. Data Columns

| Column        | Meaning                                  |
|---------------|-------------------------------------------|
| timestamp     | UTC datetime of sample                   |
| Temp          | Simulated temperature (°C)               |
| Humidity      | Simulated relative humidity (%)          |
| Shock         | Simulated shock/vibration magnitude      |
| lat / lon     | Simulated route coordinates              |
| Anomaly*      | Boolean flags when anomaly mode enabled  |

---

## 7. Customization Points

In `pharmas.py`:
- `MAX_HISTORY`: adjust memory usage.
- `AUTOSAVE_EVERY`: change autosave frequency.
- Anomaly threshold: modify `> 2.5` inside `anomaly_flags`.
- Route shape: change radius, angle increment, or adopt real GPS ingestion.

---

## 8. Troubleshooting

| Symptom                                    | Cause / Fix |
|--------------------------------------------|-------------|
| "streamlit not recognized"                 | Activate venv; use `python -m streamlit` |
| Chart not updating                         | Ensure Start pressed; check browser auto-refresh not blocked |
| No map points                              | Wait for first sample; ensure records not empty |
| `st.experimental_rerun` error (basic file) | Replace with `st.rerun()` if using new Streamlit |
| High CPU                                   | Reduce polling rate (increase interval) or disable anomaly flags |
| CSV not created                            | Need at least `AUTOSAVE_EVERY` samples; or press Download |

---

## 9. Extending Toward Real Devices

Replace `simulate_row()` with ingestion:
- MQTT subscribe (background thread → queue → drain on interval).
- REST polling (requests every interval).
- Serial sensor read (pyserial) inside the timed block.

Ensure thread-safety: store inbound raw readings in `st.session_state.buffer` then pop during scheduled sample window.

---

## 10. Roadmap Ideas

- SLA summary (time out-of-range pie).
- Email / webhook notifications.
- User auth & role-based dashboards.
- Multi-shipment selection (session-based dataset filter).
- Export PDF report.
- Geo-fenced alerts (entering hot zones).

---

## 11. License / Disclaimer

Simulation code is illustrative. Not validated for regulatory compliance (GDP / GxP). Replace with validated data acquisition stack for production.

---

## 12. Quick Reference (Advanced App State Keys)

| Key                   | Purpose                              |
|-----------------------|--------------------------------------|
| records               | List of sample dicts                 |
| running               | Start/Stop flag                      |
| point_index           | Sample counter                       |
| last_sample_time      | Timestamp of latest sample           |
| next_sample_time      | Scheduled next sampling time         |
| anomaly_baseline      | Rolling lists per metric             |
| last_alert_flags      | Previous alert state for debouncing  |

---

## 13. Minimal Run (One-Liners)

Create + run advanced app fresh:
```powershell
py -m venv .venv; .\.venv\Scripts\activate; pip install --upgrade pip streamlit pandas plotly pydeck; python -m streamlit run pharmas.py
```

---

Enjoy experimenting with both levels: start simple (`pharmasure.py`), then switch to real-time (
