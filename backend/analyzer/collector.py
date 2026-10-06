"""
analyzer/collector.py

Collects real-time system metrics for SysKernel-AI's anomaly detection model.
"""

import time
import psutil
from dataclasses import dataclass, asdict


@dataclass
class SystemSnapshot:
    timestamp: float
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    disk_read_bytes: int
    disk_write_bytes: int
    net_bytes_sent: int
    net_bytes_recv: int
    load_avg_1min: float
    process_count: int


def collect_snapshot() -> SystemSnapshot:
    """Grab a single point-in-time snapshot of key system metrics."""
    disk_io = psutil.disk_io_counters()
    net_io = psutil.net_io_counters()

    try:
        import os
        load_avg = os.getloadavg()[0]
    except (AttributeError, OSError):
        load_avg = psutil.cpu_percent(interval=None)

    return SystemSnapshot(
        timestamp=time.time(),
        cpu_percent=psutil.cpu_percent(interval=0.5),
        memory_percent=psutil.virtual_memory().percent,
        disk_percent=psutil.disk_usage("/").percent,
        disk_read_bytes=disk_io.read_bytes if disk_io else 0,
        disk_write_bytes=disk_io.write_bytes if disk_io else 0,
        net_bytes_sent=net_io.bytes_sent if net_io else 0,
        net_bytes_recv=net_io.bytes_recv if net_io else 0,
        load_avg_1min=load_avg,
        process_count=len(psutil.pids()),
    )


def stream_snapshots(interval_seconds: float = 2.0):
    """Generator that yields a SystemSnapshot every `interval_seconds`."""
    while True:
        yield collect_snapshot()
        time.sleep(interval_seconds)


if __name__ == "__main__":
    for i, snap in enumerate(stream_snapshots(interval_seconds=1.0)):
        print(asdict(snap))
        if i >= 4:
            break