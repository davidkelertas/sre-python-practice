#!/usr/bin/env python3
# =============================================================================
# 01_variables.py  —  Variables, Types, and Printing
# Run: python 01_variables.py
# =============================================================================

# --- What is a variable? ---
# A variable is a name that points to a value stored in memory.
# In Python you do NOT declare a type — Python works it out for you.

name = "Alice"          # str   — text, always inside quotes (single or double)
age = 30                # int   — a whole number, no decimal point
height = 1.75           # float — a number with a decimal point
is_admin = True         # bool  — either True or False  (capital first letter!)

# type() returns the type of any value — useful for debugging
print(type(name))       # <class 'str'>
print(type(age))        # <class 'int'>
print(type(height))     # <class 'float'>
print(type(is_admin))   # <class 'bool'>

# --- Printing ---
# print() sends text to the terminal, then moves to the next line.
print("Hello, world!")  # plain string — no variables inserted

# f-strings: put f before the opening quote, then use {} to insert variables.
# Anything inside {} is evaluated as Python code.
print(f"Name: {name}")                      # inserts the value of 'name'
print(f"Age:  {age}")                       # inserts 30
print(f"Height: {height:.1f} m")           # :.1f = format as 1 decimal place
print(f"Admin:  {is_admin}")               # prints True

# You can do calculations inside {}
print(f"Age in 10 years: {age + 10}")      # evaluates age + 10 = 40

# --- Reassigning variables ---
# Variables can be changed at any time — Python is not const by default.
age = 31                # age now holds 31, not 30
print(f"Updated age: {age}")

# --- Multiple assignment ---
# Assign several variables on one line (useful for related values).
x, y, z = 1, 2, 3      # x=1, y=2, z=3
print(f"x={x}  y={y}  z={z}")

# --- None — the "no value" value ---
# None is Python's way of saying "this variable exists but has no value yet."
result = None           # common pattern: declare before you know the value
print(f"result is None: {result is None}")   # 'is' checks identity, not equality

# --- String operations ---
first = "David"
last  = "Smith"
full  = first + " " + last      # + joins two strings together (concatenation)
print(full)                      # David Smith

upper = full.upper()             # .upper() returns a new string in ALL CAPS
lower = full.lower()             # .lower() returns a new string in all lowercase
print(upper)                     # DAVID SMITH
print(lower)                     # david smith

# len() returns the number of characters in a string (or items in a list)
print(f"Length of full name: {len(full)}")   # 10

# .strip() removes leading/trailing whitespace — useful when reading user input
messy = "   hello   "
clean = messy.strip()
print(f"'{messy}' -> '{clean}'")    # '   hello   ' -> 'hello'

# --- Type conversion ---
# int(), float(), str() convert between types
number_as_string = "42"                     # this is a str, not a number
converted = int(number_as_string)           # now it's an int you can do maths with
print(f"Converted: {converted + 1}")        # 43

# str() goes the other way — turn a number into a string
score = 95
message = "Your score is " + str(score)    # can't add str + int directly
print(message)

# =============================================================================
# EXERCISES
# =============================================================================
# 1. Create a variable called 'city' with your city name, and a variable called
#    'population' with a number.  Print:  "City: <city>, Pop: <population>"
#
# city = ???
# population = ???
# print(???)

# 2. Create two float variables, 'price' and 'tax_rate' (e.g. 0.1 for 10%).
#    Calculate the total price and print it formatted to 2 decimal places.
#    Hint: total = price + price * tax_rate
#          print(f"Total: {total:.2f}")
#
# price = ???
# tax_rate = ???
# total = ???
# print(???)

# 3. Ask Python: what is the type of  3 + 1.5 ?
#    Run:  print(type(3 + 1.5))
#    Why is the result a float and not an int?
