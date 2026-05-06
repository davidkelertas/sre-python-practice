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


def _bar(pct: float, width: int = 20) -> str:
    """ASCII progress bar: _bar(50) -> '##########----------'"""
    filled = round(pct / 100 * width)
    return "#" * filled + "-" * (width - filled)


def _spin_worker(duration_s: float) -> None:
    """Burn one core for duration_s seconds. Must be a top-level function so
    multiprocessing can pickle it on all platforms."""
    end = time.monotonic() + duration_s
    while time.monotonic() < end:
        _ = 99999 ** 7


def burn_cpu(duration_s: float = 0.8) -> None:
    """Saturate every logical core using multiprocessing.
    threading cannot do this — the GIL only lets one thread run Python at a time.
    Each Process gets its own interpreter and its own GIL."""
    import multiprocessing
    procs = [
        multiprocessing.Process(target=_spin_worker, args=(duration_s,))
        for _ in range(psutil.cpu_count(logical=True))
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join()


# --- Data model for a single snapshot of system state ---
@dataclass
class Snapshot:
    timestamp: datetime
    cpu_pct: float          # average across all cores
    mem_pct: float
    disk_pct: float
    core_pcts: List[float] = field(default_factory=list)
    net_tx_kb: float = 0.0   # KB/s sent this interval
    net_rx_kb: float = 0.0   # KB/s received this interval
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
            f"DISK {self.disk_pct:5.1f}% | "
            f"TX {self.net_tx_kb:7.1f} KB/s | "
            f"RX {self.net_rx_kb:7.1f} KB/s"
            + (f"  !! {', '.join(self.alerts)}" if self.alerts else "")
        )

    def core_summary(self) -> str:
        """Per-core bar graph lines, e.g.: Core 0: ##########---------- 52.0%"""
        return "\n".join(
            f"  Core {i}: {_bar(pct)} {pct:5.1f}%"
            for i, pct in enumerate(self.core_pcts)
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
        # Seed with current counters so the first delta is meaningful
        self._prev_net = psutil.net_io_counters()
        self._prev_net_time = time.monotonic()

    def collect(self) -> Snapshot:
        # psutil.cpu_percent(interval=None) returns usage since last call;
        # the first call returns 0.0 - use interval=1 for a blocking reading.
        # percpu=True returns one float per core; average that for threshold checks
        core_pcts = psutil.cpu_percent(percpu=True, interval=1)
        cpu = sum(core_pcts) / len(core_pcts)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage(self.disk_path).percent

        # Network delta: subtract previous cumulative counters to get per-interval rate
        now_net = psutil.net_io_counters()
        now_time = time.monotonic()
        elapsed = now_time - self._prev_net_time or 1.0   # guard against zero
        tx_kb = (now_net.bytes_sent - self._prev_net.bytes_sent) / 1024 / elapsed
        rx_kb = (now_net.bytes_recv - self._prev_net.bytes_recv) / 1024 / elapsed
        self._prev_net = now_net
        self._prev_net_time = now_time

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
            core_pcts=core_pcts,
            net_tx_kb=max(0.0, tx_kb),
            net_rx_kb=max(0.0, rx_kb),
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
            if iteration % 2 == 1:   # odd iterations: spike all cores before sampling
                print("  [load] burning CPU...")
                burn_cpu(duration_s=0.8)

            snap = monitor.collect()
            label = " *LOAD*" if iteration % 2 == 1 else ""
            print(snap.summary() + label)
            print(snap.core_summary())
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
#
# python -m pdb 01_system_monitor.py
# n         next line
# s         step into
# c         continue
# r         return from function
# q         quit
# l         list source
# w         call stack
# u / d     up/down the stack
# b 42      set breakpoint at line 42
# cl 1      clear breakpoint 1
# p expr    print expression
# pp expr   pretty-print