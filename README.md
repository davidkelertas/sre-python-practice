# Python SRE Practice Scripts

Practice scripts for the Anduril Senior SRE interview. Each script covers
real DevOps/SRE patterns with exercises to debug and expand.

---

## Setup

These scripts assume **Linux** (the interview context) but most work on Windows too.
On a Linux machine or WSL:

```bash
cd ~/acme/python           # or wherever you cloned this

python3 -m venv .venv      # create isolated environment
source .venv/bin/activate  # activate it  (Windows: .venv\Scripts\activate)

pip install -r requirements.txt
```

Check it worked:
```bash
python -c "import psutil, requests, yaml, aiohttp; print('All deps OK')"
```

---

## Scripts

| File | Topic | Key Libraries |
|------|-------|---------------|
| `01_system_monitor.py` | CPU/memory/disk polling | psutil, dataclasses, argparse |
| `02_health_checker.py` | Concurrent HTTP checks | requests, threading, queue |
| `03_log_analyzer.py` | Regex log parsing | re, collections, generators |
| `04_subprocess_runner.py` | Wrapping CLI tools | subprocess, shlex, logging |
| `05_config_manager.py` | Layered config (file+env+CLI) | yaml, dataclasses, argparse |
| `06_file_watcher.py` | File change detection + log tail | threading, pathlib, queue |
| `07_async_health.py` | Async HTTP with asyncio | asyncio, aiohttp |
| `08_data_structures.py` | Ring buffer, LRU, heap, rate limiter | deque, heapq |

---

## Running each script

```bash
# 01 - run for 5 samples every 2 seconds
python 01_system_monitor.py --interval 2 --count 5

# 02 - check 6 built-in URLs with 3 worker threads
python 02_health_checker.py --workers 3

# 03 - generate 500 fake nginx log lines, then analyze them
python 03_log_analyzer.py --generate 500
python 03_log_analyzer.py --file sample.log

# 03 - pipe mode (works with any nginx log)
cat sample.log | python 03_log_analyzer.py

# 04 - run subprocess demos (some only work on Linux)
python 04_subprocess_runner.py

# 05 - show resolved config with defaults
python 05_config_manager.py
# Generate a config.yaml, then override via env var and CLI:
python 05_config_manager.py --dump-config
APP_DATABASE__HOST=replica.internal python 05_config_manager.py --env staging --log-level DEBUG

# 06 - self-contained demo (watch + tail simultaneously)
python 06_file_watcher.py --demo
# Watch a real file for changes (open another terminal and edit it):
python 06_file_watcher.py --watch config.yaml

# 07 - async health check (compare timing vs 02)
python 07_async_health.py
python 07_async_health.py --watch 10   # re-check every 10s

# 08 - data structure demos with assertions
python 08_data_structures.py
```

---

## Debugging tips

### Read tracebacks bottom-up
Python tracebacks show the innermost frame last.  The error line is at the
bottom; the call chain is above it.

```
Traceback (most recent call last):
  File "01_system_monitor.py", line 92, in main
    snap = monitor.collect()          <-- called here
  File "01_system_monitor.py", line 55, in collect
    cpu = psutil.cpu_percent(...)     <-- failed here  ← read this first
ZeroDivisionError: ...
```

### Use pdb (Python debugger)
Insert a breakpoint anywhere:
```python
import pdb; pdb.set_trace()   # legacy style
breakpoint()                   # Python 3.7+ shortcut
```
Key pdb commands: `n` (next line), `s` (step into), `c` (continue),
`p expr` (print expression), `l` (list source), `q` (quit).

### Print types when confused
```python
print(type(variable), variable)
```

### Check what a module provides
```python
import psutil
print(dir(psutil))
help(psutil.cpu_percent)
```

---

## Interview topic map

| Interview topic | Relevant scripts |
|-----------------|-----------------|
| Classes, OOP | 01, 02, 05, 06, 08 |
| Concurrency (threads) | 02, 06 |
| Async / asyncio | 07 |
| File I/O, pathlib | 03, 05, 06 |
| Regex | 03 |
| Data structures | 08 |
| subprocess / shell | 04 |
| CLI with argparse | 01, 02, 03, 05 |
| Error handling | 02, 04, 05, 07 |
| Logging | 04 |
| Config management | 05 |
| Generators | 03 |
| Type hints | all |

---

## What to focus on first

1. **Run each script** — understand what it does before reading the code.
2. **Read the exercises** at the bottom of each file.
3. **Attempt at least one exercise per script** — the bugs are real patterns
   you'll encounter in production code reviews.
4. **Be able to explain**: generators vs lists, threading vs asyncio,
   `subprocess.run` vs `Popen`, why `shell=True` is dangerous.
