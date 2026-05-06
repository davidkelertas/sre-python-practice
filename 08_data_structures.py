#!/usr/bin/env python3
"""
08_data_structures.py - Data Structures & Algorithms for SREs
Covers the DS/algo concepts most likely to come up in a cloud-native SRE interview:
  - Ring buffer (circular buffer) for fixed-size metric windows
  - LRU cache (without functools.lru_cache to show the mechanics)
  - Priority queue for alert severity
  - Sliding window rate limiter

Concepts: deque, heapq, dict ordering, generics, __dunder__ methods
Run: python 08_data_structures.py
"""

import heapq
import time
from collections import deque
from typing import Any, Generic, Hashable, List, Optional, Tuple, TypeVar

V = TypeVar("V")
K = TypeVar("K", bound=Hashable)


# ---------------------------------------------------------------------------
# 1. Ring Buffer - fixed-size circular buffer for streaming metrics
# ---------------------------------------------------------------------------

class RingBuffer(Generic[V]):
    """
    Stores the last N values, discarding the oldest when full.
    Use-case: keep a 60-sample CPU history for a sparkline.
    Time: O(1) append, O(n) iteration.  Space: O(n).
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._buf: deque = deque(maxlen=capacity)
        self.capacity = capacity

    def push(self, value: V) -> None:
        self._buf.append(value)

    @property
    def full(self) -> bool:
        return len(self._buf) == self.capacity

    def average(self) -> float:
        if not self._buf:
            return 0.0
        return sum(self._buf) / len(self._buf)  # type: ignore[arg-type]

    def __len__(self) -> int:
        return len(self._buf)

    def __iter__(self):
        return iter(self._buf)

    def __repr__(self) -> str:
        return f"RingBuffer(capacity={self.capacity}, data={list(self._buf)})"


# ---------------------------------------------------------------------------
# 2. LRU Cache - Least Recently Used cache using dict + deque
# ---------------------------------------------------------------------------

class LRUCache(Generic[K, V]):
    """
    O(1) get and put.  Evicts the least-recently-used key when full.
    Use-case: cache DNS lookups, Kubernetes node metadata, etc.

    Implementation: Python dicts preserve insertion order (3.7+), so we can
    move a key to the end by deleting and re-inserting it.
    """

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._cache: dict = {}   # key → value, ordered by access time

    def get(self, key: K) -> Optional[V]:
        if key not in self._cache:
            return None
        # Move to end = mark as most recently used
        value = self._cache.pop(key)
        self._cache[key] = value
        return value

    def put(self, key: K, value: V) -> None:
        if key in self._cache:
            self._cache.pop(key)
        elif len(self._cache) >= self.capacity:
            # Remove the oldest (first inserted) key - dict preserves insertion order
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[key] = value

    def __len__(self) -> int:
        return len(self._cache)

    def __repr__(self) -> str:
        return f"LRUCache(capacity={self.capacity}, size={len(self)}, keys={list(self._cache.keys())})"


# ---------------------------------------------------------------------------
# 3. Alert Priority Queue - min-heap ordered by severity
# ---------------------------------------------------------------------------

SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class Alert:
    def __init__(self, severity: str, message: str, timestamp: Optional[float] = None) -> None:
        if severity not in SEVERITY:
            raise ValueError(f"severity must be one of {list(SEVERITY)}")
        self.severity = severity
        self.message = message
        self.timestamp = timestamp or time.time()

    # heapq requires __lt__ for comparison
    def __lt__(self, other: "Alert") -> bool:
        if SEVERITY[self.severity] != SEVERITY[other.severity]:
            return SEVERITY[self.severity] < SEVERITY[other.severity]
        return self.timestamp < other.timestamp  # earlier alert wins on tie

    def __repr__(self) -> str:
        return f"Alert({self.severity}: {self.message})"


class AlertQueue:
    """Min-heap of alerts; pop() always returns the highest-severity alert."""

    def __init__(self) -> None:
        self._heap: List[Alert] = []

    def push(self, alert: Alert) -> None:
        heapq.heappush(self._heap, alert)

    def pop(self) -> Optional[Alert]:
        if not self._heap:
            return None
        return heapq.heappop(self._heap)

    def peek(self) -> Optional[Alert]:
        return self._heap[0] if self._heap else None

    def __len__(self) -> int:
        return len(self._heap)


# ---------------------------------------------------------------------------
# 4. Sliding Window Rate Limiter
# ---------------------------------------------------------------------------

class SlidingWindowRateLimiter:
    """
    Allows up to `max_calls` requests within any `window_s` second window.
    Use-case: rate-limiting calls to an external API (e.g., AWS, Slack).

    Uses a deque of timestamps; old entries are pruned on each check.
    Thread-safety: not included here - add threading.Lock for concurrent use.
    """

    def __init__(self, max_calls: int, window_s: float) -> None:
        self.max_calls = max_calls
        self.window_s = window_s
        self._calls: deque = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_s

        # Remove timestamps outside the window (left side of deque = oldest)
        while self._calls and self._calls[0] < cutoff:
            self._calls.popleft()

        if len(self._calls) < self.max_calls:
            self._calls.append(now)
            return True
        return False

    @property
    def current_usage(self) -> int:
        now = time.monotonic()
        return sum(1 for t in self._calls if t >= now - self.window_s)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_ring_buffer() -> None:
    print("=== RingBuffer ===")
    rb: RingBuffer[float] = RingBuffer(capacity=5)
    for v in [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]:
        rb.push(v)
        print(f"  push({v:4.0f})  avg={rb.average():.1f}  {list(rb)}")
    # After 6 pushes into a cap-5 buffer, 10.0 should be gone
    assert 10.0 not in list(rb), "10.0 should have been evicted"
    print()


def demo_lru_cache() -> None:
    print("=== LRUCache ===")
    cache: LRUCache[str, int] = LRUCache(capacity=3)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    print(f"  Initial: {cache}")
    cache.get("a")          # 'a' is now most-recently-used
    cache.put("d", 4)       # evicts 'b' (LRU) not 'a'
    print(f"  After get(a) and put(d): {cache}")
    assert cache.get("b") is None, "b should be evicted"
    assert cache.get("a") == 1, "a should still be present"
    print()


def demo_alert_queue() -> None:
    print("=== AlertQueue ===")
    aq = AlertQueue()
    aq.push(Alert("low", "disk at 70%"))
    aq.push(Alert("critical", "node unreachable"))
    aq.push(Alert("high", "CPU >90%"))
    aq.push(Alert("medium", "latency spike"))
    print(f"  {len(aq)} alerts queued, top: {aq.peek()}")
    while aq:
        print(f"  -> {aq.pop()}")
    print()


def demo_rate_limiter() -> None:
    print("=== SlidingWindowRateLimiter (5 calls / 2s) ===")
    limiter = SlidingWindowRateLimiter(max_calls=5, window_s=2.0)
    for i in range(8):
        allowed = limiter.allow()
        print(f"  Call {i+1}: {'ALLOWED' if allowed else 'DENIED '} (usage={limiter.current_usage})")
        time.sleep(0.1)
    print("  (sleeping 2s to reset window...)")
    time.sleep(2.0)
    print(f"  Call after reset: {'ALLOWED' if limiter.allow() else 'DENIED'}")
    print()


if __name__ == "__main__":
    demo_ring_buffer()
    demo_lru_cache()
    demo_alert_queue()
    demo_rate_limiter()


# =============================================================================
# EXERCISES
# =============================================================================
# 1. BUG: SlidingWindowRateLimiter.current_usage re-scans the deque without
#    pruning old entries.  This means it can return a value higher than
#    max_calls after the window expires.  Fix it.
#
# 2. EXPAND: Make LRUCache thread-safe by adding a threading.RLock.
#    Show why an RLock (re-entrant) is needed over a plain Lock here.
#
# 3. EXPAND: Add a ttl (time-to-live) parameter to LRUCache so entries
#    expire after N seconds regardless of access order.
#
# 4. EXPAND: Implement a TokenBucket rate limiter as an alternative to
#    SlidingWindowRateLimiter.  Compare the two under a bursty traffic pattern.
#
# 5. THINK: RingBuffer uses collections.deque(maxlen=N).  Why is deque faster
#    than a Python list for this use-case?  What is the time complexity of
#    list.insert(0, item) vs deque.appendleft(item)?
