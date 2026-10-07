"""
analyzer/model.py
 
Rolling z-score anomaly detector for SysKernel-AI.
 
Keeps a short rolling window of recent SystemSnapshots per metric,
and flags a new snapshot as anomalous if any metric deviates sharply
(beyond `z_threshold` standard deviations) from the recent baseline.
 
This is deliberately simple and explainable for the hackathon demo.
A GPU-accelerated autoencoder can be swapped in later (see NOTE at
bottom) to justify the AMD/ROCm compute requirement more directly.
"""
 
from collections import deque
from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Deque, List, Optional
 
from analyzer.collector import SystemSnapshot
 
# Metrics we actually monitor for anomalies (skip timestamp/counters
# that only make sense as deltas, not raw values, for a first pass).
MONITORED_FIELDS = [
    "cpu_percent",
    "memory_percent",
    "disk_percent",
    "load_avg_1min",
    "process_count",
]
 
 
@dataclass
class AnomalyResult:
    is_anomaly: bool
    anomalous_fields: List[str]
    z_scores: dict
    snapshot: SystemSnapshot
    reason: str
 
 
class RollingAnomalyDetector:
    def __init__(self, window_size: int = 30, z_threshold: float = 3.0, min_samples: int = 10):
        """
        window_size: how many recent snapshots to keep as the baseline
        z_threshold: how many standard deviations counts as anomalous
        min_samples: don't flag anomalies until we have at least this
                     many samples (avoids false positives on startup)
        """
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.min_samples = min_samples
        self.history: Deque[SystemSnapshot] = deque(maxlen=window_size)
 
    def _z_score(self, field_name: str, value: float) -> Optional[float]:
        values = [getattr(s, field_name) for s in self.history]
        if len(values) < self.min_samples:
            return None
        avg = mean(values)
        try:
            sd = stdev(values)
        except Exception:
            sd = 0.0
        if sd == 0:
            return 0.0
        return (value - avg) / sd
 
    def check(self, snapshot: SystemSnapshot) -> AnomalyResult:
        """Check a new snapshot against the rolling baseline, then add it to history."""
        z_scores = {}
        anomalous_fields = []
 
        for field_name in MONITORED_FIELDS:
            value = getattr(snapshot, field_name)
            z = self._z_score(field_name, value)
            z_scores[field_name] = z
            if z is not None and abs(z) >= self.z_threshold:
                anomalous_fields.append(field_name)
 
        is_anomaly = len(anomalous_fields) > 0
 
        if len(self.history) < self.min_samples:
            reason = f"Warming up baseline ({len(self.history)}/{self.min_samples} samples)"
            is_anomaly = False
        elif is_anomaly:
            parts = [f"{f} (z={z_scores[f]:.2f})" for f in anomalous_fields]
            reason = "Anomalous: " + ", ".join(parts)
        else:
            reason = "Normal"
 
        # Add this snapshot to history AFTER checking, so it doesn't
        # influence its own z-score.
        self.history.append(snapshot)
 
        return AnomalyResult(
            is_anomaly=is_anomaly,
            anomalous_fields=anomalous_fields,
            z_scores=z_scores,
            snapshot=snapshot,
            reason=reason,
        )
 
 
if __name__ == "__main__":
    # Quick manual test using live collector data.
    from analyzer.collector import stream_snapshots
 
    detector = RollingAnomalyDetector(window_size=20, z_threshold=2.5, min_samples=8)
 
    print("Streaming snapshots and checking for anomalies (Ctrl+C to stop)...")
    for snap in stream_snapshots(interval_seconds=1.0):
        result = detector.check(snap)
        status = "ANOMALY" if result.is_anomaly else "ok"
        print(f"[{status}] cpu={snap.cpu_percent:.1f}% mem={snap.memory_percent:.1f}% -> {result.reason}")
 
# NOTE for later / AMD GPU upgrade path:
# Replace RollingAnomalyDetector with a small autoencoder (PyTorch) trained
# on "normal" snapshots; reconstruction error above a threshold = anomaly.
# Train/infer on the AMD Developer Cloud instance (ROCm) to satisfy the
# "meaningful AMD compute" requirement. Keep this z-score version as a
# fast, dependency-free fallback / baseline comparison in the demo.