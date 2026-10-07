"""
frontend/app.py

Streamlit dashboard for SysKernel-AI. Talks to the FastAPI backend
(backend/main.py) over HTTP to show live system status, control
monitoring, and display the incident log.

Run with (while main.py / uvicorn is already running separately):
    streamlit run app.py
"""

import time
import requests
import streamlit as st
import pandas as pd

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="SysKernel-AI", page_icon="🛠️", layout="wide")

st.title("🛠️ SysKernel-AI")
st.caption("Automated, cloud-accelerated Linux diagnostic & self-healing agent")


def api_get(path: str):
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Could not reach backend at {API_BASE}{path} — is uvicorn running? ({e})")
        return None


def api_post(path: str):
    try:
        r = requests.post(f"{API_BASE}{path}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Could not reach backend at {API_BASE}{path} — is uvicorn running? ({e})")
        return None


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

col1, col2, col3 = st.columns([1, 1, 4])
with col1:
    if st.button("▶ Start Monitoring", use_container_width=True):
        result = api_post("/monitoring/start")
        if result:
            st.success(result.get("message", "Started."))
with col2:
    if st.button("■ Stop Monitoring", use_container_width=True):
        result = api_post("/monitoring/stop")
        if result:
            st.info(result.get("message", "Stopped."))

st.divider()

# ---------------------------------------------------------------------------
# Live status
# ---------------------------------------------------------------------------

status = api_get("/status")

if status:
    monitoring_active = status.get("monitoring_active", False)
    snapshot = status.get("latest_snapshot")
    incident_count = status.get("incident_count", 0)

    status_col, metrics_col = st.columns([1, 3])

    with status_col:
        if monitoring_active:
            st.success("🟢 Monitoring Active")
        else:
            st.warning("⚪ Monitoring Stopped")
        st.metric("Incidents Detected", incident_count)

    with metrics_col:
        if snapshot:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("CPU", f"{snapshot['cpu_percent']:.1f}%")
            m2.metric("Memory", f"{snapshot['memory_percent']:.1f}%")
            m3.metric("Disk", f"{snapshot['disk_percent']:.1f}%")
            m4.metric("Processes", snapshot['process_count'])
        else:
            st.info("No snapshot yet — start monitoring or trigger a manual check below.")

st.divider()

# ---------------------------------------------------------------------------
# Manual check button (useful for demo - instant feedback without waiting
# for the poll loop)
# ---------------------------------------------------------------------------

if st.button("🔍 Run Check Now"):
    result = api_post("/check-now") or api_get("/check-now")  # check-now is POST
    if result is None:
        pass
    else:
        if result.get("is_anomaly"):
            st.error(f"ANOMALY: {result['reason']}")
            st.write(f"Action: **{result.get('action_requested') or 'none'}** — {result['notes']}")
        else:
            st.success("System normal.")

st.divider()

# ---------------------------------------------------------------------------
# Incident log
# ---------------------------------------------------------------------------

st.subheader("📋 Recent Incidents")

incidents = api_get("/incidents?limit=20")

if incidents:
    df = pd.DataFrame(incidents)
    df = df[["timestamp", "reason", "action_requested", "executed", "notes"]]
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No incidents logged yet.")

# ---------------------------------------------------------------------------
# Auto-refresh every 3 seconds so the dashboard feels live
# ---------------------------------------------------------------------------

time.sleep(3)
st.rerun()