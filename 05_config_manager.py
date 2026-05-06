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
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    """Recursively merge override into base.  Returns a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
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
