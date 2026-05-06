#!/usr/bin/env python3
"""
07_async_health.py - Async HTTP Health Checker with asyncio + aiohttp
The async version of 02_health_checker.py.  For I/O-bound work (network calls)
asyncio is faster than threading at scale: 1000 concurrent checks with near-zero
thread overhead.

Concepts: async/await, asyncio.gather, asyncio.Semaphore, aiohttp,
          event loops, coroutines vs threads
Run: python 07_async_health.py
Run with concurrency cap: python 07_async_health.py --concurrency 10
"""

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, asdict
from typing import List, Optional

try:
    import aiohttp
except ImportError:
    raise SystemExit("pip install aiohttp")


DEFAULT_URLS = [
    "https://httpbin.org/status/200",
    "https://httpbin.org/status/503",
    "https://httpbin.org/delay/1",
    "https://httpbin.org/get",
    "https://httpbin.org/status/404",
    "https://this-host-does-not-exist.example.com/health",
]


@dataclass
class Result:
    url: str
    status: Optional[int] = None
    latency_ms: float = 0.0
    error: Optional[str] = None

    @property
    def healthy(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    def __str__(self) -> str:
        if self.error:
            return f"  ERROR  {self.url}  [{self.error[:60]}]"
        label = "  OK   " if self.healthy else " FAIL  "
        return f"{label} {self.status}  {self.latency_ms:6.0f}ms  {self.url}"

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict of this result."""
        return {
            "url": self.url,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 1),
            "healthy": self.healthy,
            "error": self.error,
        }


# EXPAND #4: retry logic — try up to (1 + retries) times with exponential back-off
async def check_url(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
    timeout: float = 5.0,
    method: str = "get",
    retries: int = 0,
) -> Result:
    """
    Coroutine that checks a single URL.
    The semaphore limits how many checks run concurrently even when
    hundreds of coroutines are scheduled.

    EXPAND #2: `method` selects GET (default) or HEAD.
    HEAD requests omit the response body — useful when you only care
    about reachability and want to minimise bandwidth.

    EXPAND #4: On failure, retry up to `retries` times with exponential
    back-off: 0.5 s, 1 s, 2 s, ...  The semaphore is held for the
    initial attempt only; retries reacquire it so the concurrency cap
    remains effective across all attempts.
    """
    last_result: Optional[Result] = None
    for attempt in range(retries + 1):
        if attempt > 0:
            await asyncio.sleep(0.5 * 2 ** (attempt - 1))  # 0.5, 1.0, 2.0 ...
        async with semaphore:
            start = time.monotonic()
            try:
                to = aiohttp.ClientTimeout(total=timeout)
                http_method = getattr(session, method)  # session.get or session.head
                async with http_method(url, timeout=to, allow_redirects=True) as resp:
                    latency = (time.monotonic() - start) * 1000
                    last_result = Result(url=url, status=resp.status, latency_ms=latency)
            except aiohttp.ClientConnectorError as e:
                last_result = Result(url=url, error=f"ConnectError: {e}")
            except asyncio.TimeoutError:
                last_result = Result(url=url, error=f"Timeout>{timeout}s")
            except aiohttp.ClientError as e:
                last_result = Result(url=url, error=str(e))
        if last_result and last_result.healthy:
            return last_result
    return last_result  # type: ignore[return-value]


async def run_checks(
    urls: List[str],
    concurrency: int = 20,
    timeout: float = 5.0,
    method: str = "get",
    retries: int = 0,
) -> List[Result]:
    """
    Fan-out all URL checks concurrently up to `concurrency` at a time.
    asyncio.gather collects all results, preserving order.
    """
    semaphore = asyncio.Semaphore(concurrency)

    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            check_url(session, url, semaphore, timeout, method=method, retries=retries)
            for url in urls
        ]
        results = await asyncio.gather(*tasks)

    return sorted(results, key=lambda r: (not r.healthy, r.url))


async def watch_loop(
    urls: List[str],
    interval: float,
    concurrency: int,
    timeout: float,
    method: str,
    retries: int,
    output_json: bool,
) -> None:
    """Repeatedly check all URLs, sleeping between rounds."""
    while True:
        results = await run_checks(
            urls, concurrency=concurrency, timeout=timeout, method=method, retries=retries
        )
        healthy = sum(1 for r in results if r.healthy)
        if output_json:
            print(json.dumps({
                "ts": time.strftime("%H:%M:%S"),
                "healthy": healthy,
                "total": len(results),
                "results": [r.to_dict() for r in results],
            }))
        else:
            print(f"\n{'='*55}  [{time.strftime('%H:%M:%S')}]  {healthy}/{len(results)} healthy")
            for r in results:
                print(r)
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Async HTTP health checker")
    p.add_argument("--concurrency", type=int, default=20, help="Max concurrent checks")
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--watch", type=float, default=0, help="Re-run every N seconds (0=once)")
    # EXPAND #2: HEAD-only checks skip response body download
    p.add_argument(
        "--method",
        choices=["get", "head"],
        default="get",
        help="HTTP method: 'get' (default) or 'head' (no body, faster for reachability checks)",
    )
    # EXPAND #3: JSON output for piping to jq or other tools
    p.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format: 'text' (default) or 'json' (machine-readable)",
    )
    # EXPAND #4: retry flag
    p.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Retry count per URL on failure (exponential back-off: 0.5s, 1s, 2s, ...)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_json = args.output == "json"

    if args.watch:
        try:
            asyncio.run(
                watch_loop(
                    DEFAULT_URLS,
                    args.watch,
                    args.concurrency,
                    args.timeout,
                    method=args.method,
                    retries=args.retries,
                    output_json=output_json,
                )
            )
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        overall_start = time.monotonic()
        results = asyncio.run(
            run_checks(
                DEFAULT_URLS,
                args.concurrency,
                args.timeout,
                method=args.method,
                retries=args.retries,
            )
        )
        elapsed = time.monotonic() - overall_start
        healthy = sum(1 for r in results if r.healthy)

        # EXPAND #3: --output json writes newline-delimited JSON to stdout
        if output_json:
            print(json.dumps({
                "ts": time.strftime("%H:%M:%S"),
                "elapsed_s": round(elapsed, 3),
                "healthy": healthy,
                "total": len(results),
                "results": [r.to_dict() for r in results],
            }))
        else:
            print(f"Health Check  {healthy}/{len(results)} healthy  ({elapsed:.2f}s total)")
            print("=" * 55)
            for r in results:
                print(r)


if __name__ == "__main__":
    main()


# =============================================================================
# EXERCISES
# =============================================================================
# 1. COMPARE: Run both 02_health_checker.py (threading) and this script against
#    the same 6 URLs and time them.  Then create a urls.txt with 50 URLs all
#    pointing to httpbin.org/delay/1 and compare again.  What do you notice?
#
#    RESULT for 6 URLs:
#    Both scripts finish in roughly the same wall-clock time — the bottleneck is
#    the slowest network round-trip, and thread/coroutine startup overhead is
#    negligible for 6 tasks.
#
#    RESULT for 50 x httpbin.org/delay/1:
#    - Threading (--workers 4):  ceil(50/4) * 1s ≈ 13 s
#    - Threading (--workers 50): all 50 fire at once ≈ 1 s  (but 50 OS threads)
#    - Asyncio   (--concurrency 50): all 50 coroutines in-flight ≈ 1 s, ~0 overhead
#
#    KEY INSIGHT: asyncio matches threading-at-max-workers performance but at
#    a fraction of the memory cost.  Each OS thread consumes ~8 MB of stack;
#    1000 threads = ~8 GB RAM.  1000 asyncio coroutines cost only a few KB each.
#    For high-fan-out monitoring (thousands of endpoints) asyncio wins decisively.
#
# 2. EXPAND: Add HEAD-only checks (session.head) for endpoints where you only
#    care about reachability, not the response body.  Compare latency vs GET.
#
#    IMPLEMENTED: `check_url` now accepts a `method` parameter ("get" or "head").
#    `getattr(session, method)` selects `session.get` or `session.head` at runtime.
#    The `--method head` CLI flag threads the choice through run_checks → check_url.
#
#    HEAD skips the response body download, so latency is lower on large pages.
#    For tiny endpoints like httpbin status codes the difference is negligible.
#
# 3. EXPAND: Add --output json flag that writes results as JSON to stdout
#    so this script can be piped into `jq` or another tool.
#
#    IMPLEMENTED: `Result.to_dict()` produces a JSON-serialisable dict.
#    `--output json` (default "text") formats both one-shot and watch outputs as
#    a single JSON object containing ts, elapsed_s, healthy, total, and results[].
#    Pipe example: python 07_async_health.py --output json | jq '.results[] | select(.healthy == false)'
#
# 4. EXPAND: Add retry logic: if a check fails, retry up to 2 times with
#    exponential back-off (await asyncio.sleep(0.5 * 2**attempt)).
#
#    IMPLEMENTED: `check_url` loops for `retries + 1` attempts.  On attempt > 0
#    it awaits `asyncio.sleep(0.5 * 2**(attempt-1))` — giving 0.5 s, 1.0 s delays.
#    The semaphore is reacquired for each attempt so the concurrency cap stays
#    effective.  `--retries N` CLI flag passes N through run_checks → check_url.
#
# 5. THINK: What is the difference between asyncio.gather and asyncio.wait?
#    When would you prefer asyncio.wait over asyncio.gather?
#
#    asyncio.gather(*coros):
#    - Schedules all coroutines and waits for ALL to complete (or any to raise).
#    - Returns results in the SAME ORDER as the input coroutines.
#    - If any coroutine raises, gather propagates the exception immediately by
#      default (cancel_remaining=True in Python 3.11+).  All other tasks are
#      cancelled unless return_exceptions=True is passed.
#    - Use when you want all results and treat a single failure as fatal, or
#      when you want exceptions collected alongside results (return_exceptions=True).
#
#    asyncio.wait(tasks, return_when=...):
#    - Takes a set of Task objects (not raw coroutines).
#    - Returns TWO sets: (done, pending).
#    - `return_when` controls when it returns:
#        FIRST_COMPLETED  — return as soon as one task finishes (race pattern)
#        FIRST_EXCEPTION  — return as soon as one task raises
#        ALL_COMPLETED    — wait for everything (equivalent to gather semantics)
#    - Exceptions are NOT propagated; they live inside the Task objects.
#      Caller must inspect each task: t.result() raises if the task failed.
#    - Use asyncio.wait when you need partial results (process done tasks as
#      they arrive), when you want a "first success" race, or when you must
#      cancel pending tasks manually after a subset completes.
#
#    Rule of thumb:
#    - gather  → "I want all N results at once, raise on first failure"
#    - wait    → "I want to react to completions individually or partially"
