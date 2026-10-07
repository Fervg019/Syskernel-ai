"""
agent/diagnoser.py

The orchestration loop: pulls live system snapshots, runs them through the
anomaly detector, and when something looks wrong, decides which allowlisted
action to request and routes it through the SafetyGuard before anything
actually executes.

This is the piece that turns "we noticed a problem" into "we took a safe,
bounded action about it" - the core SysKernel-AI loop.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from analyzer.collector import SystemSnapshot, stream_snapshots
from analyzer.model import RollingAnomalyDetector, AnomalyResult
from agent.safety import (
    SafetyGuard,
    ActionRequest,
    ActionDecision,
    DEFAULT_ALLOWLIST,
)


@dataclass
class IncidentLogEntry:
    timestamp: datetime
    anomaly: AnomalyResult
    action_requested: Optional[str]
    decision: Optional[ActionDecision]
    executed: bool
    notes: str = ""


class Diagnoser:
    """
    Ties detection + safety together. Call `handle_snapshot()` for each new
    SystemSnapshot (e.g. from collector.stream_snapshots()).
    """

    def __init__(self, detector: RollingAnomalyDetector = None, guard: SafetyGuard = None):
        self.detector = detector or RollingAnomalyDetector()
        self.guard = guard or SafetyGuard(DEFAULT_ALLOWLIST)
        self.incident_log: List[IncidentLogEntry] = []

    def choose_action(self, anomaly: AnomalyResult) -> Optional[ActionRequest]:
        """
        Very simple rule-based mapping from anomalous field -> candidate action.
        This is intentionally explicit/explainable for the demo, rather than
        an opaque model decision - judges can see exactly why an action was
        chosen.
        """
        fields = set(anomaly.anomalous_fields)

        if "memory_percent" in fields:
            return ActionRequest(
                action_name="restart_service",
                params={"service_name": "demo-app"},  # TODO: map to the real affected service
            )
        if "cpu_percent" in fields or "load_avg_1min" in fields:
            return ActionRequest(
                action_name="scale_replica",
                params={"service_name": "demo-app", "replicas": 2},
            )
        if "disk_percent" in fields:
            return ActionRequest(
                action_name="clear_temp_cache",
                params={"path": "/tmp/demo-cache"},  # TODO: real, validated path
            )
        # process_count spikes or anything else: no safe automated action yet,
        # just log it for a human to look at.
        return None

    def handle_snapshot(self, snapshot: SystemSnapshot) -> IncidentLogEntry:
        anomaly = self.detector.check(snapshot)

        if not anomaly.is_anomaly:
            entry = IncidentLogEntry(
                timestamp=datetime.now(timezone.utc),
                anomaly=anomaly,
                action_requested=None,
                decision=None,
                executed=False,
                notes="No anomaly.",
            )
            self.incident_log.append(entry)
            return entry

        request = self.choose_action(anomaly)

        if request is None:
            entry = IncidentLogEntry(
                timestamp=datetime.now(timezone.utc),
                anomaly=anomaly,
                action_requested=None,
                decision=None,
                executed=False,
                notes="Anomaly detected but no safe automated action mapped - flagged for human review.",
            )
            self.incident_log.append(entry)
            return entry

        decision = self.guard.check_action(request)
        executed = False
        notes = decision.reason

        if decision.approved:
            action_def = self.guard.allowlist[request.action_name]
            result = action_def.handler(**request.params)
            self.guard.record_executed()
            executed = True
            notes = f"{decision.reason} | Result: {result}"
        elif decision.requires_human_approval:
            notes = f"{decision.reason} | Awaiting human approval (not executed)."
        else:
            notes = f"{decision.reason} | Action blocked."

        entry = IncidentLogEntry(
            timestamp=datetime.now(timezone.utc),
            anomaly=anomaly,
            action_requested=request.action_name,
            decision=decision,
            executed=executed,
            notes=notes,
        )
        self.incident_log.append(entry)
        return entry


if __name__ == "__main__":
    diagnoser = Diagnoser()

    print("SysKernel-AI diagnoser running (Ctrl+C to stop)...")
    for snapshot in stream_snapshots(interval_seconds=1.0):
        entry = diagnoser.handle_snapshot(snapshot)
        if entry.anomaly.is_anomaly:
            print(f"\n[{entry.timestamp.isoformat()}] ANOMALY: {entry.anomaly.reason}")
            print(f"  -> {entry.notes}")
        else:
            print(".", end="", flush=True)