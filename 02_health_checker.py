#!/usr/bin/env python3
"""
02_health_checker.py - Concurrent HTTP Health Checker
Checks a list of service endpoints in parallel and reports status.
SRE use-case: synthetic monitoring, readiness probes, on-call scripts.

Concepts: threading, queue, requests, argparse, dataclasses, typing
Run: python 02_health_checker.py
Run with a custom URL file: python 02_health_checker.py --urls-file urls.txt --workers 5
"""

import argparse
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import requests
except ImportError:
    raise SystemExit("pip install requests")


# --- Sensible defaults: a mix of real public endpoints and one that will fail ---
DEFAULT_URLS = [
    "https://httpbin.org/status/200",
    "https://httpbin.org/status/503",
    "https://httpbin.org/delay/1",
    "https://httpbin.org/get",
    "https://httpbin.org/status/404",
    "https://this-host-does-not-exist.example.com/health",
]


@dataclass
class CheckResult:
    url: str
    status_code: Optional[int] = None
    latency_ms: float = 0.0
    error: Optional[str] = None

    @property
    def healthy(self) -> bool:
        # 2xx is healthy; anything else (including errors) is not
        return self.status_code is not None and 200 <= self.status_code < 300

    def __str__(self) -> str:
        if self.error:
            return f"  ERROR  {self.url}  [{self.error}]"
        label = "  OK   " if self.healthy else " FAIL  "
        return f"{label} {self.status_code}  {self.latency_ms:6.0f}ms  {self.url}"


def check_url(url: str, timeout: float = 5.0) -> CheckResult:
    """Single blocking HTTP GET.  Returns a CheckResult regardless of outcome."""
    start = time.monotonic()
    try:
        # stream=False is default; we just want headers and status quickly
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        latency = (time.monotonic() - start) * 1000
        return CheckResult(url=url, status_code=resp.status_code, latency_ms=latency)
    except requests.exceptions.ConnectionError as e:
        return CheckResult(url=url, error=f"ConnectionError: {e}")
    except requests.exceptions.Timeout:
        return CheckResult(url=url, error=f"Timeout after {timeout}s")
    except requests.exceptions.RequestException as e:
        return CheckResult(url=url, error=str(e))


def worker(url_queue: queue.Queue, result_queue: queue.Queue, timeout: float) -> None:
    """Thread target: pull URLs from url_queue, push results to result_queue."""
    while True:
        try:
            # block=False raises queue.Empty immediately if nothing is left
            url = url_queue.get(block=False)
        except queue.Empty:
            return
        result = check_url(url, timeout=timeout)
        result_queue.put(result)
        url_queue.task_done()


def run_checks(urls: List[str], workers: int = 4, timeout: float = 5.0) -> List[CheckResult]:
    """Fan-out URL checks across a thread pool, collect and return results."""
    url_queue: queue.Queue = queue.Queue()
    result_queue: queue.Queue = queue.Queue()

    for url in urls:
        url_queue.put(url)

    threads = []
    # min() so we don't spin up 10 threads for 2 URLs
    for _ in range(min(workers, len(urls))):
        t = threading.Thread(target=worker, args=(url_queue, result_queue, timeout), daemon=True)
        t.start()
        threads.append(t)

    # Wait for all threads to finish
    for t in threads:
        t.join()

    results = []
    while not result_queue.empty():
        results.append(result_queue.get())

    # Sort so healthy URLs appear first, then by URL name
    results.sort(key=lambda r: (not r.healthy, r.url))
    return results


def load_urls_from_file(path: str) -> List[str]:
    """Read one URL per line; skip blank lines and # comments."""
    with open(path) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Concurrent HTTP health checker")
    p.add_argument("--urls-file", help="Text file with one URL per line")
    p.add_argument("--workers", type=int, default=4, help="Parallel check threads")
    p.add_argument("--timeout", type=float, default=5.0, help="Per-request timeout (s)")
    p.add_argument("--watch", type=float, default=0, help="Re-run every N seconds (0=once)")
    return p.parse_args()


def print_report(results: List[CheckResult]) -> None:
    healthy = sum(1 for r in results if r.healthy)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"Health Check  {healthy}/{total} healthy  ({time.strftime('%H:%M:%S')})")
    print(f"{'='*60}")
    for r in results:
        print(r)
    if healthy < total:
        print(f"\n  *** {total - healthy} endpoint(s) UNHEALTHY ***")


def main() -> None:
    args = parse_args()

    if args.urls_file:
        urls = load_urls_from_file(args.urls_file)
    else:
        urls = DEFAULT_URLS
        print(f"No --urls-file given; using {len(urls)} built-in test URLs\n")

    try:
        while True:
            results = run_checks(urls, workers=args.workers, timeout=args.timeout)
            print_report(results)
            if not args.watch:
                break
            time.sleep(args.watch)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()


# =============================================================================
# EXERCISES
# =============================================================================
# 1. BUG: If --watch is used and a URL is added to the list between iterations,
#    the new URL will never be checked.  Modify load_urls_from_file so it re-reads
#    the file on every iteration in watch mode.
#
# 2. EXPAND: Add a --retries N flag so a failed URL is retried up to N times
#    before being recorded as unhealthy.  Use exponential back-off (0.5s, 1s, 2s).
#
# 3. EXPAND: Track consecutive failures per URL and only print "ALERT" once it
#    has failed more than a threshold (e.g., 3 times in a row).
#
# 4. EXPAND: Replace threading with asyncio + aiohttp (see 07_async_health.py)
#    and compare performance against this version for 50 URLs.
#
# 5. THINK: This script uses daemon=True threads.  What does daemon mean here
#    and what happens to in-flight requests if the main thread exits?
