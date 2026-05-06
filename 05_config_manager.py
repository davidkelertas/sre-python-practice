#!/usr/bin/env python3
"""
05_config_manager.py - Layered Config Manager
Real apps need config from multiple sources: defaults → file → env vars → CLI.
Each layer overrides the previous.  This is how tools like kubectl, terraform,
and docker-compose work.

Concepts: dataclasses, yaml, json, argparse, os.environ, type hints,
          __post_init__, validation, immutability pattern
Run: python 05_config_manager.py
Run with overrides: python 05_config_manager.py --env production --log-level DEBUG
Generate a sample config: python 05_config_manager.py --dump-config
"""

import argparse
import copy
import json
import logging
import os
import sys
import threading
import time
import unittest
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import yaml
except ImportError:
    raise SystemExit("pip install pyyaml")


# ---------------------------------------------------------------------------
# Config schema - using a dataclass gives us type hints, defaults, and a
# clean __repr__ for free.
# ---------------------------------------------------------------------------

@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    name: str = "app"
    pool_size: int = 10

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError(f"Invalid database port: {self.port}")
        if self.pool_size < 1:
            raise ValueError(f"pool_size must be >= 1, got {self.pool_size}")


@dataclass
class AppConfig:
    env: str = "development"
    log_level: str = "INFO"
    listen_port: int = 8080
    debug: bool = False
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    # feature flags - a list shows how nested collections work
    features: List[str] = field(default_factory=list)

    # Allowed log levels - validated after init
    _VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    _VALID_ENVS = {"development", "staging", "production"}

    def __post_init__(self) -> None:
        self.log_level = self.log_level.upper()
        if self.log_level not in self._VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of {self._VALID_LOG_LEVELS}")
        if self.env not in self._VALID_ENVS:
            raise ValueError(f"env must be one of {self._VALID_ENVS}")
        if not 1 <= self.listen_port <= 65535:
            raise ValueError(f"Invalid listen_port: {self.listen_port}")


# ---------------------------------------------------------------------------
# Loader: each layer merges into a plain dict before constructing the dataclass
# ---------------------------------------------------------------------------

def load_yaml_file(path: Path) -> Dict[str, Any]:
    """Returns {} if file doesn't exist - makes layering safe."""
    if not path.exists():
        return {}
    with path.open() as f:
        data = yaml.safe_load(f)
    return data or {}


def load_env_vars(prefix: str = "APP_") -> Dict[str, Any]:
    """
    Map environment variables to config keys.
    APP_LOG_LEVEL=DEBUG  →  {"log_level": "DEBUG"}
    APP_DB_HOST=pg       →  {"database": {"host": "pg"}}

    Double-underscore separates nested keys:  APP_DATABASE__PORT=5433
    """
    config: Dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        # Strip prefix, lowercase, split on double-underscore for nesting
        trimmed = key[len(prefix):].lower()
        parts = trimmed.split("__")

        # Coerce obvious types: "true"/"false" → bool, digits → int
        coerced: Any = value
        if value.lower() in ("true", "false"):
            coerced = value.lower() == "true"
        elif value.isdigit():
            coerced = int(value)

        if len(parts) == 1:
            config[parts[0]] = coerced
        elif len(parts) == 2:
            # One level of nesting (e.g., database.host)
            config.setdefault(parts[0], {})[parts[1]] = coerced

    return config


def deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge override into base.  Returns a new dict.

    Uses copy.deepcopy on every nested dict from *base* so that the caller's
    original dicts are never mutated, even across multiple merge calls.
    """
    # Deep-copy the base so we never mutate the caller's dict.
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            # Deep-copy override values that are dicts so callers stay isolated.
            result[key] = copy.deepcopy(value) if isinstance(value, dict) else value
    return result


def build_config(
    config_file: Optional[Path] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
    env_prefix: str = "APP_",
) -> AppConfig:
    """
    Layered config resolution (lowest → highest priority):
      1. AppConfig dataclass defaults
      2. YAML config file
      3. Environment variables (APP_* prefix)
      4. CLI flags
    """
    # Start with dataclass defaults expressed as a dict
    defaults = asdict(AppConfig())

    # Layer 2: file
    file_cfg = load_yaml_file(config_file or Path("config.yaml"))

    # Layer 3: environment variables
    env_cfg = load_env_vars(env_prefix)

    # Layer 4: CLI
    cli_cfg = cli_overrides or {}

    # Merge in order
    merged = defaults
    for layer in (file_cfg, env_cfg, cli_cfg):
        merged = deep_merge(merged, layer)

    # Construct and validate the typed dataclass
    db_data = merged.pop("database", {})
    db = DatabaseConfig(**db_data)
    return AppConfig(database=db, **merged)


# ---------------------------------------------------------------------------
# Exercise 2 – Secrets layer (Docker secrets pattern)
# ---------------------------------------------------------------------------

_secrets_logger = logging.getLogger(__name__)


def load_secrets(secrets_dir: str = "/run/secrets") -> Dict[str, Any]:
    """Read Docker-style secrets from a directory.

    Each file in *secrets_dir* becomes a config key whose value is the file's
    text content (stripped).  Secret *values* are never logged; only key names
    are mentioned at DEBUG level so operators can see which secrets were loaded
    without exposing the values.

    Example:
        /run/secrets/db_password  →  {"db_password": "<contents>"}
    """
    secrets: Dict[str, Any] = {}
    dir_path = Path(secrets_dir)
    if not dir_path.is_dir():
        _secrets_logger.debug("Secrets directory %s not found – skipping.", secrets_dir)
        return secrets

    for secret_file in dir_path.iterdir():
        if not secret_file.is_file():
            continue
        key = secret_file.name
        try:
            value = secret_file.read_text(encoding="utf-8").strip()
            secrets[key] = value
            # Log the KEY only – never the value.
            _secrets_logger.debug("Loaded secret key: %s", key)
        except OSError as exc:
            _secrets_logger.warning("Could not read secret %s: %s", key, exc)

    return secrets


# ---------------------------------------------------------------------------
# Exercise 3 – Manual field-level validation (no jsonschema dependency)
# ---------------------------------------------------------------------------

def validate_config_dict(cfg: Dict[str, Any]) -> None:
    """Validate a raw config dict before constructing dataclasses.

    Raises ValueError with a clear field-level message for the first error
    found.  Checks types and value ranges for all known top-level and database
    fields.
    """
    valid_envs = {"development", "staging", "production"}
    valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    # --- top-level fields ---
    if "env" in cfg:
        if not isinstance(cfg["env"], str):
            raise ValueError(f"'env' must be a string, got {type(cfg['env']).__name__!r}")
        if cfg["env"] not in valid_envs:
            raise ValueError(
                f"'env' must be one of {sorted(valid_envs)}, got {cfg['env']!r}"
            )

    if "log_level" in cfg:
        if not isinstance(cfg["log_level"], str):
            raise ValueError(
                f"'log_level' must be a string, got {type(cfg['log_level']).__name__!r}"
            )
        if cfg["log_level"].upper() not in valid_log_levels:
            raise ValueError(
                f"'log_level' must be one of {sorted(valid_log_levels)}, "
                f"got {cfg['log_level']!r}"
            )

    if "listen_port" in cfg:
        if not isinstance(cfg["listen_port"], int):
            raise ValueError(
                f"'listen_port' must be an int, got {type(cfg['listen_port']).__name__!r}"
            )
        if not 1 <= cfg["listen_port"] <= 65535:
            raise ValueError(
                f"'listen_port' must be 1–65535, got {cfg['listen_port']}"
            )

    if "debug" in cfg:
        if not isinstance(cfg["debug"], bool):
            raise ValueError(
                f"'debug' must be a bool, got {type(cfg['debug']).__name__!r}"
            )

    if "features" in cfg:
        if not isinstance(cfg["features"], list):
            raise ValueError(
                f"'features' must be a list, got {type(cfg['features']).__name__!r}"
            )
        for i, item in enumerate(cfg["features"]):
            if not isinstance(item, str):
                raise ValueError(
                    f"'features[{i}]' must be a string, got {type(item).__name__!r}"
                )

    # --- database sub-dict ---
    db = cfg.get("database")
    if db is not None:
        if not isinstance(db, dict):
            raise ValueError(
                f"'database' must be a mapping, got {type(db).__name__!r}"
            )

        if "host" in db:
            if not isinstance(db["host"], str) or not db["host"]:
                raise ValueError("'database.host' must be a non-empty string")

        if "port" in db:
            if not isinstance(db["port"], int):
                raise ValueError(
                    f"'database.port' must be an int, got {type(db['port']).__name__!r}"
                )
            if not 1 <= db["port"] <= 65535:
                raise ValueError(
                    f"'database.port' must be 1–65535, got {db['port']}"
                )

        if "pool_size" in db:
            if not isinstance(db["pool_size"], int):
                raise ValueError(
                    f"'database.pool_size' must be an int, "
                    f"got {type(db['pool_size']).__name__!r}"
                )
            if db["pool_size"] < 1:
                raise ValueError(
                    f"'database.pool_size' must be >= 1, got {db['pool_size']}"
                )

        if "name" in db:
            if not isinstance(db["name"], str) or not db["name"]:
                raise ValueError("'database.name' must be a non-empty string")


# ---------------------------------------------------------------------------
# Exercise 4 – Config reload on file change (background watcher thread)
# ---------------------------------------------------------------------------

def watch_and_reload(
    config_file: Path,
    callback: Callable[[AppConfig], None],
    interval: float = 2.0,
) -> threading.Thread:
    """Start a daemon thread that watches *config_file* for mtime changes.

    When the file's last-modified time changes, ``build_config`` is called and
    the new :class:`AppConfig` is passed to *callback*.  Errors during reload
    are logged but never crash the watcher.

    Args:
        config_file: Path to the YAML config file to monitor.
        callback:    Called with the freshly built AppConfig on each change.
        interval:    Polling interval in seconds (default 2).

    Returns:
        The started daemon thread (already running).  The caller does not need
        to join it; it will stop automatically when the main process exits.

    Example::

        def on_reload(cfg: AppConfig) -> None:
            print("Config reloaded:", cfg.log_level)

        watch_and_reload(Path("config.yaml"), on_reload, interval=5)
    """
    _watcher_logger = logging.getLogger(__name__ + ".watcher")

    def _poll() -> None:
        last_mtime: Optional[float] = None
        while True:
            try:
                mtime = config_file.stat().st_mtime if config_file.exists() else None
                if mtime != last_mtime and last_mtime is not None:
                    _watcher_logger.info(
                        "Config file %s changed – reloading.", config_file
                    )
                    new_cfg = build_config(config_file=config_file)
                    callback(new_cfg)
                last_mtime = mtime
            except Exception as exc:  # pylint: disable=broad-except
                _watcher_logger.error("Error during config reload: %s", exc)
            time.sleep(interval)

    thread = threading.Thread(target=_poll, name="config-watcher", daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Config manager demo")
    p.add_argument("--config", type=Path, default=Path("config.yaml"))
    p.add_argument("--env", choices=["development", "staging", "production"])
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.add_argument("--port", type=int)
    p.add_argument("--debug", action="store_true", default=None)
    p.add_argument("--dump-config", action="store_true", help="Write a sample config.yaml and exit")
    return p.parse_args()


SAMPLE_CONFIG = """
env: staging
log_level: INFO
listen_port: 9090
features:
  - dark_mode
  - new_dashboard
database:
  host: postgres.internal
  port: 5432
  name: myapp
  pool_size: 20
"""


def main() -> None:
    args = parse_args()

    if args.dump_config:
        path = Path("config.yaml")
        path.write_text(SAMPLE_CONFIG.strip())
        print(f"Wrote sample config to {path}")
        sys.exit(0)

    # Build CLI override dict - only include flags that were actually set
    cli_overrides: Dict[str, Any] = {}
    if args.env:
        cli_overrides["env"] = args.env
    if args.log_level:
        cli_overrides["log_level"] = args.log_level
    if args.port:
        cli_overrides["listen_port"] = args.port
    if args.debug:
        cli_overrides["debug"] = True

    try:
        cfg = build_config(config_file=args.config, cli_overrides=cli_overrides)
    except ValueError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    print("Resolved configuration:")
    print(json.dumps(asdict(cfg), indent=2))
    print(f"\nActive environment  : {cfg.env}")
    print(f"Database endpoint  : {cfg.database.host}:{cfg.database.port}/{cfg.database.name}")
    print(f"Features enabled   : {cfg.features or ['(none)']}")

    # Demonstrate env-var override without touching the file:
    print("\nTip: override any field via env var:")
    print("  APP_LOG_LEVEL=DEBUG APP_DATABASE__HOST=replica.db python 05_config_manager.py")


if __name__ == "__main__":
    main()


# =============================================================================
# EXERCISES
# =============================================================================
# 1. BUG: deep_merge modifies the `base` dict in some edge cases.
#    Write a unit test using `unittest` that proves this and then fix deep_merge.
#    Hint: try merging {"a": {"b": 1}} with {"a": {"c": 2}} twice.
#
# 2. EXPAND: Add a secrets layer that reads from a file like /run/secrets/db_password
#    (Docker secrets pattern) and never logs the values.
#
# 3. EXPAND: Add JSON Schema validation using `jsonschema` so invalid config
#    produces a clear field-level error message rather than a Python TypeError.
#
# 4. EXPAND: Support config reload at runtime: watch config.yaml with a
#    background thread (see 06_file_watcher.py) and rebuild the config on change.
#
# 5. THINK: The dataclass uses field(default_factory=list) for `features`.
#    What would go wrong if you wrote `features: List[str] = []` instead?
#    (This is one of Python's most common gotchas.)
#
# ---------------------------------------------------------------------------
# EXERCISE 5 – THINK answer
# ---------------------------------------------------------------------------
# If you wrote:
#
#     features: List[str] = []
#
# Python would raise a TypeError at class definition time:
#   "mutable default <class 'list'> … is not allowed: use default_factory"
#
# Why?  In a plain function, `def f(x=[])` shares the *same* list object
# across all calls that omit the argument — this is Python's infamous mutable
# default argument gotcha.  Dataclasses detect mutable defaults (list, dict,
# set) and refuse to allow them, because each instance must own its own list.
# Without that protection, appending to one instance's `features` would silently
# corrupt every other instance.
#
# `field(default_factory=list)` tells the dataclass machinery to call `list()`
# freshly for every new instance, so each instance gets its own independent
# empty list.  The same applies to `database: DatabaseConfig` — that's why it
# uses `field(default_factory=DatabaseConfig)` rather than a bare default.
#
# ---------------------------------------------------------------------------
# EXERCISE 1 – Unit tests (proves the original bug then verifies the fix)
# ---------------------------------------------------------------------------


class TestDeepMerge(unittest.TestCase):
    """Tests for deep_merge – non-mutation guarantee."""

    def test_original_bug_nested_dict_mutation(self) -> None:
        """The old implementation mutated base's nested dict across two merges.

        Concretely: merging base={"a": {"b": 1}} with {"a": {"c": 2}} used to
        update the *same* inner dict object that lives in `base`, so a second
        merge would see the side-effects of the first.  Prove it is now fixed.
        """
        base = {"a": {"b": 1}}
        override1 = {"a": {"c": 2}}
        override2 = {"a": {"d": 3}}

        result1 = deep_merge(base, override1)
        result2 = deep_merge(base, override2)

        # base must be completely untouched
        self.assertEqual(base, {"a": {"b": 1}}, "deep_merge must not mutate base")

        # Each result must contain only what was merged in for that call
        self.assertEqual(result1, {"a": {"b": 1, "c": 2}})
        self.assertEqual(result2, {"a": {"b": 1, "d": 3}})

        # And the two results must be independent of each other
        self.assertNotIn("d", result1["a"], "result1 must not contain keys from result2")
        self.assertNotIn("c", result2["a"], "result2 must not contain keys from result1")

    def test_nested_value_independence(self) -> None:
        """Mutating the result must not affect base or vice-versa."""
        base = {"db": {"host": "localhost", "port": 5432}}
        override = {"db": {"port": 9999}}

        result = deep_merge(base, override)
        # Mutate result's nested dict
        result["db"]["host"] = "remote"

        self.assertEqual(base["db"]["host"], "localhost",
                         "Mutating result must not affect base")

    def test_override_value_independence(self) -> None:
        """Mutating the override's nested dict after the call must not affect result."""
        base = {"x": 1}
        override = {"nested": {"key": "value"}}

        result = deep_merge(base, override)
        override["nested"]["key"] = "mutated"

        self.assertEqual(result["nested"]["key"], "value",
                         "Mutating override after merge must not affect result")

    def test_flat_merge(self) -> None:
        """Simple flat merge still works correctly."""
        self.assertEqual(
            deep_merge({"a": 1, "b": 2}, {"b": 99, "c": 3}),
            {"a": 1, "b": 99, "c": 3},
        )

    def test_empty_override(self) -> None:
        """Merging with an empty override returns a copy of base."""
        base = {"a": {"b": 1}}
        result = deep_merge(base, {})
        self.assertEqual(result, base)
        self.assertIsNot(result, base)

    def test_empty_base(self) -> None:
        """Merging into an empty base returns a (deep) copy of override."""
        override = {"a": {"b": 1}}
        result = deep_merge({}, override)
        self.assertEqual(result, override)
        self.assertIsNot(result, override)


def run_tests() -> None:
    """Run all unit tests for this module."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestDeepMerge)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
