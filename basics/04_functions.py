#!/usr/bin/env python3
# =============================================================================
# 04_functions.py  —  Defining and calling functions
# Run: python 04_functions.py
# =============================================================================

# --- What is a function? ---
# A function is a reusable block of code with a name.
# You DEFINE it once with 'def', then CALL it as many times as you want.
# This avoids copy-pasting the same code in multiple places.

# --- Basic function (no parameters, no return value) ---
def greet():                        # 'def' starts the definition; colon required
    print("Hello from a function!") # indented block = function body
# Nothing runs yet — we've only defined it, not called it.

greet()     # CALL the function — now the body runs
greet()     # call it again — functions are reusable

# --- Function with parameters ---
# Parameters are variables that the caller passes IN to the function.
def greet_user(name):               # 'name' is a parameter (a local variable)
    print(f"Hello, {name}!")

greet_user("Alice")     # "Alice" is the argument — it becomes name inside the function
greet_user("Bob")       # different argument, same function

# --- Function that returns a value ---
# 'return' sends a value back to whoever called the function.
def add(a, b):
    result = a + b      # compute something
    return result       # send result back to the caller

total = add(3, 4)       # total = 7 (the returned value)
print(f"3 + 4 = {total}")

# You don't need to store the return value — you can use it directly
print(f"10 + 20 = {add(10, 20)}")

# --- Default parameter values ---
# If a caller doesn't pass an argument, the default is used.
# Defaults must come AFTER parameters without defaults.
def check_cpu(pct, threshold=80):           # threshold defaults to 80
    if pct >= threshold:
        return f"ALERT: CPU at {pct}%"
    return f"OK: CPU at {pct}%"

print(check_cpu(95))            # uses default threshold=80 → ALERT
print(check_cpu(95, 99))        # overrides threshold=99 → OK
print(check_cpu(pct=50))        # keyword argument — name=value syntax

# --- Keyword arguments ---
# You can pass arguments by name in any order using name=value.
def describe_server(name, env, role="web"):
    print(f"Server: {name}, Env: {env}, Role: {role}")

describe_server("web-01", "prod")               # positional, role defaults to "web"
describe_server(env="staging", name="db-01", role="db")   # keyword, any order

# --- Multiple return values (actually a tuple) ---
# Python functions can return more than one value — separated by commas.
# They come back as a tuple, which you can unpack into multiple variables.
def min_max(numbers):
    return min(numbers), max(numbers)   # returns a tuple: (min, max)

low, high = min_max([3, 1, 7, 2, 9])   # unpack the tuple into two variables
print(f"min={low}  max={high}")         # min=1  max=9

# --- Docstrings — documenting your function ---
# A string as the very first line of the function body is its documentation.
def is_healthy(status_code):
    """Return True if status_code is a 2xx HTTP response."""   # docstring
    return 200 <= status_code < 300

print(is_healthy(200))   # True
print(is_healthy(503))   # False
print(is_healthy.__doc__)  # prints the docstring

# --- Functions calling functions ---
# Functions can call other functions — this is how you build up complex programs.
def bytes_to_mb(bytes_count):
    """Convert bytes to megabytes."""
    return bytes_count / (1024 * 1024)

def format_size(bytes_count):
    """Return a human-readable size string."""
    mb = bytes_to_mb(bytes_count)       # calls another function
    return f"{mb:.1f} MB"

print(format_size(5_242_880))   # 5.0 MB  (underscore in numbers is legal — visual grouping)

# --- Variable scope ---
# Variables defined INSIDE a function only exist during that function call.
# They are NOT accessible outside.
def my_func():
    local_var = "I only exist inside my_func"
    print(local_var)

my_func()
# print(local_var)  # ← this would crash with NameError — local_var doesn't exist here

# Variables defined OUTSIDE functions (module level) are accessible everywhere.
GLOBAL_TIMEOUT = 5.0    # convention: UPPER_CASE for module-level constants

def get_timeout():
    return GLOBAL_TIMEOUT   # reads the module-level variable

print(f"Timeout: {get_timeout()}s")

# =============================================================================
# EXERCISES
# =============================================================================
# 1. Write a function called 'celsius_to_fahrenheit' that takes a celsius float
#    and returns the fahrenheit equivalent.  Formula: (c * 9/5) + 32
#    Then print: "20°C = <result>°F"
#
# def celsius_to_fahrenheit(celsius):
#     ???
#
# print(???)

# 2. Write a function 'health_label(pct, warn=75, crit=90)' that returns:
#      "CRITICAL" if pct >= crit
#      "WARNING"  if pct >= warn
#      "OK"       otherwise
#    Test with pct = 60, 80, 95
#
# def health_label(pct, warn=75, crit=90):
#     ???

# 3. Write a function 'summarise(numbers)' that returns THREE values:
#    the count, the sum, and the average.  Use it like:
#      count, total, avg = summarise([10, 20, 30, 40])
#    Hint: len() gives count, sum() gives total, average = total / count
