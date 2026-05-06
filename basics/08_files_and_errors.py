#!/usr/bin/env python3
# =============================================================================
# 08_files_and_errors.py  —  Reading/writing files and handling exceptions
# Run: python 08_files_and_errors.py
# =============================================================================

import json                     # standard library module for reading/writing JSON
from pathlib import Path        # modern way to work with file paths (Python 3.4+)

# =============================================================================
# PART 1 — WRITING AND READING FILES
# =============================================================================

# --- Writing a text file ---
# open(path, mode)  — opens a file and returns a file object.
# Mode "w" = write (creates or OVERWRITES the file).
# Mode "a" = append (adds to the end without erasing existing content).
# Mode "r" = read (default mode).
# ALWAYS use 'with' — it guarantees the file is closed even if an error occurs.

with open("demo.txt", "w") as f:    # 'f' is the file object; 'with' closes it automatically
    f.write("Line 1: hello\n")      # \n is a newline character — moves to the next line
    f.write("Line 2: world\n")
    f.write("Line 3: done\n")
print("Wrote demo.txt")

# --- Reading the whole file at once ---
with open("demo.txt", "r") as f:    # "r" for read (also the default mode)
    content = f.read()              # reads the ENTIRE file into one string
print(f"Full content:\n{content}")

# --- Reading line by line ---
# For large files this is better than f.read() — only one line is in memory at a time.
with open("demo.txt") as f:         # "r" is implied when mode not given
    for line in f:                  # iterate — each 'line' includes the trailing \n
        line = line.strip()         # .strip() removes the \n and any surrounding whitespace
        print(f"  Line: {line}")

# --- Reading all lines into a list ---
with open("demo.txt") as f:
    lines = f.readlines()           # returns ["Line 1: hello\n", "Line 2: world\n", ...]
print(f"Number of lines: {len(lines)}")

# --- Appending to a file ---
with open("demo.txt", "a") as f:    # "a" = append mode: adds to end, never erases
    f.write("Line 4: appended\n")
print("Appended a line")

# =============================================================================
# PART 2 — PATHLIB  (modern path handling)
# =============================================================================

# pathlib.Path represents a file or directory path as an object with methods.
# It's safer and more readable than string concatenation for paths.

p = Path("demo.txt")               # create a Path object (file doesn't have to exist yet)

print(p.exists())                   # True — file exists on disk
print(p.name)                       # "demo.txt" — just the filename
print(p.suffix)                     # ".txt" — file extension
print(p.stem)                       # "demo" — filename without extension
print(p.parent)                     # "." — the directory containing the file

# Read entire file with pathlib (alternative to open())
text = p.read_text()                # reads the whole file into a string
print(f"Size: {len(text)} characters")

# Write a file with pathlib
Path("demo2.txt").write_text("Created by pathlib\n")

# Check and create a directory
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)       # create the directory; exist_ok=True = don't crash if it exists
(logs_dir / "app.log").write_text("first log line\n")   # / joins path segments (not division here)

# Glob — find files matching a pattern
for txt_file in Path(".").glob("*.txt"):    # all .txt files in current directory
    print(f"  Found: {txt_file}")

# =============================================================================
# PART 3 — JSON FILES  (very common in SRE/DevOps)
# =============================================================================

# JSON is a text format for structured data — used in configs, APIs, logs.
config = {
    "service": "api-gateway",
    "port": 8080,
    "replicas": 3,
    "features": ["auth", "rate-limit"],
}

# Write JSON to a file
with open("config.json", "w") as f:
    json.dump(config, f, indent=2)      # indent=2 makes it human-readable (pretty-print)
print("Wrote config.json")

# Read JSON from a file
with open("config.json") as f:
    loaded = json.load(f)               # parses JSON text → Python dict/list
print(loaded["service"])                # "api-gateway"
print(loaded["features"])              # ['auth', 'rate-limit']

# JSON ↔ string (without a file)
json_string = json.dumps(config)        # dict → JSON string  (dumps = dump to String)
back_to_dict = json.loads(json_string)  # JSON string → dict  (loads = load from String)
print(type(back_to_dict))              # <class 'dict'>

# =============================================================================
# PART 4 — EXCEPTION HANDLING  (try / except / finally)
# =============================================================================

# An exception is an error that occurs at runtime.
# Without handling, it crashes your script with a traceback.
# try/except lets you catch the error and respond gracefully.

# --- Basic try/except ---
try:                                # try to run this block
    number = int("not a number")    # int() raises ValueError if input isn't numeric
except ValueError as e:             # catch ValueError specifically; 'e' holds the error
    print(f"Caught ValueError: {e}")
# Script continues running after the except block

# --- Catching multiple exception types ---
def read_config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:           # file doesn't exist
        print(f"Config file not found: {path}")
        return {}                       # return empty dict as a safe default
    except json.JSONDecodeError as e:   # file exists but isn't valid JSON
        print(f"Invalid JSON in {path}: {e}")
        return {}

result = read_config("missing.json")    # file doesn't exist — prints warning, no crash
print(f"Got config: {result}")          # {}

# --- finally — always runs, even if an exception occurred ---
# Use it for cleanup (closing files, releasing locks, etc.)
def divide(a, b):
    try:
        result = a / b              # raises ZeroDivisionError if b == 0
        return result
    except ZeroDivisionError:
        print("Cannot divide by zero!")
        return None
    finally:
        print("divide() finished")  # runs whether or not an exception occurred

print(divide(10, 2))    # 5.0 — no exception; "divide() finished" still prints
print(divide(10, 0))    # exception caught; "divide() finished" still prints

# --- Raising your own exceptions ---
def set_replicas(n):
    if n < 1 or n > 100:
        raise ValueError(f"replicas must be 1-100, got {n}")   # raise stops execution
    print(f"Setting replicas to {n}")

try:
    set_replicas(200)           # raises ValueError
except ValueError as e:
    print(f"Bad input: {e}")

# --- Clean up demo files ---
import os
for fname in ["demo.txt", "demo2.txt", "config.json"]:
    if os.path.exists(fname):
        os.remove(fname)            # delete the temp files we created

# =============================================================================
# EXERCISES
# =============================================================================
# 1. Write a function 'save_servers(servers, path)' that writes a list of
#    server name strings to a text file, one per line.
#    Then write 'load_servers(path)' that reads it back into a list.
#    Test by saving ["web-01","web-02","db-01"] and loading it back.
#
# def save_servers(servers, path):
#     with open(path, "w") as f:
#         for server in servers:
#             f.write(??? + "\n")
#
# def load_servers(path):
#     with open(path) as f:
#         return [line.strip() for line in f if line.strip()]

# 2. Use try/except to handle the case where load_servers is called with a
#    path that doesn't exist — print a warning and return an empty list.

# 3. Write a dict as JSON to "alerts.json", then read it back and print
#    the value of the "severity" key.
#    alert = {"severity": "critical", "host": "db-01", "msg": "disk full"}
