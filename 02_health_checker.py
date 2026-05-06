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
from typing import Dict, List, Optional

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


def check_url(url: str, timeout: float = 5.0, retries: int = 0) -> CheckResult:
    """Single blocking HTTP GET with optional retries and exponential back-off.
    Returns a CheckResult regardless of outcome."""
    # EXPAND #2: retry loop with exponential back-off (0.5s, 1s, 2s, ...)
    backoff = 0.5
    last_result: Optional[CheckResult] = None
    for attempt in range(retries + 1):
        if attempt > 0:
            time.sleep(backoff)
            backoff *= 2
        start = time.monotonic()
        try:
            resp = requests.get(url, timeout=timeout, allow_redirects=True)
            latency = (time.monotonic() - start) * 1000
            result = CheckResult(url=url, status_code=resp.status_code, latency_ms=latency)
        except requests.exceptions.ConnectionError as e:
            result = CheckResult(url=url, error=f"ConnectionError: {e}")
        except requests.exceptions.Timeout:
            result = CheckResult(url=url, error=f"Timeout after {timeout}s")
        except requests.exceptions.RequestException as e:
            result = CheckResult(url=url, error=str(e))
        last_result = result
        if result.healthy:
            return result
    return last_result  # type: ignore[return-value]


def worker(url_queue: queue.Queue, result_queue: queue.Queue, timeout: float, retries: int) -> None:
    """Thread target: pull URLs from url_queue, push results to result_queue."""
    while True:
        try:
            url = url_queue.get(block=False)
        except queue.Empty:
            return
        result = check_url(url, timeout=timeout, retries=retries)
        result_queue.put(result)
        url_queue.task_done()


def run_checks(
    urls: List[str],
    workers: int = 4,
    timeout: float = 5.0,
    retries: int = 0,
) -> List[CheckResult]:
    """Fan-out URL checks across a thread pool, collect and return results."""
    url_queue: queue.Queue = queue.Queue()
    result_queue: queue.Queue = queue.Queue()

    for url in urls:
        url_queue.put(url)

    threads = []
    for _ in range(min(workers, len(urls))):
        t = threading.Thread(
            target=worker,
            args=(url_queue, result_queue, timeout, retries),
            daemon=True,
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    results = []
    while not result_queue.empty():
        results.append(result_queue.get())

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
    # EXPAND #2: --retries flag
    p.add_argument("--retries", type=int, default=0, help="Retry count per URL on failure (exponential back-off)")
    # EXPAND #3: --alert-threshold flag
    p.add_argument(
        "--alert-threshold",
        type=int,
        default=3,
        help="Print ALERT after this many consecutive failures per URL (default: 3)",
    )
    return p.parse_args()


def print_report(
    results: List[CheckResult],
    consecutive_failures: Dict[str, int],
    alert_threshold: int,
) -> None:
    healthy = sum(1 for r in results if r.healthy)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"Health Check  {healthy}/{total} healthy  ({time.strftime('%H:%M:%S')})")
    print(f"{'='*60}")
    for r in results:
        print(r)
        # EXPAND #3: ALERT after N consecutive failures
        if not r.healthy:
            if consecutive_failures.get(r.url, 0) >= alert_threshold:
                print(f"  *** ALERT: {r.url} has failed {consecutive_failures[r.url]} times in a row ***")
    if healthy < total:
        print(f"\n  *** {total - healthy} endpoint(s) UNHEALTHY ***")


def main() -> None:
    args = parse_args()

    # EXPAND #3: track consecutive failures across watch iterations
    consecutive_failures: Dict[str, int] = {}

    try:
        while True:
            # BUG FIX #1: re-read the URLs file on every iteration so new URLs
            # added between watch cycles are picked up automatically.
            if args.urls_file:
                urls = load_urls_from_file(args.urls_file)
            else:
                urls = DEFAULT_URLS
                if not args.watch:
                    print(f"No --urls-file given; using {len(urls)} built-in test URLs\n")

            results = run_checks(
                urls,
                workers=args.workers,
                timeout=args.timeout,
                retries=args.retries,
            )

            # Update consecutive failure counts
            for r in results:
                if r.healthy:
                    consecutive_failures[r.url] = 0
                else:
                    consecutive_failures[r.url] = consecutive_failures.get(r.url, 0) + 1

            print_report(results, consecutive_failures, args.alert_threshold)

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
#    FIX: Moved the `load_urls_from_file` call (and the DEFAULT_URLS fallback)
#    inside the while-True loop so that every iteration re-evaluates the URL list.
#    Previously the list was loaded once before the loop, so any edits made to the
#    file while --watch was running were never picked up.
#
# 2. EXPAND: Add a --retries N flag so a failed URL is retried up to N times
#    before being recorded as unhealthy.  Use exponential back-off (0.5s, 1s, 2s).
#
#    IMPLEMENTED: check_url now accepts a `retries` parameter and loops up to
#    retries+1 times.  Between attempts it sleeps `backoff` seconds and doubles
#    it each time (0.5, 1.0, 2.0, …).  The --retries CLI flag threads the value
#    through run_checks → worker → check_url.
#
# 3. EXPAND: Track consecutive failures per URL and only print "ALERT" once it
#    has failed more than a threshold (e.g., 3 times in a row).
#
#    IMPLEMENTED: `consecutive_failures` dict is maintained in main().  After
#    each run_checks call it increments the counter for unhealthy URLs and resets
#    it to 0 when they recover.  print_report emits an ALERT line when the
#    counter reaches --alert-threshold (default 3).
#
# 4. EXPAND: Replace threading with asyncio + aiohttp (see 07_async_health.py)
#    and compare performance against this version for 50 URLs.
#
#    THREADING vs ASYNCIO COMPARISON:
#    For a small number of URLs (e.g., 6) the wall-clock time is similar: both
#    are bounded by the slowest network round-trip, and thread-creation overhead
#    is negligible.
#
#    For 50 URLs all pointing at httpbin.org/delay/1 (1-second latency each):
#    - Threading version: total time ≈ ceil(50 / workers) × 1s.
#      With --workers 4 that is ~13 s.  With --workers 50 it matches async.
#    - Asyncio version: all 50 coroutines are in-flight simultaneously (up to
#      --concurrency limit), so total time ≈ 1s regardless of URL count,
#      as long as concurrency >= 50.
#
#    The key difference is resource cost at scale.  Each OS thread consumes
#    ~8 MB of stack; 1000 threads = ~8 GB RAM.  Each asyncio coroutine costs
#    only a few KB.  For high-fan-out monitoring (thousands of endpoints) asyncio
#    wins decisively.  For CPU-bound work (not the case here) threads or
#    multiprocessing are preferred because asyncio is single-threaded.
#
# 5. THINK: This script uses daemon=True threads.  What does daemon mean here
#    and what happens to in-flight requests if the main thread exits?
#
#    ANSWER: A daemon thread is one that does NOT block the Python interpreter
#    from exiting.  When ALL non-daemon threads (including the main thread)
#    finish, the interpreter shuts down immediately — daemon threads are killed
#    at that point without any cleanup, even if they are mid-execution.
#
#    In this script, the worker threads are daemon=True.  This means:
#    - If the user presses Ctrl-C (KeyboardInterrupt) the main() function
#      catches it, prints "Stopped." and returns.  The main thread ends.
#    - The interpreter then tears down without waiting for workers.
#    - Any in-flight HTTP requests being made by those worker threads are
#      abruptly terminated: TCP connections may be left half-open, response
#      bodies may never be read, and the remote server gets a connection reset.
#    - Results that were already computed but not yet placed in result_queue
#      are silently dropped.
#
#    The trade-off is intentional here: we want the script to exit promptly
#    on Ctrl-C rather than waiting up to `timeout` seconds for every in-flight
#    request to complete.  For scripts where correctness matters more than
#    speed (e.g., writing audit logs), you would use non-daemon threads and
#    call t.join() with a short timeout before raising SystemExit.
