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
import os
import queue
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
    """

    def __init__(self, path: Path, line_queue: queue.Queue, poll_interval: float = 0.5) -> None:
        self.path = path
        self.queue = line_queue
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="tailer")

    def start(self) -> "LogTailer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        # Seek to end so we only get NEW lines (tail -f behaviour)
        try:
            f = self.path.open()
            f.seek(0, 2)  # SEEK_END
        except FileNotFoundError:
            print(f"[tailer] file not found: {self.path}")
            return

        current_inode = os.stat(self.path).st_ino

        while not self._stop_event.is_set():
            # Detect log rotation: inode changed = file was replaced
            try:
                new_inode = os.stat(self.path).st_ino
                if new_inode != current_inode:
                    f.close()
                    f = self.path.open()
                    current_inode = new_inode
                    print("[tailer] log rotation detected, reopening file")
            except FileNotFoundError:
                time.sleep(self.poll_interval)
                continue

            line = f.readline()
            if line:
                self.queue.put(line.rstrip("\n"))
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


def tail_mode(path: Path) -> None:
    print(f"Tailing {path} (Ctrl-C to stop)...")
    q: queue.Queue = queue.Queue()
    tailer = LogTailer(path, q).start()
    try:
        while True:
            try:
                print(q.get(timeout=1))
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
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.watch:
        watch_mode(args.watch)
    elif args.tail:
        tail_mode(args.tail)
    else:
        demo()


if __name__ == "__main__":
    main()


# =============================================================================
# EXERCISES
# =============================================================================
# 1. BUG: LogTailer._run uses os.stat to detect rotation but doesn't handle
#    the case where the file is deleted and recreated with the same inode
#    (common on some filesystems).  What additional check would make this robust?
#
# 2. EXPAND: Add a --filter PATTERN flag to tail_mode that only prints lines
#    matching a regex pattern (like `tail -f app.log | grep ERROR`).
#
# 3. EXPAND: Add a max_queue_size to LogTailer so if the consumer is slow
#    the queue doesn't grow unbounded.  What should happen when it's full?
#
# 4. EXPAND: On Linux, replace the mtime polling in FileWatcher with inotify
#    via the `watchdog` library for immediate detection instead of polling.
#
# 5. THINK: FileWatcher uses daemon=True.  What are the implications for data
#    integrity if the main thread exits while the callback is mid-execution?
