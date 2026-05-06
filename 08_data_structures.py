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
import threading
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
# 2. LRU Cache - Least Recently Used cache using dict + RLock
# ---------------------------------------------------------------------------

class LRUCache(Generic[K, V]):
    """
    O(1) get and put.  Evicts the least-recently-used key when full.
    Use-case: cache DNS lookups, Kubernetes node metadata, etc.

    Implementation: Python dicts preserve insertion order (3.7+), so we can
    move a key to the end by deleting and re-inserting it.

    EXPAND #2: Thread-safe via threading.RLock (re-entrant lock).
    RLock is used instead of plain Lock because get() calls pop() + re-insert,
    and put() also calls pop() — if either method were to call the other
    internally (e.g., a subclass override), a plain Lock would deadlock because
    the same thread would try to acquire a lock it already holds.  An RLock
    can be acquired multiple times by the *same* thread without blocking.

    EXPAND #3: `ttl` (time-to-live) in seconds.  Entries older than ttl are
    treated as missing even if still present in the cache.  Expiry is checked
    lazily on access (no background sweeper thread needed for SRE scripts).
    """

    def __init__(self, capacity: int, ttl: Optional[float] = None) -> None:
        self.capacity = capacity
        self.ttl = ttl                          # seconds; None = no expiry
        self._cache: dict = {}                   # key -> value
        self._timestamps: dict = {}              # key -> insertion time (for TTL)
        self._lock = threading.RLock()           # EXPAND #2: re-entrant lock

    def _expired(self, key: K) -> bool:
        """Return True if the TTL has passed for this key."""
        if self.ttl is None:
            return False
        return time.monotonic() - self._timestamps.get(key, 0) > self.ttl

    def get(self, key: K) -> Optional[V]:
        with self._lock:                         # acquire RLock; released at end of block
            if key not in self._cache:
                return None
            if self._expired(key):               # EXPAND #3: treat expired entries as missing
                del self._cache[key]
                del self._timestamps[key]
                return None
            # Move to end = mark as most recently used
            value = self._cache.pop(key)
            self._cache[key] = value
            self._timestamps[key] = time.monotonic()  # refresh timestamp on access
            return value

    def put(self, key: K, value: V) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.pop(key)
            elif len(self._cache) >= self.capacity:
                # Remove the oldest (first inserted) key - dict preserves insertion order
                oldest = next(iter(self._cache))
                del self._cache[oldest]
                del self._timestamps[oldest]
            self._cache[key] = value
            self._timestamps[key] = time.monotonic()  # record insertion time for TTL

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

    def _prune(self, now: float) -> None:
        """Remove timestamps that have fallen outside the sliding window."""
        cutoff = now - self.window_s
        while self._calls and self._calls[0] < cutoff:
            self._calls.popleft()

    def allow(self) -> bool:
        now = time.monotonic()
        self._prune(now)                    # drop stale entries before checking

        if len(self._calls) < self.max_calls:
            self._calls.append(now)
            return True
        return False

    @property
    def current_usage(self) -> int:
        # BUG FIX #1: prune first so stale entries are not counted.
        # Previously this re-scanned without pruning, potentially returning a
        # count > 0 after the window had fully expired.
        now = time.monotonic()
        self._prune(now)
        return len(self._calls)


# ---------------------------------------------------------------------------
# EXPAND #4: Token Bucket Rate Limiter
# ---------------------------------------------------------------------------

class TokenBucket:
    """
    Alternative rate limiter using the token-bucket algorithm.
    Tokens refill at `rate` per second up to `capacity` (burst budget).
    allow() consumes one token; returns False if the bucket is empty.

    COMPARISON vs SlidingWindowRateLimiter under bursty traffic:
    - SlidingWindow: strictly limits the number of calls in the last W seconds.
      A burst of max_calls is allowed but once they are recorded, the window
      must slide past all of them before new calls are permitted.  Fairest for
      sustained traffic.
    - TokenBucket: refills tokens at a steady rate regardless of when requests
      arrive.  If traffic is quiet for a while, unused tokens accumulate up to
      `capacity`, allowing a burst of up to `capacity` calls all at once.
      More permissive under bursty workloads (allows "credit" to build up).

    Example: max_calls=5, window=1s vs rate=5/s, capacity=10.
    After 2 s of silence:
      SlidingWindow: allows 5 calls immediately (window is clear).
      TokenBucket:   has 10 tokens saved up, allows 10 calls immediately.
    """

    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = rate            # tokens added per second
        self.capacity = capacity    # maximum tokens (burst ceiling)
        self._tokens: float = capacity  # start full
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    def allow(self) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False

    @property
    def current_tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


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

    # EXPAND #3: TTL demo
    print(f"\n=== LRUCache with TTL=0.1s ===")
    ttl_cache: LRUCache[str, int] = LRUCache(capacity=5, ttl=0.1)
    ttl_cache.put("x", 99)
    print(f"  get('x') immediately: {ttl_cache.get('x')}")
    time.sleep(0.15)
    print(f"  get('x') after 0.15s (should be None): {ttl_cache.get('x')}")
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
    print(f"  Call after reset: {'ALLOWED' if limiter.allow() else 'DENIED'} (usage={limiter.current_usage})")

    # EXPAND #4: Token bucket demo
    print("\n=== TokenBucket (5 tokens/s, capacity=10) ===")
    bucket = TokenBucket(rate=5.0, capacity=10)
    print("  Burst: sending 12 calls immediately")
    for i in range(12):
        allowed = bucket.allow()
        print(f"  Call {i+1}: {'ALLOWED' if allowed else 'DENIED '} (tokens={bucket.current_tokens:.1f})")
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
#    FIX: Extracted `_prune(now)` helper that removes timestamps outside the
#    window.  Both `allow()` and `current_usage` call `_prune()` first.
#    Previously `current_usage` used a generator expression that counted
#    without removing stale entries, so after the window expired `len(self._calls)`
#    still held the old timestamps and would return inflated counts.
#
# 2. EXPAND: Make LRUCache thread-safe by adding a threading.RLock.
#    Show why an RLock (re-entrant) is needed over a plain Lock here.
#
#    IMPLEMENTED: Every public method acquires `self._lock = threading.RLock()`
#    via `with self._lock`.  RLock is chosen over plain Lock because:
#    - Plain Lock raises a deadlock if the same thread tries to acquire it twice.
#    - If a subclass overrides `get()` and calls `super().get()` while still
#      inside its own `with self._lock` block, a plain Lock would deadlock.
#    - RLock tracks the owning thread and allows recursive acquisition,
#      incrementing an internal counter.  The lock is released when the counter
#      reaches zero (i.e., every `acquire` has a matching `release`).
#
# 3. EXPAND: Add a ttl (time-to-live) parameter to LRUCache so entries
#    expire after N seconds regardless of access order.
#
#    IMPLEMENTED: `LRUCache.__init__` gains `ttl: Optional[float] = None`.
#    `self._timestamps` tracks insertion time per key.  `_expired(key)` checks
#    whether `time.monotonic() - timestamps[key] > ttl`.  `get()` calls
#    `_expired()` before moving to end — expired entries are deleted and None
#    is returned.  `put()` updates the timestamp on write; `get()` refreshes
#    it on access (cache hit resets the TTL clock).
#
# 4. EXPAND: Implement a TokenBucket rate limiter as an alternative to
#    SlidingWindowRateLimiter.  Compare the two under a bursty traffic pattern.
#
#    IMPLEMENTED: `TokenBucket(rate, capacity)`.  `_refill()` adds
#    `elapsed * rate` tokens (capped at capacity) on every `allow()` call.
#    Thread-safe via `threading.Lock`.
#
#    COMPARISON: see docstring on TokenBucket class above.  Key difference:
#    TokenBucket accumulates credit during quiet periods, allowing larger bursts
#    than SlidingWindow.  SlidingWindow is stricter: it only looks at the last
#    W seconds regardless of history.  Choose SlidingWindow for hard API quota
#    compliance; choose TokenBucket when you want to reward idle clients with
#    burst allowance.
#
# 5. THINK: RingBuffer uses collections.deque(maxlen=N).  Why is deque faster
#    than a Python list for this use-case?  What is the time complexity of
#    list.insert(0, item) vs deque.appendleft(item)?
#
#    deque (double-ended queue) is implemented as a doubly-linked list of fixed-
#    size blocks.  Appending or prepending is O(1) because it only updates two
#    pointers at one end.
#
#    list is a dynamic array (contiguous block of memory).  Appending to the
#    RIGHT end is amortised O(1) (occasional realloc doubles the buffer).
#    But insert(0, item) — prepending — is O(n) because every existing element
#    must be shifted one position right in memory to make room at index 0.
#
#    For a ring buffer that evicts the oldest element (from the left) and
#    appends the newest (to the right):
#    - deque.append(item):    O(1) — just update the tail pointer
#    - deque.popleft():       O(1) — just advance the head pointer
#    - list.append(item):     O(1) amortised — fast, same as deque
#    - list.pop(0):           O(n) — shifts all remaining n elements left
#
#    With deque(maxlen=N) Python automatically discards the leftmost item when
#    the buffer is full, giving O(1) ring-buffer semantics.  Achieving the same
#    with a plain list requires list.pop(0) which is O(n) per insertion — 100x
#    slower for a 100-element buffer and 1000x slower for a 1000-element buffer.
