#!/usr/bin/env python3
# =============================================================================
# 02_conditionals.py  —  if / elif / else and Boolean Logic
# Run: python 02_conditionals.py
# =============================================================================

# --- Comparison operators ---
# These compare two values and return True or False.
print(5 > 3)    # True   — greater than
print(5 < 3)    # False  — less than
print(5 == 5)   # True   — equal to  (== not = because = means assignment)
print(5 != 3)   # True   — NOT equal to
print(5 >= 5)   # True   — greater than OR equal to
print(5 <= 4)   # False  — less than OR equal to

# --- if / elif / else ---
# Python uses INDENTATION (spaces) to define blocks — there are no { } braces.
# The standard indent is 4 spaces.  The colon : is required after every condition.

cpu_pct = 87.0          # pretend we just measured CPU usage

if cpu_pct >= 90:       # colon required — starts the 'if' block
    print("CRITICAL: CPU above 90%")   # 4 spaces indent — this line is inside the if
elif cpu_pct >= 80:     # 'elif' = else if — checked only when the above was False
    print("WARNING: CPU above 80%")    # runs because 87 >= 80 is True
else:                   # runs when ALL conditions above were False
    print("CPU OK")

# Result: WARNING: CPU above 80%

# --- Boolean operators: and, or, not ---
# 'and' — both sides must be True
# 'or'  — at least one side must be True
# 'not' — flips True to False and vice versa

is_weekend = False
is_holiday = True

if is_weekend or is_holiday:            # True because is_holiday is True
    print("Day off!")

disk_pct = 75
mem_pct  = 92

if disk_pct > 80 and mem_pct > 80:     # False — disk is fine
    print("Both disk AND memory are high")
else:
    print("At most one resource is high")

if not is_weekend:                      # not False = True
    print("It's a weekday")

# --- Chaining comparisons ---
# Python lets you write range checks naturally (like maths notation)
temp = 22
if 18 <= temp <= 25:    # same as: temp >= 18 and temp <= 25
    print(f"Temperature {temp}°C is comfortable")

# --- Inline if (ternary expression) ---
# Single-line shorthand for simple true/false choices.
# Format:  value_if_true  if  condition  else  value_if_false
status = "UP" if cpu_pct < 90 else "DOWN"      # "UP" because 87 < 90
print(f"Service status: {status}")

# --- Truthiness — what counts as True/False without == ---
# Python treats some values as automatically False:
#   0, 0.0, "", [], {}, None   →   False (called "falsy")
# Everything else is True ("truthy").

name = ""               # empty string is falsy
if name:                # same as: if name != ""
    print(f"Hello, {name}")
else:
    print("No name provided")   # runs because "" is falsy

items = [1, 2, 3]
if items:               # a non-empty list is truthy
    print(f"List has {len(items)} items")

# --- in operator ---
# Checks whether a value is inside a sequence (list, string, dict).
allowed_users = ["alice", "bob", "carol"]
user = "bob"

if user in allowed_users:           # True — "bob" is in the list
    print(f"{user} is allowed")

hostname = "web-prod-01"
if "prod" in hostname:              # checks if "prod" is a substring
    print("This is a production server — be careful!")

# =============================================================================
# EXERCISES
# =============================================================================
# 1. Write an if/elif/else that prints a health label based on disk_pct:
#      >= 90  ->  "CRITICAL"
#      >= 75  ->  "WARNING"
#      anything else -> "OK"
#    Test with disk_pct = 60, 80, 95
#
# disk_pct = 80
# if ???:
#     print("CRITICAL")
# elif ???:
#     print("WARNING")
# else:
#     print("OK")

# 2. Use 'and' to print "All clear" only when cpu_pct < 80 AND disk_pct < 75.

# 3. Write a one-liner (ternary) that sets label = "FAIL" if mem_pct > 90,
#    otherwise label = "OK".  Then print label.
#    mem_pct = 92
#    label = ???
#    print(label)
