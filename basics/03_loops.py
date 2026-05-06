#!/usr/bin/env python3
# =============================================================================
# 03_loops.py  —  for loops, while loops, range, break, continue
# Run: python 03_loops.py
# =============================================================================

# --- for loop ---
# Repeats a block of code once for each item in a sequence.
# 'item' is a temporary variable that holds the current value each iteration.

servers = ["web-01", "web-02", "db-01"]    # a list (covered in 05_lists.py)

for server in servers:          # 'server' takes each value in turn
    print(f"Checking {server}") # runs 3 times: web-01, web-02, db-01

# --- range() ---
# Generates a sequence of integers.  Very common in for loops.
# range(stop)        — 0, 1, 2, ... stop-1
# range(start, stop) — start, start+1, ... stop-1
# range(start, stop, step) — with a custom step

for i in range(5):              # i = 0, 1, 2, 3, 4  (stops BEFORE 5)
    print(f"  i = {i}")

print("---")
for i in range(1, 6):          # i = 1, 2, 3, 4, 5
    print(f"  i = {i}")

print("---")
for i in range(0, 10, 2):      # i = 0, 2, 4, 6, 8  (step of 2)
    print(f"  i = {i}")

# --- enumerate() — loop with index AND value ---
# enumerate() wraps a sequence and yields (index, value) pairs.
fruits = ["apple", "banana", "cherry"]

for index, fruit in enumerate(fruits):  # unpack tuple into two variables
    print(f"  [{index}] {fruit}")       # [0] apple, [1] banana, [2] cherry

# --- while loop ---
# Repeats a block as long as a condition is True.
# Use when you don't know in advance how many iterations you need.

count = 0
while count < 3:                # keep looping while count is less than 3
    print(f"count = {count}")
    count += 1                  # += is shorthand for count = count + 1
# After the loop, count = 3 (the condition became False)

# --- break — exit the loop early ---
# Stops the loop immediately, even if items remain.

for server in servers:
    if server == "db-01":
        print(f"Found database server: {server} — stopping search")
        break                   # jump out of the for loop entirely
    print(f"  Skipping {server}")

# Output:
#   Skipping web-01
#   Skipping web-02
#   Found database server: db-01 — stopping search

# --- continue — skip the current iteration ---
# Jumps to the next iteration without running the rest of the block.

for i in range(6):
    if i % 2 == 0:              # % is modulo — remainder after division
        continue                # skip even numbers
    print(f"  odd: {i}")        # only prints 1, 3, 5

# --- Nested loops ---
# A loop inside another loop.  The inner loop runs fully for each outer iteration.
environments = ["prod", "staging"]
roles        = ["web", "db"]

for env in environments:
    for role in roles:
        print(f"  {env}-{role}")    # prod-web, prod-db, staging-web, staging-db

# --- Looping over a string ---
# Strings are sequences too — you can loop over each character.
for char in "SRE":
    print(f"  char: {char}")    # S, R, E

# --- while with break — "loop forever until done" pattern ---
# Common in SRE scripts that poll until a condition is met.
import time                     # import a standard library module (covered later)

attempts = 0
max_attempts = 5

while True:                     # loops forever on its own
    attempts += 1
    print(f"  Attempt {attempts}...")
    if attempts >= max_attempts:
        print("  Max attempts reached — giving up")
        break                   # break is the ONLY way out of while True
    # In a real script you'd check if a service is up here

# =============================================================================
# EXERCISES
# =============================================================================
# 1. Use a for loop with range() to print the numbers 1 through 10.
#
# for i in ???:
#     print(i)

# 2. Use enumerate() to print each server in the list WITH its index:
#      0: web-01
#      1: web-02
#      2: db-01
#
# for ???, ??? in enumerate(servers):
#     print(???)

# 3. Use a for loop and 'continue' to print only the servers whose name
#    starts with "web".  Hint: use server.startswith("web")
#
# for server in servers:
#     if ???:
#         continue
#     print(server)
#
# Wait — should the continue go before or after the print?
# Think about it: continue skips the REST of the block, so where you put it matters.
