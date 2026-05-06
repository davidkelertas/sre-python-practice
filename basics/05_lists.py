#!/usr/bin/env python3
# =============================================================================
# 05_lists.py  —  Lists: creating, indexing, slicing, modifying, iterating
# Run: python 05_lists.py
# =============================================================================

# --- What is a list? ---
# A list is an ordered, changeable collection of items.
# Items can be any type — strings, ints, floats, even other lists.
# Lists are defined with square brackets [ ].

servers = ["web-01", "web-02", "db-01"]   # list of strings
cpu_readings = [72.1, 81.3, 65.0, 90.5]  # list of floats
mixed = ["hello", 42, True, 3.14]         # lists can hold different types (but avoid this)

print(servers)          # prints the full list: ['web-01', 'web-02', 'db-01']
print(len(servers))     # len() = number of items = 3

# --- Indexing — accessing one item ---
# Python uses zero-based indexing: first item is index 0.
# Negative indices count from the END: -1 is the last item.

print(servers[0])       # "web-01"   — first item
print(servers[1])       # "web-02"   — second item
print(servers[2])       # "db-01"    — third (last) item
print(servers[-1])      # "db-01"    — same as servers[2]: last item
print(servers[-2])      # "web-02"   — second to last

# --- Slicing — getting a sub-list ---
# list[start:stop]  — items from index start up to (but NOT including) stop
# list[start:]      — from start to the end
# list[:stop]       — from the beginning up to stop
# list[:]           — a copy of the whole list

nums = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
print(nums[2:5])        # [2, 3, 4]   — index 2, 3, 4 (stop=5 not included)
print(nums[:3])         # [0, 1, 2]   — first 3
print(nums[7:])         # [7, 8, 9]   — from index 7 to end
print(nums[-3:])        # [7, 8, 9]   — last 3 items (same result)
print(nums[::2])        # [0, 2, 4, 6, 8] — every 2nd item (step=2)
print(nums[::-1])       # [9, 8, 7, 6, 5, 4, 3, 2, 1, 0] — reversed

# --- Modifying a list ---
# Lists are MUTABLE — you can change them after creation.

servers.append("cache-01")          # adds one item to the END
print(servers)                      # ['web-01', 'web-02', 'db-01', 'cache-01']

servers.insert(1, "web-00")         # insert at index 1, shifting others right
print(servers)                      # ['web-01', 'web-00', 'web-02', 'db-01', 'cache-01']

servers.remove("web-00")            # remove by VALUE (first match)
print(servers)                      # ['web-01', 'web-02', 'db-01', 'cache-01']

popped = servers.pop()              # remove and RETURN the last item
print(f"Popped: {popped}")          # cache-01
print(servers)                      # ['web-01', 'web-02', 'db-01']

servers.pop(0)                      # remove by INDEX (removes 'web-01')
print(servers)                      # ['web-02', 'db-01']

# Reset for further examples
servers = ["web-01", "web-02", "db-01"]

servers[0] = "web-NEW"              # change an item by index
print(servers)                      # ['web-NEW', 'web-02', 'db-01']
servers[0] = "web-01"               # put it back

# --- Checking membership ---
print("web-01" in servers)          # True  — 'in' checks if value exists
print("web-99" in servers)          # False

# --- Sorting ---
readings = [90.5, 72.1, 81.3, 65.0]
readings.sort()                     # sort IN PLACE (modifies the list)
print(readings)                     # [65.0, 72.1, 81.3, 90.5]

readings.sort(reverse=True)         # sort descending
print(readings)                     # [90.5, 81.3, 72.1, 65.0]

sorted_servers = sorted(servers)    # sorted() returns a NEW list, doesn't modify original
print(sorted_servers)
print(servers)                      # original unchanged

# --- Combining lists ---
a = [1, 2, 3]
b = [4, 5, 6]
combined = a + b                    # + creates a NEW list with all items
print(combined)                     # [1, 2, 3, 4, 5, 6]

a.extend(b)                         # extend() adds all items of b INTO a (modifies a)
print(a)                            # [1, 2, 3, 4, 5, 6]

# --- List comprehension — building a list with one line ---
# Format: [expression  for  variable  in  sequence]
# This is VERY common Python — it replaces a for loop that builds a list.

# Without comprehension:
squares = []
for n in range(1, 6):
    squares.append(n ** 2)          # ** is the power operator: 2**3 = 8
print(squares)                      # [1, 4, 9, 16, 25]

# With comprehension — same result, one line:
squares = [n ** 2 for n in range(1, 6)]
print(squares)                      # [1, 4, 9, 16, 25]

# With a filter — only include items that match a condition:
high_cpu = [r for r in cpu_readings if r > 80]   # only values > 80
print(high_cpu)                                   # [81.3, 90.5]

# Transform items:
server_upper = [s.upper() for s in servers]       # uppercase every name
print(server_upper)                               # ['WEB-01', 'WEB-02', 'DB-01']

# =============================================================================
# EXERCISES
# =============================================================================
# 1. Create a list of 5 port numbers (e.g. 80, 443, 8080, 3306, 5432).
#    Print the first, last, and middle item using indexing.
#
# ports = [???, ???, ???, ???, ???]
# print(ports[???])   # first
# print(ports[???])   # last
# print(ports[???])   # middle

# 2. Use a list comprehension to create a list of only the port numbers > 1000.
#
# high_ports = [??? for ??? in ports if ???]
# print(high_ports)

# 3. Given the list below, sort it descending and print only the top 3.
#    Hint: sort descending, then slice [:3]
#
# latencies = [120, 45, 300, 78, 210, 33, 500]
# ???
# print(???)
