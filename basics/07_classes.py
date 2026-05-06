#!/usr/bin/env python3
# =============================================================================
# 07_classes.py  —  Classes, instances, methods, and inheritance
# Run: python 07_classes.py
# =============================================================================

# --- What is a class? ---
# A class is a blueprint for creating objects.
# An object (also called an "instance") bundles DATA (attributes) and
# BEHAVIOUR (methods) together.
#
# Analogy: a class is the blueprint for a house; an instance is an actual house.

# --- Defining a class ---
class Server:                               # class name: CapitalizedWords by convention
    """Represents a single server in the cluster."""   # class docstring

    # __init__ is the constructor — called automatically when you create an instance.
    # 'self' refers to the NEW instance being created.  Always the first parameter.
    def __init__(self, name, env, cpu_pct=0.0):   # parameters become attributes
        self.name    = name         # self.name stores 'name' ON the instance
        self.env     = env          # every instance gets its own copy of these
        self.cpu_pct = cpu_pct      # defaults to 0.0 if not provided
        self.healthy = True         # default attribute — not passed in by caller

    # A method is a function defined inside a class.
    # 'self' is always the first parameter — Python passes the instance automatically.
    def status(self):
        """Return a human-readable status string."""
        state = "UP" if self.healthy else "DOWN"
        return f"[{state}] {self.name} ({self.env})  CPU: {self.cpu_pct:.1f}%"

    def update_cpu(self, new_pct):
        """Update CPU reading and flag as unhealthy if above 90%."""
        self.cpu_pct = new_pct          # update the attribute
        self.healthy = new_pct < 90.0   # sets healthy based on threshold

    # __repr__ is called when you print an object or inspect it in the REPL.
    # Always define this — it makes debugging much easier.
    def __repr__(self):
        return f"Server(name={self.name!r}, env={self.env!r}, cpu={self.cpu_pct})"
        # !r adds quotes around string values: name='web-01'


# --- Creating instances ---
web1 = Server("web-01", "prod", 72.5)   # calls __init__
web2 = Server("web-02", "prod")          # cpu_pct defaults to 0.0
db1  = Server("db-01",  "prod", 88.0)

# Each instance is independent — changing web1 does not affect web2
print(web1.status())    # [UP] web-01 (prod)  CPU: 72.5%
print(web2.status())    # [UP] web-02 (prod)  CPU: 0.0%

# Access attributes directly with dot notation
print(web1.name)        # "web-01"
print(web1.cpu_pct)     # 72.5

# Call methods with dot notation
web1.update_cpu(95.0)   # updates web1 only
print(web1.status())    # [DOWN] web-01 (prod)  CPU: 95.0%
print(web2.status())    # [UP] web-02 (prod)  CPU: 0.0%  ← unchanged

# __repr__ kicks in when you print the object itself
print(web1)             # Server(name='web-01', env='prod', cpu=95.0)


# --- Class with a list attribute ---
# Storing a list on self lets you accumulate data per instance.
class AlertQueue:
    """Accumulates alert messages and lets you drain them."""

    def __init__(self):
        self.alerts = []            # each instance gets its OWN empty list
        self.count  = 0

    def add(self, message):
        self.alerts.append(message)
        self.count += 1

    def drain(self):
        """Return and clear all alerts."""
        result = self.alerts[:]     # slice copy so we can clear the original
        self.alerts.clear()         # .clear() empties the list in place
        return result

    def __len__(self):              # called by len(queue) — makes the class feel native
        return len(self.alerts)

    def __bool__(self):             # called by  if queue: — True when non-empty
        return len(self.alerts) > 0


queue = AlertQueue()
queue.add("web-01: high CPU")
queue.add("db-01: replication lag")
print(f"Queue size: {len(queue)}")      # 2  — calls __len__
if queue:                               # calls __bool__ — True because non-empty
    messages = queue.drain()
    for msg in messages:
        print(f"  ALERT: {msg}")
print(f"After drain: {len(queue)}")     # 0


# --- Inheritance — extending an existing class ---
# A child class inherits ALL methods and attributes from the parent.
# You can override methods or add new ones.

class DatabaseServer(Server):           # DatabaseServer inherits from Server
    """A server that also tracks replication lag."""

    def __init__(self, name, env, cpu_pct=0.0, repl_lag_s=0.0):
        super().__init__(name, env, cpu_pct)    # call parent __init__ to set name/env/cpu
        self.repl_lag_s = repl_lag_s            # new attribute only DatabaseServer has

    def status(self):               # OVERRIDE parent's status method
        parent_status = super().status()        # call parent's status() as a starting point
        return f"{parent_status}  Lag: {self.repl_lag_s:.2f}s"

    def is_lagging(self, threshold=1.0):
        """Return True if replication lag exceeds threshold."""
        return self.repl_lag_s > threshold


db = DatabaseServer("db-primary", "prod", cpu_pct=60.0, repl_lag_s=2.5)
print(db.status())                          # [UP] db-primary (prod)  CPU: 60.0%  Lag: 2.50s
print(db.is_lagging())                      # True  (2.5 > 1.0)
print(isinstance(db, DatabaseServer))       # True
print(isinstance(db, Server))              # True — db IS also a Server (inheritance)

# =============================================================================
# EXERCISES
# =============================================================================
# 1. Add a method 'restart()' to Server that sets healthy=True and cpu_pct=0.0
#    (simulating a fresh restart).  Test it on web1 which is currently DOWN.
#
# Inside the Server class add:
#     def restart(self):
#         ???
#
# web1.restart()
# print(web1.status())   # should show [UP] with CPU: 0.0%

# 2. Create a class 'Cluster' that holds a list of Server instances.
#    Add methods:
#      add_server(server) — append to internal list
#      unhealthy_servers() — return a list of servers where healthy == False
#      average_cpu() — return the average cpu_pct across all servers
#
# class Cluster:
#     def __init__(self):
#         self.servers = []
#     def add_server(self, server):
#         ???
#     def unhealthy_servers(self):
#         return [??? for s in self.servers if ???]
#     def average_cpu(self):
#         ???

# 3. Create a DatabaseServer with repl_lag_s=0.5 and confirm is_lagging()
#    returns False (below the 1.0s default threshold).
