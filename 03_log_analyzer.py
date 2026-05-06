#!/usr/bin/env python3
"""
03_log_analyzer.py - Log File Analyzer
Parse structured (JSON) and unstructured (nginx/syslog) log lines,
aggregate stats, and surface anomalies.

Concepts: regex, generators, pathlib, collections.Counter, dataclasses,
          context managers, argparse, stdin piping
Run (generate sample logs first): python 03_log_analyzer.py --generate 500
Run (analyze):                     python 03_log_analyzer.py --file sample.log
Pipe mode:                         cat sample.log | python 03_log_analyzer.py
"""

import argparse
import json
import random
import re
import sys
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional, Tuple


# --- Nginx combined-log format (the most common real-world log) ---
# Example line (IPv4):  192.168.1.10 - alice [01/May/2026:12:00:01 +0000] "GET /path HTTP/1.1" 200 1234
# Example line (IPv6):  ::1 - - [01/May/2026:12:00:01 +0000] "GET /path HTTP/1.1" 200 1234
# Example line (IPv6 bracketed): [2001:db8::1] - - [01/May/2026:12:00:01 +0000] "GET /path HTTP/1.1" 200 1234
#
# BUG FIX #1: The original \S+ IP group matches bare IPv6 (::1) but fails on
# the bracketed form [2001:db8::1] that some nginx configs emit. The new
# alternation (?:\[[^\]]+\]|\S+) matches either form.
NGINX_PATTERN = re.compile(
    r'(?P<ip>(?:\[[^\]]+\]|\S+)) \S+ (?P<user>\S+) \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\w+) (?P<path>\S+) \S+" '
    r'(?P<status>\d{3}) (?P<bytes>\d+|-)'
)

# Verify the fix with an assertion so regressions are caught immediately
assert NGINX_PATTERN.match('::1 - - [01/May/2026:12:00:01 +0000] "GET / HTTP/1.1" 200 100')
assert NGINX_PATTERN.match('[2001:db8::1] - - [01/May/2026:12:00:01 +0000] "GET / HTTP/1.1" 200 100')
assert NGINX_PATTERN.match('192.168.1.10 - alice [01/May/2026:12:00:01 +0000] "GET / HTTP/1.1" 200 100')

# --- JSON log format (common in cloud-native apps) ---
# Example: {"level": "ERROR", "msg": "db timeout", "svc": "api", "ts": 1714905600}


@dataclass
class LogEntry:
    ip: str
    user: str
    method: str
    path: str
    status: int
    bytes_sent: int
    raw: str                  # original line kept for fallback display
    timestamp_str: str = ""   # nginx time string, used for burst detection


def parse_nginx_line(line: str) -> Optional[LogEntry]:
    """Return a LogEntry or None if the line doesn't match."""
    m = NGINX_PATTERN.match(line.strip())
    if not m:
        return None
    return LogEntry(
        ip=m.group("ip"),
        user=m.group("user"),
        method=m.group("method"),
        path=m.group("path"),
        status=int(m.group("status")),
        bytes_sent=int(m.group("bytes")) if m.group("bytes") != "-" else 0,
        raw=line.strip(),
        timestamp_str=m.group("time"),
    )


def parse_json_line(line: str) -> Optional[LogEntry]:
    """EXPAND #4: parse a JSON log line.
    Expected keys: level, msg, svc (optional), status (optional), path (optional).
    Maps ERROR/WARN levels to 5xx/4xx status codes if no explicit status given."""
    try:
        data = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    level = data.get("level", "INFO").upper()
    status = data.get("status") or (500 if level == "ERROR" else (400 if level == "WARN" else 200))
    return LogEntry(
        ip=data.get("ip", "-"),
        user=data.get("user", "-"),
        method=data.get("method", "GET"),
        path=data.get("path", data.get("msg", "/unknown")),
        status=int(status),
        bytes_sent=int(data.get("bytes", 0)),
        raw=line.strip(),
        timestamp_str=str(data.get("ts", "")),
    )


def iter_entries(lines: Iterable[str]) -> Generator[LogEntry, None, None]:
    """Generator: yields valid LogEntry objects; silently skips unparseable lines.
    Tries JSON first, then nginx format. Using a generator keeps memory flat
    for multi-GB log files (see THINK #5 in exercises)."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Try JSON first (cloud-native apps), fall back to nginx format
        entry = parse_json_line(line) or parse_nginx_line(line)
        if entry:
            yield entry


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

NGINX_TS_FMT = "%d/%b/%Y:%H:%M:%S %z"
BURST_WINDOW_S = 60
BURST_THRESHOLD = 10


def _parse_ts(ts_str: str) -> Optional[float]:
    """Parse nginx timestamp to a Unix epoch float. Returns None if unparseable."""
    try:
        return datetime.strptime(ts_str, NGINX_TS_FMT).timestamp()
    except (ValueError, TypeError):
        return None


def aggregate(entries: Iterable[LogEntry]) -> Dict:
    status_counts: Counter = Counter()
    path_counts: Counter = Counter()
    ip_counts: Counter = Counter()
    error_paths: Counter = Counter()
    total_bytes = 0
    total_lines = 0
    # EXPAND #3: sliding deque of (timestamp, path) for error-burst detection
    error_window: deque = deque()   # holds float timestamps of recent errors
    bursts: List[str] = []         # human-readable burst warnings

    for e in entries:
        total_lines += 1
        total_bytes += e.bytes_sent
        status_counts[e.status] += 1
        path_counts[e.path] += 1
        ip_counts[e.ip] += 1
        if e.status >= 400:
            error_paths[e.path] += 1
            ts = _parse_ts(e.timestamp_str)
            if ts is not None:
                error_window.append(ts)
                # Prune entries older than BURST_WINDOW_S
                cutoff = ts - BURST_WINDOW_S
                while error_window and error_window[0] < cutoff:
                    error_window.popleft()
                if len(error_window) == BURST_THRESHOLD + 1:
                    # Crossed the threshold: record once per burst onset
                    bursts.append(
                        f"  BURST: {BURST_THRESHOLD}+ errors in {BURST_WINDOW_S}s "
                        f"window ending at {e.timestamp_str}"
                    )

    return {
        "total": total_lines,
        "total_bytes": total_bytes,
        "status_counts": status_counts,
        "path_counts": path_counts,
        "ip_counts": ip_counts,
        "error_paths": error_paths,
        "bursts": bursts,
    }


def print_report(stats: Dict) -> None:
    print(f"\n{'='*50}")
    print(f"  Log Analysis Report")
    print(f"{'='*50}")
    print(f"  Total requests : {stats['total']:,}")
    print(f"  Total bytes    : {stats['total_bytes']:,}")

    print(f"\n  Status codes:")
    for code, count in sorted(stats["status_counts"].items()):
        bar = "#" * min(count // max(stats["total"] // 40, 1), 40)
        label = "ERROR" if code >= 500 else ("WARN" if code >= 400 else "    ")
        print(f"    {code} {label}  {bar} {count}")

    print(f"\n  Top 5 paths:")
    for path, count in stats["path_counts"].most_common(5):
        print(f"    {count:5d}  {path}")

    print(f"\n  Top 5 client IPs:")
    for ip, count in stats["ip_counts"].most_common(5):
        print(f"    {count:5d}  {ip}")

    if stats["error_paths"]:
        print(f"\n  Paths with most errors (4xx/5xx):")
        for path, count in stats["error_paths"].most_common(5):
            print(f"    {count:5d}  {path}")

    if stats.get("bursts"):
        print(f"\n  Error bursts detected:")
        for b in stats["bursts"]:
            print(b)


# ---------------------------------------------------------------------------
# Sample log generator (so you can run this script without a real log file)
# ---------------------------------------------------------------------------

SAMPLE_IPS = ["10.0.0.1", "10.0.0.2", "192.168.1.50", "172.16.0.10", "8.8.8.8"]
SAMPLE_PATHS = [
    "/api/v1/health", "/api/v1/status", "/api/v2/deploy", "/metrics",
    "/login", "/logout", "/api/v1/pods", "/api/v1/nodes", "/favicon.ico",
]
SAMPLE_STATUSES = [200, 200, 200, 200, 201, 301, 400, 401, 403, 404, 500, 503]


def generate_log_line(second_offset: int = 0) -> str:
    ip = random.choice(SAMPLE_IPS)
    path = random.choice(SAMPLE_PATHS)
    status = random.choice(SAMPLE_STATUSES)
    method = "GET" if status != 201 else "POST"
    nbytes = random.randint(100, 8192)
    # Vary timestamps so burst detection has real time data to work with
    ts = datetime(2026, 5, 1, 12, second_offset // 60, second_offset % 60, tzinfo=timezone.utc)
    ts_str = ts.strftime("%d/%b/%Y:%H:%M:%S +0000")
    return f'{ip} - - [{ts_str}] "{method} {path} HTTP/1.1" {status} {nbytes}'


def generate_sample_file(path: Path, n: int) -> None:
    with path.open("w") as f:
        for i in range(n):
            f.write(generate_log_line(second_offset=i) + "\n")
    print(f"Generated {n} log lines -> {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def tail_lines(path: Path, n: int) -> List[str]:
    """EXPAND #2: read only the last N lines without loading the whole file.
    deque(maxlen=N) auto-discards old lines as new ones are added — O(1) memory."""
    with path.open() as f:
        return list(deque(f, maxlen=n))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Nginx log analyzer")
    p.add_argument("--file", "-f", help="Log file to analyze (omit to read stdin)")
    p.add_argument("--generate", type=int, metavar="N",
                   help="Generate N sample log lines into sample.log and analyze them")
    p.add_argument("--tail", type=int, metavar="N",
                   help="Analyze only the last N lines (requires --file)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.generate:
        out = Path("sample.log")
        generate_sample_file(out, args.generate)
        lines: Iterable[str] = out.open()
    elif args.tail and args.file:
        # EXPAND #2: tail mode — only look at last N lines, never reads full file into RAM
        lines = tail_lines(Path(args.file), args.tail)
        print(f"Analyzing last {args.tail} lines of {args.file}\n")
    elif args.file:
        lines = Path(args.file).open()
    else:
        lines = sys.stdin

    # Must close file handles when we're done; a context manager handles that
    source = lines if hasattr(lines, "close") else None
    try:
        stats = aggregate(iter_entries(lines))
    finally:
        if source and hasattr(source, "close"):
            source.close()

    print_report(stats)


if __name__ == "__main__":
    main()


# =============================================================================
# EXERCISES
# =============================================================================
# 1. BUG: The NGINX_PATTERN doesn't handle IPv6 addresses like "::1".
#    Update the regex so it also matches IPv6 and verify with a test line.
#
# 2. EXPAND: Add a --tail N flag that only analyzes the last N lines of the
#    file without reading the whole file into memory.  (Hint: collections.deque)
#
# 3. EXPAND: Detect "error bursts": if more than 10 errors occur in any
#    60-second window, print a warning.  You'll need to parse the timestamp.
#
# 4. EXPAND: Support JSON log lines alongside nginx format.  If json.loads()
#    succeeds, extract level/msg/svc; otherwise try the nginx regex.
#
# 5. THINK: iter_entries is a generator.  What would happen to memory usage
#    if you changed it to return a list instead?  Why does that matter for
#    a 10 GB log file on a pod with 512 MB RAM?
#
#    ANSWER: A generator yields one LogEntry at a time and discards it after
#    the consumer (aggregate) is done with it.  At any moment only one parsed
#    line is alive in memory alongside the running totals in Counter objects.
#    Total RAM usage is O(unique_keys) — tiny.
#
#    If iter_entries returned a list, Python would materialise ALL parsed lines
#    before aggregate() even starts.  A 10 GB log file with ~100 million lines
#    and ~200-byte LogEntry objects would need ~20 GB of RAM — the pod would
#    be OOM-killed almost immediately.
#
#    The generator pattern is idiomatic Python for streaming large inputs:
#    the `yield` keyword suspends execution and hands control back to the
#    caller, which processes one item, then resumes the generator for the next.
