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
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional


# --- Nginx combined-log format (the most common real-world log) ---
# Example line:
# 192.168.1.10 - alice [01/May/2026:12:00:01 +0000] "GET /api/v1/status HTTP/1.1" 200 1234
NGINX_PATTERN = re.compile(
    r'(?P<ip>\S+) \S+ (?P<user>\S+) \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\w+) (?P<path>\S+) \S+" '
    r'(?P<status>\d{3}) (?P<bytes>\d+|-)'
)

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
    raw: str  # original line kept for fallback display


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
    )


def iter_entries(lines: Iterable[str]) -> Generator[LogEntry, None, None]:
    """Generator: yields valid LogEntry objects; silently skips unparseable lines.
    Using a generator keeps memory usage flat for multi-GB log files."""
    for line in lines:
        entry = parse_nginx_line(line)
        if entry:
            yield entry


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def aggregate(entries: Iterable[LogEntry]) -> Dict:
    status_counts: Counter = Counter()
    path_counts: Counter = Counter()
    ip_counts: Counter = Counter()
    error_paths: Counter = Counter()
    total_bytes = 0
    total_lines = 0

    for e in entries:
        total_lines += 1
        total_bytes += e.bytes_sent
        status_counts[e.status] += 1
        path_counts[e.path] += 1
        ip_counts[e.ip] += 1
        if e.status >= 400:
            error_paths[e.path] += 1

    return {
        "total": total_lines,
        "total_bytes": total_bytes,
        "status_counts": status_counts,
        "path_counts": path_counts,
        "ip_counts": ip_counts,
        "error_paths": error_paths,
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


# ---------------------------------------------------------------------------
# Sample log generator (so you can run this script without a real log file)
# ---------------------------------------------------------------------------

SAMPLE_IPS = ["10.0.0.1", "10.0.0.2", "192.168.1.50", "172.16.0.10", "8.8.8.8"]
SAMPLE_PATHS = [
    "/api/v1/health", "/api/v1/status", "/api/v2/deploy", "/metrics",
    "/login", "/logout", "/api/v1/pods", "/api/v1/nodes", "/favicon.ico",
]
SAMPLE_STATUSES = [200, 200, 200, 200, 201, 301, 400, 401, 403, 404, 500, 503]


def generate_log_line() -> str:
    ip = random.choice(SAMPLE_IPS)
    path = random.choice(SAMPLE_PATHS)
    status = random.choice(SAMPLE_STATUSES)
    method = "GET" if status != 201 else "POST"
    nbytes = random.randint(100, 8192)
    return f'{ip} - - [01/May/2026:12:00:01 +0000] "{method} {path} HTTP/1.1" {status} {nbytes}'


def generate_sample_file(path: Path, n: int) -> None:
    with path.open("w") as f:
        for _ in range(n):
            f.write(generate_log_line() + "\n")
    print(f"Generated {n} log lines -> {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Nginx log analyzer")
    p.add_argument("--file", "-f", help="Log file to analyze (omit to read stdin)")
    p.add_argument("--generate", type=int, metavar="N",
                   help="Generate N sample log lines into sample.log and analyze them")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.generate:
        out = Path("sample.log")
        generate_sample_file(out, args.generate)
        source = out.open()
    elif args.file:
        source = Path(args.file).open()
    else:
        # Piped: cat access.log | python 03_log_analyzer.py
        source = sys.stdin

    with source:
        stats = aggregate(iter_entries(source))

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
