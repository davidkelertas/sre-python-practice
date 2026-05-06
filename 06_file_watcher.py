#!/usr/bin/env python3
"""
06_file_watcher.py - File Watcher / Log Tailer
SRE use-case: watch a config file for changes and reload; tail a growing log.
Demonstrates: threading, Events, mtime polling, queue, context managers.

Run (watch mode):  python 06_file_watcher.py --watch config.yaml
Run (tail mode):   python 06_file_watcher.py --tail /var/log/syslog
Run (demo):        python 06_file_watcher.py --demo
"""

import argparse
import collections
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# File change watcher - polls mtime (no inotify dep for portability)
# ---------------------------------------------------------------------------

class FileWatcher:
    """
    Background thread that polls a file's mtime and calls `callback` when it changes.
    Uses threading.Event for clean shutdown rather than a daemon thread flag.
    """

    def __init__(
        self,
        path: Path,
        callback: Callable[[Path], None],
        interval: float = 1.0,
    ) -> None:
        self.path = path
        self.callback = callback
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"watcher-{path.name}")
        self._last_mtime: Optional[float] = None

    def start(self) -> "FileWatcher":
        self._thread.start()
        return self  # allow `with FileWatcher(...) as w:` chaining

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=self.interval + 1)

    # Context manager support so callers can use `with FileWatcher(...) as w:`
    def __enter__(self) -> "FileWatcher":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()

    def _current_mtime(self) -> Optional[float]:
        try:
            return self.path.stat().st_mtime
        except FileNotFoundError:
            return None

    def _run(self) -> None:
        self._last_mtime = self._current_mtime()
        while not self._stop_event.wait(self.interval):
            mtime = self._current_mtime()
            if mtime != self._last_mtime:
                self._last_mtime = mtime
                try:
                    self.callback(self.path)
                except Exception as e:
                    print(f"[watcher] callback error: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Log tailer - reads new lines as they are appended
# ---------------------------------------------------------------------------

class LogTailer:
    """
    Reads a file from the end and streams new lines to a queue.
    Handles log rotation by detecting when the file shrinks (inode swap).

    Exercise 3: max_queue_size caps the internal deque. When the deque is full,
    the oldest item is dropped (popleft) before inserting the new line so the
    producer never blocks. A warning is printed to stderr on each drop.
    """

    # EXERCISE 3: Added max_queue_size parameter.
    # When the queue is full we drop the oldest item (popleft from a deque) and
    # log a warning rather than blocking. This keeps the tailer thread alive and
    # responsive even if the consumer falls far behind — useful in SRE tooling
    # where losing a few log lines is preferable to blocking the producer or
    # letting memory grow without bound.
    def __init__(
        self,
        path: Path,
        line_queue: queue.Queue,
        poll_interval: float = 0.5,
        max_queue_size: Optional[int] = None,
    ) -> None:
        self.path = path
        self.queue = line_queue
        self.poll_interval = poll_interval
        self.max_queue_size = max_queue_size
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="tailer")
        # Internal deque used only when max_queue_size is set.
        self._deque: Optional[collections.deque] = (
            collections.deque(maxlen=None) if max_queue_size is not None else None
        )

    def start(self) -> "LogTailer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()

    def _enqueue(self, line: str) -> None:
        """Put a line into the queue, honouring max_queue_size."""
        if self.max_queue_size is None:
            self.queue.put(line)
            return

        # Non-blocking bounded enqueue: drop oldest if full.
        assert self._deque is not None
        self._deque.append(line)
        if len(self._deque) > self.max_queue_size:
            dropped = self._deque.popleft()
            print(
                f"[tailer] WARNING: queue full (max={self.max_queue_size}), "
                f"dropped oldest line: {dropped!r}",
                file=sys.stderr,
            )
        self.queue.put(line)

    def _run(self) -> None:
        # Seek to end so we only get NEW lines (tail -f behaviour)
        try:
            f = self.path.open()
            f.seek(0, 2)  # SEEK_END
        except FileNotFoundError:
            print(f"[tailer] file not found: {self.path}")
            return

        current_inode = os.stat(self.path).st_ino
        # EXERCISE 1 (BUG FIX): track the last known file size so we can detect
        # same-inode rotation (file deleted+recreated on filesystems that recycle
        # inodes quickly, or truncated in-place).
        current_size = os.stat(self.path).st_size

        while not self._stop_event.is_set():
            # Detect log rotation: inode changed = file was replaced
            try:
                stat = os.stat(self.path)
                new_inode = stat.st_ino
                new_size = stat.st_size

                # EXERCISE 1 (BUG FIX): also reopen when the file has shrunk
                # even if the inode is the same. This catches the case where the
                # log daemon deletes and recreates the file on a filesystem that
                # immediately recycles the same inode number (e.g. small tmpfs
                # partitions or certain ext4 configurations). Without the size
                # check we would silently miss all new lines written after the
                # recreation because our read position would be past EOF.
                if new_inode != current_inode or new_size < current_size:
                    f.close()
                    f = self.path.open()
                    current_inode = new_inode
                    current_size = 0  # reset; will be updated below
                    print("[tailer] log rotation detected, reopening file")
            except FileNotFoundError:
                time.sleep(self.poll_interval)
                continue

            line = f.readline()
            if line:
                current_size = os.fstat(f.fileno()).st_size
                self._enqueue(line.rstrip("\n"))
            else:
                time.sleep(self.poll_interval)

        f.close()


# ---------------------------------------------------------------------------
# Demo: generate a growing file and tail it simultaneously
# ---------------------------------------------------------------------------

def demo() -> None:
    demo_file = Path("demo_growing.log")
    demo_cfg = Path("demo_config.yaml")
    demo_cfg.write_text("version: 1\nlog_level: INFO\n")

    print("=== Demo: FileWatcher + LogTailer ===\n")

    # 1. Watch config file for changes
    change_count = [0]
    def on_config_change(p: Path) -> None:
        change_count[0] += 1
        print(f"[watcher] Config changed! ({change_count[0]} changes so far)")

    # 2. Tail a growing log file
    line_q: queue.Queue = queue.Queue()

    print(f"Watching {demo_cfg} for changes (will modify it in 2s)")
    print(f"Tailing {demo_file} (will write lines to it)")
    print("Press Ctrl-C to stop\n")

    with FileWatcher(demo_cfg, on_config_change, interval=0.5):
        tailer = LogTailer(demo_file, line_q, poll_interval=0.2).start()

        # Background thread writes to the log file
        def write_lines() -> None:
            with demo_file.open("w") as f:
                for i in range(20):
                    f.write(f"[{time.strftime('%H:%M:%S')}] Event {i:03d} happened\n")
                    f.flush()
                    time.sleep(0.4)

        # Background thread modifies the config file
        def modify_config() -> None:
            time.sleep(2)
            demo_cfg.write_text("version: 2\nlog_level: DEBUG\nfeature: enabled\n")
            time.sleep(2)
            demo_cfg.write_text("version: 3\nlog_level: WARNING\n")

        writer = threading.Thread(target=write_lines, daemon=True)
        changer = threading.Thread(target=modify_config, daemon=True)
        writer.start()
        changer.start()

        try:
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                try:
                    line = line_q.get(timeout=0.5)
                    print(f"[tail] {line}")
                except queue.Empty:
                    pass
        except KeyboardInterrupt:
            pass
        finally:
            tailer.stop()
            demo_file.unlink(missing_ok=True)
            demo_cfg.unlink(missing_ok=True)


def watch_mode(path: Path) -> None:
    print(f"Watching {path} for changes (Ctrl-C to stop)...")
    def on_change(p: Path) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] Changed: {p}")

    with FileWatcher(path, on_change):
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped.")


# EXERCISE 2: Added optional filter_pattern parameter.
# tail_mode now accepts a compiled regex; only lines that match are printed,
# mirroring `tail -f app.log | grep PATTERN` but without the extra process.
def tail_mode(path: Path, filter_pattern: Optional[re.Pattern] = None) -> None:
    desc = f" (filter: {filter_pattern.pattern})" if filter_pattern else ""
    print(f"Tailing {path}{desc} (Ctrl-C to stop)...")
    q: queue.Queue = queue.Queue()
    tailer = LogTailer(path, q).start()
    try:
        while True:
            try:
                line = q.get(timeout=1)
                # Apply filter: skip lines that do not match the pattern.
                if filter_pattern is None or filter_pattern.search(line):
                    print(line)
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        tailer.stop()
        print("\nStopped.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="File watcher and log tailer")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--watch", type=Path, metavar="FILE", help="Watch a file for changes")
    g.add_argument("--tail", type=Path, metavar="FILE", help="Tail a growing log file")
    g.add_argument("--demo", action="store_true", help="Run built-in demo")
    # EXERCISE 2: --filter wires a regex pattern through to tail_mode.
    p.add_argument(
        "--filter",
        metavar="PATTERN",
        help="Only print lines matching this regex (--tail mode only)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.watch:
        watch_mode(args.watch)
    elif args.tail:
        # EXERCISE 2: compile the pattern once and pass it down.
        pattern: Optional[re.Pattern] = None
        if args.filter:
            try:
                pattern = re.compile(args.filter)
            except re.error as exc:
                print(f"Invalid --filter pattern: {exc}", file=sys.stderr)
                sys.exit(1)
        tail_mode(args.tail, filter_pattern=pattern)
    else:
        demo()


if __name__ == "__main__":
    main()


# =============================================================================
# EXERCISES — ANSWERS
# =============================================================================
# 1. BUG FIX (LogTailer._run — same-inode rotation)
#    ---------------------------------------------------------------------------
#    The original code only checked whether os.stat().st_ino changed. On some
#    filesystems (small tmpfs, certain ext4 configurations) the OS recycles inode
#    numbers immediately, so deleting a file and creating a new one can yield the
#    same inode. The tailer would then keep reading from the stale file descriptor,
#    silently missing all new content.
#
#    Fix: also track the current file size. If the new size is *less* than the
#    previously observed size (i.e. the file shrank), treat it as rotation even
#    when the inode matches. See _run() above where `new_size < current_size` is
#    ORed with the inode comparison.
#
# 2. EXPAND (--filter PATTERN in tail_mode)
#    ---------------------------------------------------------------------------
#    parse_args() now exposes a --filter PATTERN argument. main() compiles the
#    pattern with re.compile() (with a helpful error message on bad patterns) and
#    passes the compiled object to tail_mode(). Inside tail_mode() each dequeued
#    line is tested with pattern.search(); lines that do not match are silently
#    skipped. Using .search() (not .match()) allows the pattern to appear anywhere
#    on the line, matching the intuitive behaviour of `grep`.
#
# 3. EXPAND (max_queue_size in LogTailer)
#    ---------------------------------------------------------------------------
#    LogTailer.__init__ now accepts an optional max_queue_size: int. Internally
#    _enqueue() maintains a collections.deque that mirrors items going into the
#    queue. When len(deque) > max_queue_size the *oldest* item is removed with
#    popleft() and a warning is printed to stderr. The producer never calls
#    queue.put() with block=True, so the background tailer thread is never stalled
#    by a slow consumer. The tradeoff is that under sustained backpressure older
#    log lines are silently dropped — acceptable for real-time monitoring tools
#    where recency matters more than completeness.
#
# 4. EXPAND (watchdog / inotify vs. mtime polling)
#    ---------------------------------------------------------------------------
#    On Linux the `watchdog` library wraps inotify (via the InotifyObserver back-
#    end), which gives *instant* notification the moment the kernel writes the
#    change — no polling delay at all.  Our FileWatcher polls every `interval`
#    seconds, so a change made 1 ms after a poll won't be noticed for up to
#    `interval - 1 ms` longer.
#
#    Why we don't add watchdog as a dependency here:
#      • watchdog is a third-party package (pip install watchdog) and pulls in
#        native extension code.  Adding it would break the "zero-dependency"
#        guarantee of this practice module, which must run with the stdlib alone.
#      • inotify is Linux-only; watchdog falls back to polling on macOS/Windows
#        anyway (unless FSEventsObserver / ReadDirectoryChangesW are used), so
#        the cross-platform story becomes more complex.
#      • For most SRE use-cases a 0.5–1 s polling interval is acceptable and is
#        simpler to reason about and test.
#
#    The right choice in production: use watchdog (or inotify bindings directly)
#    for latency-sensitive workloads on Linux; use mtime polling for simplicity
#    and cross-platform compatibility when sub-second latency isn't required.
#
# 5. THINK (daemon=True and data integrity)
#    ---------------------------------------------------------------------------
#    Setting daemon=True on the FileWatcher / LogTailer thread means the Python
#    interpreter will *not* wait for those threads to finish when the main thread
#    exits. The OS abruptly terminates them.
#
#    Data integrity risk: if the callback is in the middle of writing to a file,
#    database, or network socket when the main thread calls sys.exit() (or simply
#    returns), the write is cut short. The result can be:
#      • a truncated or partially-written log entry
#      • a half-committed database transaction that leaves the DB in an
#        inconsistent state
#      • a buffered network write that is never flushed
#
#    Mitigation strategies:
#      a) Use threading.Event + thread.join() for a graceful shutdown (as done in
#         FileWatcher.stop()), giving the callback time to finish.
#      b) Wrap critical writes in try/finally to flush/close resources even when
#         interrupted.
#      c) Use atomics (write to a temp file then os.rename()) so partial writes
#         are never visible to readers.
#
#    daemon=True is therefore appropriate only for truly fire-and-forget background
#    tasks (e.g. a health-check pinger) where losing in-flight work on exit is
#    acceptable, or when you pair it with a proper shutdown sequence that joins
#    the thread before the main thread exits.
