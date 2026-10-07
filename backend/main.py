"""
backend/main.py

FastAPI app exposing SysKernel-AI's monitoring loop over HTTP so the
Streamlit frontend (or anything else) can start/stop monitoring, pull
live status, and view the incident log.

Run with:
    uvicorn main:app --reload --port 8000
"""

import asyncio
from dataclasses import asdict
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analyzer.collector import collect_snapshot
from agent.diagnoser import Diagnoser, IncidentLogEntry

app = FastAPI(title="SysKernel-AI", version="0.1.0")

# Allow the Streamlit frontend (likely on a different port) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for a hackathon demo; tighten for real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

diagnoser = Diagnoser()

# Background monitoring loop state
_monitoring_task: Optional[asyncio.Task] = None
_monitoring_active = False
_poll_interval_seconds = 2.0


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class StatusResponse(BaseModel):
    monitoring_active: bool
    latest_snapshot: Optional[dict]
    latest_anomaly: Optional[bool]
    incident_count: int


class IncidentResponse(BaseModel):
    timestamp: str
    is_anomaly: bool
    reason: str
    action_requested: Optional[str]
    executed: bool
    notes: str


def _entry_to_response(entry: IncidentLogEntry) -> IncidentResponse:
    return IncidentResponse(
        timestamp=entry.timestamp.isoformat(),
        is_anomaly=entry.anomaly.is_anomaly,
        reason=entry.anomaly.reason,
        action_requested=entry.action_requested,
        executed=entry.executed,
        notes=entry.notes,
    )


# ---------------------------------------------------------------------------
# Background monitoring loop
# ---------------------------------------------------------------------------

async def _monitor_loop():
    global _monitoring_active
    _monitoring_active = True
    try:
        while _monitoring_active:
            snapshot = collect_snapshot()
            diagnoser.handle_snapshot(snapshot)
            await asyncio.sleep(_poll_interval_seconds)
    finally:
        _monitoring_active = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"service": "SysKernel-AI", "status": "running"}


@app.post("/monitoring/start")
async def start_monitoring():
    global _monitoring_task
    if _monitoring_active:
        return {"message": "Monitoring already running."}
    _monitoring_task = asyncio.create_task(_monitor_loop())
    return {"message": "Monitoring started."}


@app.post("/monitoring/stop")
async def stop_monitoring():
    global _monitoring_active
    _monitoring_active = False
    return {"message": "Monitoring stopped."}


@app.get("/status", response_model=StatusResponse)
def get_status():
    latest_snapshot = None
    latest_anomaly = None

    if diagnoser.incident_log:
        last_entry = diagnoser.incident_log[-1]
        latest_snapshot = asdict(last_entry.anomaly.snapshot)
        latest_anomaly = last_entry.anomaly.is_anomaly

    return StatusResponse(
        monitoring_active=_monitoring_active,
        latest_snapshot=latest_snapshot,
        latest_anomaly=latest_anomaly,
        incident_count=sum(1 for e in diagnoser.incident_log if e.anomaly.is_anomaly),
    )


@app.get("/incidents", response_model=List[IncidentResponse])
def get_incidents(limit: int = 50):
    """Most recent incidents (anomalies only), newest first."""
    anomalies = [e for e in diagnoser.incident_log if e.anomaly.is_anomaly]
    recent = anomalies[-limit:][::-1]
    return [_entry_to_response(e) for e in recent]


@app.get("/log", response_model=List[IncidentResponse])
def get_full_log(limit: int = 100):
    """Full log including normal snapshots, newest first."""
    recent = diagnoser.incident_log[-limit:][::-1]
    return [_entry_to_response(e) for e in recent]


@app.post("/check-now", response_model=IncidentResponse)
def check_now():
    """Trigger a single immediate snapshot + check, outside the polling loop."""
    snapshot = collect_snapshot()
    entry = diagnoser.handle_snapshot(snapshot)
    return _entry_to_response(entry)