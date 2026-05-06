#!/usr/bin/env python3
# =============================================================================
# 06_dicts.py  —  Dictionaries: key-value storage, iteration, nesting
# Run: python 06_dicts.py
# =============================================================================

# --- What is a dict? ---
# A dictionary maps KEYS to VALUES.  Think of it like a lookup table:
#   key     →  value
#   "name"  →  "web-01"
#   "cpu"   →  87.5
# Keys must be unique and immutable (strings and ints are the most common).
# Values can be anything.
# Dicts are defined with curly braces { }.

server = {
    "name":    "web-01",    # key: "name",  value: "web-01"
    "env":     "prod",
    "cpu_pct": 87.5,
    "healthy": True,
}

print(server)               # prints the whole dict
print(type(server))         # <class 'dict'>

# --- Accessing values ---
# Use square brackets with the key to get its value.
print(server["name"])       # "web-01"
print(server["cpu_pct"])    # 87.5

# --- KeyError — accessing a key that doesn't exist crashes ---
# print(server["uptime"])   # ← would raise KeyError: 'uptime'

# .get() is safer: returns None (or a default) instead of crashing
print(server.get("uptime"))         # None — key doesn't exist, no crash
print(server.get("uptime", 0))      # 0    — returns the default you provide

# --- Checking if a key exists ---
print("name" in server)     # True
print("uptime" in server)   # False

# --- Adding and updating values ---
server["region"] = "ap-southeast-2"    # add a NEW key-value pair
print(server["region"])                 # "ap-southeast-2"

server["cpu_pct"] = 92.0               # UPDATE existing value (overwrites 87.5)
print(server["cpu_pct"])               # 92.0

# --- Deleting a key ---
del server["region"]                    # removes the key entirely
print("region" in server)              # False

# --- Iterating over a dict ---
# .keys()   — iterate over keys only
# .values() — iterate over values only
# .items()  — iterate over (key, value) pairs  ← most commonly used

for key in server.keys():
    print(f"  key: {key}")

for value in server.values():
    print(f"  value: {value}")

for key, value in server.items():      # unpack each pair into two variables
    print(f"  {key}: {value}")

# --- Dict comprehension ---
# Same idea as list comprehension — build a dict in one line.
# Format:  {key_expression: value_expression  for  variable  in  sequence}

# Build a dict mapping server names to their CPU readings
names = ["web-01", "web-02", "db-01"]
cpus  = [87.5, 42.0, 63.1]

cpu_map = {name: cpu for name, cpu in zip(names, cpus)}
# zip() pairs up two lists: [("web-01", 87.5), ("web-02", 42.0), ("db-01", 63.1)]
print(cpu_map)      # {'web-01': 87.5, 'web-02': 42.0, 'db-01': 63.1}

# Filter — only servers with cpu > 60
high_cpu = {name: cpu for name, cpu in cpu_map.items() if cpu > 60}
print(high_cpu)     # {'web-01': 87.5, 'db-01': 63.1}

# --- Nested dicts — dicts inside dicts ---
# Common for structured config or API responses.
cluster = {
    "web-01": {"env": "prod",    "cpu": 87.5, "healthy": True},
    "web-02": {"env": "prod",    "cpu": 42.0, "healthy": True},
    "db-01":  {"env": "prod",    "cpu": 63.1, "healthy": False},
}

# Access nested values by chaining []
print(cluster["db-01"]["healthy"])          # False
print(cluster["web-01"]["cpu"])             # 87.5

# Iterate and check nested values
for server_name, info in cluster.items():
    status = "UP" if info["healthy"] else "DOWN"
    print(f"  {server_name}: {status}  cpu={info['cpu']}")

# --- Useful dict methods ---
print(list(server.keys()))      # list of all keys
print(len(server))              # number of key-value pairs

# .update() merges another dict IN (overwrites duplicates)
overrides = {"cpu_pct": 50.0, "new_field": "abc"}
server.update(overrides)
print(server["cpu_pct"])        # 50.0  (was 92.0)
print(server["new_field"])      # "abc" (new key added)

# dict() constructor — build a dict from keyword arguments
config = dict(host="localhost", port=5432, timeout=30)
print(config)   # {'host': 'localhost', 'port': 5432, 'timeout': 30}

# =============================================================================
# EXERCISES
# =============================================================================
# 1. Create a dict called 'alert' with keys: 'severity', 'message', 'host'.
#    Set severity="critical", message="disk full", host="db-01".
#    Print each value using its key.
#
# alert = {???}
# print(alert[???])

# 2. Loop over the 'cluster' dict above and print ONLY the unhealthy servers.
#    Expected output:  "db-01 is DOWN"
#
# for name, info in cluster.items():
#     if ???:
#         print(???)

# 3. Use a dict comprehension to build a dict of server_name → "OK"/"FAIL"
#    based on the 'healthy' field in the cluster dict.
#    Expected: {'web-01': 'OK', 'web-02': 'OK', 'db-01': 'FAIL'}
#
# status_map = {??? : ??? for ???, ??? in cluster.items()}
# print(status_map)
