#!/usr/bin/env python3
"""
04_subprocess_runner.py - Safe Subprocess / Shell Command Runner
SRE use-case: wrapping CLI tools (kubectl, terraform, docker, git) in Python
scripts for automation, with proper error handling and output capture.

Concepts: subprocess, shlex, logging, Popen vs run, timeouts, pipes
Run: python 04_subprocess_runner.py
"""

import logging
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

# Configure structured logging - in prod you'd output JSON for log aggregators
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


@dataclass
class CommandResult:
    cmd: str
    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def __str__(self) -> str:
        status = "OK" if self.ok else f"FAILED(rc={self.returncode})"
        return f"[{status}] `{self.cmd}` ({self.elapsed_s:.2f}s)"


def run_cmd(
    cmd: str,
    timeout: float = 30.0,
    env: Optional[dict] = None,
    cwd: Optional[str] = None,
    check: bool = False,
) -> CommandResult:
    """
    Run a shell command safely.
    - Uses shlex.split so you pass a plain string, not shell=True (avoids injection).
    - Captures stdout and stderr separately.
    - Enforces a timeout to prevent hangs in automation.
    """
    args: List[str] = shlex.split(cmd)
    log.info("Running: %s", cmd)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            args,
            capture_output=True,  # capture_output=True requires Python 3.7+
            text=True,            # decode stdout/stderr as str (not bytes)
            timeout=timeout,
            env={**os.environ, **(env or {})},  # merge caller env with process env
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        log.error("Command timed out after %ss: %s", timeout, cmd)
        return CommandResult(cmd=cmd, returncode=-1, stdout="", stderr="TIMEOUT", elapsed_s=timeout)
    except FileNotFoundError:
        log.error("Command not found: %s", args[0])
        return CommandResult(cmd=cmd, returncode=127, stdout="", stderr=f"not found: {args[0]}", elapsed_s=0)

    elapsed = time.monotonic() - start
    result = CommandResult(
        cmd=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
        elapsed_s=elapsed,
    )

    if result.ok:
        log.info("  %s", result)
    else:
        log.warning("  %s", result)
        if proc.stderr:
            log.warning("  stderr: %s", proc.stderr.strip()[:300])

    if check and not result.ok:
        raise subprocess.CalledProcessError(proc.returncode, cmd)

    return result


def run_streaming(cmd: str, timeout: float = 60.0) -> int:
    """
    Run a long-running command and stream its stdout line-by-line in real time.
    Useful for: terraform apply, docker build, test runners.
    Returns the exit code.
    """
    args = shlex.split(cmd)
    log.info("Streaming: %s", cmd)
    try:
        with subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr into stdout so we see it in order
            text=True,
            bufsize=1,                 # line-buffered
        ) as proc:
            deadline = time.monotonic() + timeout
            for line in proc.stdout:  # type: ignore[union-attr]
                print(f"  | {line}", end="")
                if time.monotonic() > deadline:
                    proc.kill()
                    log.error("Streaming command timed out: %s", cmd)
                    return -1
            proc.wait()
            return proc.returncode
    except FileNotFoundError:
        log.error("Command not found: %s", args[0])
        return 127


# ---------------------------------------------------------------------------
# Practical SRE scenarios
# ---------------------------------------------------------------------------

def demo_basic_commands() -> None:
    print("\n--- Basic command capture ---")
    # These work on Linux; on Windows they'll fail gracefully (FileNotFoundError)
    for cmd in [
        "uname -a",
        "df -h /",
        "free -m",
        "uptime",
        "hostname",
        "ls -la /tmp",
    ]:
        r = run_cmd(cmd)
        if r.ok and r.stdout:
            # Only show first line to keep output tidy
            print(f"  {r.stdout.splitlines()[0]}")


def demo_error_handling() -> None:
    print("\n--- Error / failure handling ---")

    # Command that will fail with non-zero exit
    r = run_cmd("ls /path/that/does/not/exist")
    print(f"  returncode={r.returncode}, stderr='{r.stderr[:60]}'")

    # Command not found
    r = run_cmd("notarealcommand --help")
    print(f"  returncode={r.returncode}, stderr='{r.stderr}'")

    # Timeout (sleep longer than our limit)
    r = run_cmd("sleep 5", timeout=1.0)
    print(f"  returncode={r.returncode}, stderr='{r.stderr}'")


def demo_env_injection() -> None:
    print("\n--- Custom environment variables ---")
    # SRE use: pass credentials or config as env vars, never as CLI args
    r = run_cmd("env", env={"MY_SECRET": "hunter2", "APP_ENV": "staging"})
    if r.ok:
        # Filter to just our custom vars
        relevant = [l for l in r.stdout.splitlines() if l.startswith("MY_") or l.startswith("APP_")]
        for line in relevant:
            print(f"  {line}")


def demo_pipeline() -> None:
    """
    Chaining commands safely - avoid shell=True pipelines.
    Instead, run each stage separately and connect via Python strings.
    """
    print("\n--- Safe pipeline (no shell=True) ---")
    r1 = run_cmd("ps aux")
    if r1.ok:
        # Filter in Python rather than piping to grep
        python_procs = [l for l in r1.stdout.splitlines() if "python" in l.lower()]
        print(f"  Found {len(python_procs)} python process(es)")


def main() -> None:
    demo_basic_commands()
    demo_error_handling()
    demo_env_injection()
    demo_pipeline()

    print("\n--- Streaming example (echo loop) ---")
    rc = run_streaming("bash -c 'for i in 1 2 3; do echo step $i; sleep 0.3; done'")
    print(f"  exit code: {rc}")


if __name__ == "__main__":
    main()


# =============================================================================
# EXERCISES
# =============================================================================
# 1. BUG: run_streaming merges stderr into stdout with STDOUT.  This means
#    error messages look identical to normal output.  Refactor it to capture
#    stderr separately and prefix those lines with "ERR | ".
#
# 2. EXPAND: Add a retry(n, delay) wrapper around run_cmd so transient
#    failures (e.g., network blips during `aws s3 cp`) are retried automatically.
#
# 3. EXPAND: Write a function `kubectl_rollout_status(deployment, namespace)`
#    that runs `kubectl rollout status deployment/<name> -n <ns>` and returns
#    True/False based on the output.  Handle the case where kubectl is not installed.
#
# 4. EXPAND: Add structured logging that emits JSON:
#    {"ts": "...", "cmd": "...", "rc": 0, "elapsed": 0.12}
#    so log lines can be ingested by Datadog/ELK without parsing.
#
# 5. THINK: Why is shell=True dangerous in an SRE script that accepts user
#    input?  Give a concrete example of a command injection attack it enables.
