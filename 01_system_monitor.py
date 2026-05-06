#!/usr/bin/env python3
"""
01_system_monitor.py - System Resource Monitor
An SRE staple: poll CPU, memory, and disk and alert when thresholds are breached.

Concepts: classes, properties, dataclasses, loops, f-strings, datetime, psutil
Run: python 01_system_monitor.py
Run with custom interval: python 01_system_monitor.py --interval 2 --count 5
"""

import argparse
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List


# --- Try importing psutil; fall back with a clear message ---
try:
    import psutil
except ImportError:
    raise SystemExit("Install psutil first:  pip install psutil")


# --- Data model for a single snapshot of system state ---
@dataclass
class Snapshot:
    timestamp: datetime
    cpu_pct: float
    mem_pct: float
    disk_pct: float
    # field(default_factory=...) avoids the mutable-default-argument trap
    alerts: List[str] = field(default_factory=list)

    def is_healthy(self) -> bool:
        return len(self.alerts) == 0

    def summary(self) -> str:
        status = "OK" if self.is_healthy() else "ALERT"
        ts = self.timestamp.strftime("%H:%M:%S")
        return (
            f"[{ts}] {status:5s} | "
            f"CPU {self.cpu_pct:5.1f}% | "
            f"MEM {self.mem_pct:5.1f}% | "
            f"DISK {self.disk_pct:5.1f}%"
            + (f"  !! {', '.join(self.alerts)}" if self.alerts else "")
        )


class SystemMonitor:
    """Collects system metrics and checks them against configurable thresholds."""

    def __init__(
        self,
        cpu_threshold: float = 80.0,
        mem_threshold: float = 85.0,
        disk_threshold: float = 90.0,
        disk_path: str = "/",
    ):
        self.cpu_threshold = cpu_threshold
        self.mem_threshold = mem_threshold
        self.disk_threshold = disk_threshold
        self.disk_path = disk_path
        self._history: List[Snapshot] = []

    def collect(self) -> Snapshot:
        # psutil.cpu_percent(interval=None) returns usage since last call;
        # the first call returns 0.0 - use interval=1 for a blocking reading.
        cpu = psutil.cpu_percent(interval=1)
        # breakpoint()          # execution stops HERE, drops you into pdb
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage(self.disk_path).percent

        alerts = []
        if cpu > self.cpu_threshold:
            alerts.append(f"CPU>{self.cpu_threshold}%")
        if mem > self.mem_threshold:
            alerts.append(f"MEM>{self.mem_threshold}%")
        if disk > self.disk_threshold:
            alerts.append(f"DISK>{self.disk_threshold}%")

        snap = Snapshot(
            timestamp=datetime.now(),
            cpu_pct=cpu,
            mem_pct=mem,
            disk_pct=disk,
            alerts=alerts,
        )
        self._history.append(snap)
        return snap

    def average_cpu(self) -> float:
        """Return mean CPU % across all collected snapshots."""
        samples = self._history[1:]   # skip index 0 — psutil returns 0.0 on first call
        if not samples:
            return 0.0
        # List comprehension - idiomatic Python
        return sum(s.cpu_pct for s in samples) / len(samples)

    def alert_count(self) -> int:
        return sum(1 for s in self._history if not s.is_healthy())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="System resource monitor")
    p.add_argument("--interval", type=float, default=5.0, help="Seconds between polls")
    p.add_argument("--count", type=int, default=0, help="Stop after N samples (0=run forever)")
    p.add_argument("--cpu-warn", type=float, default=80.0)
    p.add_argument("--mem-warn", type=float, default=85.0)
    p.add_argument("--disk-warn", type=float, default=90.0)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    monitor = SystemMonitor(
        cpu_threshold=args.cpu_warn,
        mem_threshold=args.mem_warn,
        disk_threshold=args.disk_warn,
    )

    print(f"Monitoring system every {args.interval}s  (Ctrl-C to stop)\n")
    iteration = 0
    try:
        while True:
            snap = monitor.collect()
            print(snap.summary())
            iteration += 1
            if args.count and iteration >= args.count:
                break
            time.sleep(max(0, args.interval - 1))  # cpu_percent already slept 1s
    except KeyboardInterrupt:
        pass

    print(f"\n--- Summary ---")
    print(f"Samples     : {len(monitor._history)}")
    print(f"Avg CPU     : {monitor.average_cpu():.1f}%")
    print(f"Alert iters : {monitor.alert_count()}")


if __name__ == "__main__":
    main()


# =============================================================================
# EXERCISES
# =============================================================================
# 1. BUG: The `average_cpu` method divides by len(self._history) but there's a
#    subtle issue when interval=1 and count=1.  What does psutil return on the
#    very first cpu_percent call and why?  Fix it so the first sample is skipped.
#
# 2. EXPAND: Add per-CPU-core breakdown using psutil.cpu_percent(percpu=True).
#    Print a mini bar graph: "Core 0: ████░░░░ 52%"
#
# 3. EXPAND: Add network I/O tracking (psutil.net_io_counters) and report
#    bytes sent/received per interval rather than cumulative totals.
#
# 4. EXPAND: Write snapshots to a CSV file using the `csv` stdlib module so
#    you can import them into a spreadsheet later.
#
# 5. THINK: In production you'd push metrics to Prometheus via
#    prometheus_client. How would you add a /metrics HTTP endpoint here
#    without blocking the poll loop?  (Hint: threading.Thread)
