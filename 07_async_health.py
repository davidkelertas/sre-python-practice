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
import time
from dataclasses import dataclass
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


async def check_url(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
    timeout: float = 5.0,
) -> Result:
    """
    Coroutine that checks a single URL.
    The semaphore limits how many checks run concurrently even when
    hundreds of coroutines are scheduled.
    """
    async with semaphore:          # acquire slot; release when block exits
        start = time.monotonic()
        try:
            # aiohttp ClientTimeout controls both connect and total time
            to = aiohttp.ClientTimeout(total=timeout)
            async with session.get(url, timeout=to, allow_redirects=True) as resp:
                latency = (time.monotonic() - start) * 1000
                return Result(url=url, status=resp.status, latency_ms=latency)
        except aiohttp.ClientConnectorError as e:
            return Result(url=url, error=f"ConnectError: {e}")
        except asyncio.TimeoutError:
            return Result(url=url, error=f"Timeout>{timeout}s")
        except aiohttp.ClientError as e:
            return Result(url=url, error=str(e))


async def run_checks(
    urls: List[str],
    concurrency: int = 20,
    timeout: float = 5.0,
) -> List[Result]:
    """
    Fan-out all URL checks concurrently up to `concurrency` at a time.
    asyncio.gather collects all results, preserving order.
    """
    semaphore = asyncio.Semaphore(concurrency)

    # aiohttp recommends reusing one session per batch (connection pooling)
    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Create all coroutines up front
        tasks = [check_url(session, url, semaphore, timeout) for url in urls]
        # asyncio.gather runs them concurrently and waits for all to finish
        results = await asyncio.gather(*tasks)

    return sorted(results, key=lambda r: (not r.healthy, r.url))


async def watch_loop(urls: List[str], interval: float, concurrency: int, timeout: float) -> None:
    """Repeatedly check all URLs, sleeping between rounds."""
    while True:
        results = await run_checks(urls, concurrency=concurrency, timeout=timeout)
        healthy = sum(1 for r in results if r.healthy)
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
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.watch:
        # asyncio.run() creates an event loop, runs the coroutine, then closes it
        try:
            asyncio.run(watch_loop(DEFAULT_URLS, args.watch, args.concurrency, args.timeout))
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        # One-shot: run, print, exit
        overall_start = time.monotonic()
        results = asyncio.run(run_checks(DEFAULT_URLS, args.concurrency, args.timeout))
        elapsed = time.monotonic() - overall_start

        healthy = sum(1 for r in results if r.healthy)
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
# 2. EXPAND: Add HEAD-only checks (session.head) for endpoints where you only
#    care about reachability, not the response body.  Compare latency vs GET.
#
# 3. EXPAND: Add --output json flag that writes results as JSON to stdout
#    so this script can be piped into `jq` or another tool.
#
# 4. EXPAND: Add retry logic: if a check fails, retry up to 2 times with
#    exponential back-off (await asyncio.sleep(0.5 * 2**attempt)).
#
# 5. THINK: What is the difference between asyncio.gather and asyncio.wait?
#    When would you prefer asyncio.wait over asyncio.gather?
#    (Hint: consider partial failures and return_when parameter.)
