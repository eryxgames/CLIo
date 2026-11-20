# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Simulators: vehicles in fixed steps, instruments and systems as data.

A sim (``sims.json``) is either a vehicle on a map of characters - driven, sailed or flown in real
time, with gauges, fuel, checkpoints and a landing pad - or a model of systems alone (``"mode":
"systems"``): stocks that change by formulas each tick, controls the player moves, charts. ::

    "map": ["##########", "#@..1..=2#", "#~~..TT.H#", "##########"],
    "vehicle": {"model": "hover", "fuel": 100},
    "systems": {"heat": {"rate": "thrust * 8 - (heat - 20) * 0.2", "min": 20, "damage_over": 90}}

Map: ``.`` ground, ``,`` grass, ``=`` road, ``:`` mud, ``~`` water, ``#`` rock (3 high), ``T`` trees (1),
``B`` buildings (2), ``H`` a pad to land on, ``F`` fuel, ``@`` the start, ``1``-``9`` checkpoints.

Models: ``car`` (and ``boat``, on water): throttle, brakes, steering, grip that holds the line or lets
it drift; ``hover``: thrust along its heading, lift, yaw, gravity when the fuel is gone, landing soft or
hard; ``plane``: throttle, climb and dive, turns that need speed, stalling, runways.

It runs at 20 ticks a second. Floats, but only + - * / and square roots (the same on every machine)
and the sines and cosines of a table made with whole numbers: the same keys at the same ticks fly
the same flight.

    python -m engine.sim GAME [SIM]     # the autopilot flies (drives, runs) each one: done or not
"""

from __future__ import annotations

import ast
import hashlib
import math

from .realtime import Controls

RATE = 20
TURN = 1024                                          # a heading's units in a turn


# --------------------------------------------------------------------------- #
# Sines from whole numbers (no C library in the answer)
# --------------------------------------------------------------------------- #
def _sine_table():
    S = 1 << 48
    pi = 3141592653589793238462643383279502884197 * S // 10 ** 39
    out = []
    for i in range(TURN // 4 + 1):
        x = i * pi // (TURN // 2)
        term, total, k = x, x, 1
        while term:
            term = -term * x // S * x // S // ((2 * k) * (2 * k + 1))
            total += term
            k += 1
        out.append(total / S)
    return out


QUARTER = _sine_table()


def sin_u(u):
    """The sine of a heading in 1024ths of a turn (0 north, clockwise), from the table."""
    u = u % TURN
    i = int(u)
    f = u - i

    def at(n):
        n %= TURN
        q, r = divmod(n, TURN // 4)
        v = QUARTER[r] if q in (0, 2) else QUARTER[TURN // 4 - r]
        return v if q < 2 else -v
    a, b = at(i), at(i + 1)
    return a + (b - a) * f


def cos_u(u):
    return sin_u(u + TURN // 4)


def degrees(u):
    return (u % TURN) * 360.0 / TURN


def units(deg):
    return deg * TURN / 360.0


def bearing(dx, dy):
    """The heading (1024ths) from a vector, by halving (whole-number safe; no atan)."""
    if dx == 0 and dy == 0:
        return 0.0
    lo, hi = 0.0, float(TURN)
    best, bd = 0.0, None
    for k in range(32):                               # coarse, then refine
        u = k * TURN / 32.0
        d = -(dx * sin_u(u) - dy * cos_u(u))         # how much the vector lies ahead
        if bd is None or d < bd:
            best, bd = u, d
    lo, hi = best - TURN / 32.0, best + TURN / 32.0
    for _ in range(24):
        a, b = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if -(dx * sin_u(a) - dy * cos_u(a)) <= -(dx * sin_u(b) - dy * cos_u(b)):
            hi = b
        else:
            lo = a
    return ((lo + hi) / 2) % TURN


def turn_to(a, b):
    """The shortest turn from heading ``a`` to ``b``: -512..512."""
    d = (b - a) % TURN
    return d - TURN if d > TURN / 2 else d


# --------------------------------------------------------------------------- #
# Formulas
# --------------------------------------------------------------------------- #
FUNCS = {"min": min, "max": max, "abs": abs, "clamp": lambda v, lo, hi: max(lo, min(hi, v)),
         "floor": lambda v: float(math.floor(v)), "sqrt": lambda v: math.sqrt(max(0.0, v))}
BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
       ast.Div: lambda a, b: a / b if b else 0.0, ast.Mod: lambda a, b: a % b if b else 0.0,
       ast.FloorDiv: lambda a, b: a // b if b else 0.0, ast.Pow: lambda a, b: a ** b if abs(b) <= 4 else 0.0}
CMP = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b,
       ast.GtE: lambda a, b: a >= b, ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}


class FormulaError(ValueError):
    pass


def formula(text):
    """A formula (``"thrust * 8 - (heat - 20) * 0.2"``) as a function of a dict of names. Numbers, names,
    + - * / % //, ** (small powers), comparisons, and, or, not, ``a if c else b``, min, max, abs, clamp,
    floor, sqrt - nothing else. Raises FormulaError."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        v = float(text)
        return lambda env: v
    try:
        tree = ast.parse(str(text), mode="eval").body
    except SyntaxError as e:
        raise FormulaError("cannot read %r: %s" % (text, e.msg))
    names = set()

    def build(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            v = float(n.value)
            return lambda env: v
        if isinstance(n, ast.Constant) and isinstance(n.value, bool):
            v = 1.0 if n.value else 0.0
            return lambda env: v
        if isinstance(n, ast.Name):
            k = n.id
            names.add(k)
            return lambda env: float(env.get(k, 0.0))
        if isinstance(n, ast.BinOp) and type(n.op) in BIN:
            f, a, b = BIN[type(n.op)], build(n.left), build(n.right)
            return lambda env: f(a(env), b(env))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd, ast.Not)):
            a = build(n.operand)
            if isinstance(n.op, ast.USub):
                return lambda env: -a(env)
            if isinstance(n.op, ast.Not):
                return lambda env: 0.0 if a(env) else 1.0
            return a
        if isinstance(n, ast.Compare) and all(type(o) in CMP for o in n.ops):
            parts = [build(n.left)] + [build(c) for c in n.comparators]
            ops = [CMP[type(o)] for o in n.ops]

            def cmp(env):
                vals = [p(env) for p in parts]
                return 1.0 if all(op(vals[i], vals[i + 1]) for i, op in enumerate(ops)) else 0.0
            return cmp
        if isinstance(n, ast.BoolOp):
            parts = [build(v) for v in n.values]
            if isinstance(n.op, ast.And):
                return lambda env: 1.0 if all(p(env) for p in parts) else 0.0
            return lambda env: 1.0 if any(p(env) for p in parts) else 0.0
        if isinstance(n, ast.IfExp):
            c, a, b = build(n.test), build(n.body), build(n.orelse)
            return lambda env: a(env) if c(env) else b(env)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords:
            f, args = FUNCS[n.func.id], [build(a) for a in n.args]
            return lambda env: float(f(*[a(env) for a in args]))
        raise FormulaError("not allowed in a formula: %s" % ast.dump(n)[:40])
    fn = build(tree)
    fn.names = names
    return fn


# --------------------------------------------------------------------------- #
# The map, vehicles, systems
# --------------------------------------------------------------------------- #
TERRAIN = {".": "ground", " ": "ground", ",": "grass", "=": "road", ":": "mud", "~": "water", "#": "rock",
           "T": "trees", "B": "building", "H": "pad", "F": "fuel"}
GROUND = {"ground": {}, "grass": {"drag": 0.4, "speed": 0.8}, "road": {"speed": 1.25, "grip": 1.3},
          "mud": {"drag": 1.5, "speed": 0.45, "grip": 0.5}, "water": {"water": True},
          "rock": {"height": 3, "solid": True}, "trees": {"height": 1, "solid": True},
          "building": {"height": 2, "solid": True}, "pad": {"pad": True, "speed": 1.1},
          "fuel": {"fuel": True}}
MODELS = {
    "car": {"accel": 4.0, "brake": 8.0, "max_speed": 9.0, "reverse": 3.0, "drag": 0.35, "turn": 160.0,
            "turn_speed": 3.0, "grip": 7.0, "fuel": 60.0, "burn": 0.5, "idle": 0.02, "toughness": 1.0},
    "boat": {"accel": 2.5, "brake": 2.0, "max_speed": 7.0, "reverse": 1.5, "drag": 0.25, "turn": 90.0,
             "turn_speed": 2.0, "grip": 1.5, "fuel": 60.0, "burn": 0.4, "idle": 0.02, "toughness": 1.0,
             "on": "water"},
    "hover": {"thrust": 5.0, "max_speed": 7.0, "drag": 0.6, "turn": 140.0, "climb": 4.0, "max_climb": 3.0,
              "descend": 1.4,
              "gravity": 6.0, "ceiling": 12.0, "fuel": 100.0, "burn": 0.8, "idle": 0.25, "safe_climb": 1.6,
              "safe_speed": 2.0, "toughness": 1.0},
    "plane": {"accel": 3.0, "max_speed": 14.0, "drag": 0.12, "turn": 70.0, "climb": 3.0, "stall": 5.0,
              "gravity": 4.0, "ceiling": 20.0, "fuel": 120.0, "burn": 0.6, "idle": 0.1, "safe_climb": 1.5,
              "land_speed": 7.5, "toughness": 1.0},
}
GAUGES = {
    "car": [{"show": "speed", "label": "SPEED", "max": "max_speed"}, {"show": "heading", "style": "compass"},
            {"show": "fuel", "label": "FUEL", "max": "fuel_max"}, {"show": "damage", "label": "DAMAGE",
                                                                   "max": 100, "warn": 0.6},
            {"show": "next", "label": "NEXT", "style": "number", "unit": "tiles"}],
    "hover": [{"show": "speed", "label": "SPEED", "max": "max_speed"},
              {"show": "height", "label": "ALT", "max": "ceiling"},
              {"show": "climb", "label": "CLIMB", "style": "center", "max": "max_climb"},
              {"show": "heading", "style": "compass"},
              {"show": "fuel", "label": "FUEL", "max": "fuel_max", "warn": -0.2},
              {"show": "damage", "label": "DAMAGE", "max": 100, "warn": 0.6},
              {"show": "next", "label": "NEXT", "style": "number", "unit": "tiles"}],
    "plane": [{"show": "speed", "label": "SPEED", "max": "max_speed", "warn": -0.36},
              {"show": "throttle", "label": "THROTTLE", "max": 100},
              {"show": "height", "label": "ALT", "max": "ceiling"},
              {"show": "climb", "label": "CLIMB", "style": "center", "max": 4},
              {"show": "heading", "style": "compass"}, {"show": "fuel", "label": "FUEL", "max": "fuel_max"},
              {"show": "damage", "label": "DAMAGE", "max": 100, "warn": 0.6}],
}
COLORS = {"ground": "#3a4a2a", "grass": "#2f5a26", "road": "#555560", "mud": "#4a3a24", "water": "#1c3c64",
          "rock": "#6a6a72", "trees": "#22502a", "building": "#7a5a4a", "pad": "#806020", "fuel": "#806020",
          "vehicle": "#ffffff", "checkpoint": "#60e0ff", "next": "#ffe060", "done": "#406070", "trail": "#a0a0a0"}
ARROWS = "↑↗→↘↓↙←↖"
ASCII_ARROWS = "^/>\\v/<\\"


def map_rows(spec):
    m = spec.get("map")
    if isinstance(m, str):
        m = m.split("\n")
    return [r for r in m if isinstance(r, str)] if isinstance(m, list) else []


def settings_of(data):
    cfg = (getattr(data, "config", None) or {}).get("sim") or {}
    return cfg if isinstance(cfg, dict) else {}


class System:
    """A stock: a value, a formula for how fast it changes (a second), and its limits."""

    def __init__(self, name, spec):
        self.name = name
        spec = spec if isinstance(spec, dict) else {"rate": spec}
        self.spec = spec
        self.value = float(spec.get("start", 0))
        self.rate = formula(spec.get("rate", 0))
        self.lo = spec.get("min")
        self.hi = spec.get("max")
        self.is_value = "value" in spec                # computed each tick, not a stock
        self.calc = formula(spec["value"]) if self.is_value else None


class Sim:
    """One sim being played: :meth:`step` with :class:`engine.realtime.Controls` a tick at a time."""

    def __init__(self, spec, sid="sim", data=None, rate=RATE):
        self.id, self.spec, self.rate = sid, spec, rate
        self.dt = 1.0 / rate
        self.name = spec.get("title") or spec.get("name") or sid
        cfg = settings_of(data)
        self.mode = "systems" if spec.get("mode") == "systems" else "vehicle"
        veh = dict(spec.get("vehicle") or {})
        self.model = veh.get("model") if veh.get("model") in MODELS else "car"
        self.p = dict(MODELS[self.model], **(cfg.get("models") or {}).get(self.model, {}))
        self.p.update({k: v for k, v in veh.items() if k != "model"})
        self.colors = dict(COLORS, **(cfg.get("colors") or {}), **(spec.get("colors") or {}))
        rows = map_rows(spec)
        self.W = max([len(r) for r in rows] or [1])
        self.H = max(1, len(rows))
        legend = spec.get("legend") or {}
        self.grid = []
        self.checks = {}
        start = (1.5, 1.5)
        for y in range(self.H):
            row = rows[y] if y < len(rows) else ""
            line = []
            for x in range(self.W):
                ch = row[x] if x < len(row) else "."
                kind = TERRAIN.get(ch) or (legend.get(ch) if legend.get(ch) in GROUND else None)
                if ch == "@":
                    start, kind = (x + 0.5, y + 0.5), "ground"
                elif ch.isdigit() and ch != "0":
                    self.checks[int(ch)] = (x + 0.5, y + 0.5)
                    kind = "ground"
                line.append(kind or "ground")
            self.grid.append(line)
        marks = [(int(start[0]), int(start[1]))] + [(int(x), int(y)) for x, y in self.checks.values()]
        for mx, my in marks:                         # the start and the checkpoints: the ground round them
            near = [self.grid[my + dy][mx + dx] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                    if 0 <= mx + dx < self.W and 0 <= my + dy < self.H and (mx + dx, my + dy) not in marks
                    and not GROUND.get(self.grid[my + dy][mx + dx], {}).get("solid")]
            if near:
                self.grid[my][mx] = max(sorted(set(near)), key=near.count)
        self.order = sorted(self.checks)
        self.x, self.y = start
        self.z = float(veh.get("altitude", self.ground(*start)))
        self.vx = self.vy = self.vz = 0.0
        self.heading = units(float(veh.get("heading", 0)))
        self.throttle = 0.0
        self.thrust = 0.0
        self.fuel_max = float(self.p["fuel"])
        self.fuel = float(veh.get("fuel_start", self.fuel_max))
        self.damage = 0.0
        self.landed = self.model in ("car", "boat") or self.z <= self.ground(*start) + 1e-6
        self.passed = 0                              # checkpoints passed (in order)
        self.tick = self.ticks = 0
        self.result = self.over = self.why = None
        self.ending = 0
        self.paused = "ready"
        self.events = []
        self.note = ("", "text", 0)
        self.goal = spec.get("goal") or ("checkpoints" if self.checks else ("survive" if spec.get("time")
                                                                            else "land"))
        self.land = bool(spec.get("land")) or self.goal == "land"
        self.time_ticks = int(round(float(spec["time"]) * rate)) if spec.get("time") else 0
        self.systems = [System(k, v) for k, v in (spec.get("systems") or {}).items()]
        self.controls = {}
        for k, c in (spec.get("controls") or {}).items():
            c = dict(c)
            c["value"] = float(c.get("start", c.get("min", 0)))
            self.controls[k] = c
        self.win_if = formula(spec["win_if"]) if spec.get("win_if") else None
        self.fail_if = formula(spec["fail_if"]) if spec.get("fail_if") else None
        self.score = formula(spec["score"]) if spec.get("score") else None
        self.history = {k: [] for k in (spec.get("chart") or [])}
        self.gauges = spec.get("gauges") or (GAUGES.get(self.model, []) if self.mode == "vehicle" else
                                             [{"show": k, "label": k.upper()} for k in self.history])

    # ---- the map --------------------------------------------------------- #
    def kind(self, x, y):
        tx, ty = int(math.floor(x)), int(math.floor(y))
        if 0 <= tx < self.W and 0 <= ty < self.H:
            return self.grid[ty][tx]
        return "rock"

    def ground(self, x, y):
        """How high what stands there is (rock 3, buildings 2, trees 1; else 0)."""
        return float(GROUND.get(self.kind(x, y), {}).get("height", 0))

    def blocks(self, x, y, z=0.0):
        g = GROUND.get(self.kind(x, y), {})
        if self.model in ("car", "boat"):
            on_water = self.p.get("on") == "water"
            return bool(g.get("solid")) or (bool(g.get("water")) != on_water)
        return bool(g.get("solid")) and z < g.get("height", 0)

    # ---- the numbers the gauges, formulas and goals read --------------------- #
    def env(self):
        fx, fy = sin_u(self.heading), -cos_u(self.heading)
        e = {k: v for k, v in self.p.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        e.update({"speed": self.speed(), "forward": self.vx * fx + self.vy * fy, "altitude": self.z,
             "height": self.z - self.ground(self.x, self.y), "climb": self.vz, "heading": degrees(self.heading),
             "throttle": self.throttle * 100, "thrust": self.thrust, "fuel": self.fuel, "fuel_max": self.fuel_max,
             "damage": self.damage, "time": self.ticks / float(self.rate), "landed": 1.0 if self.landed else 0.0,
             "passed": float(self.passed), "x": self.x, "y": self.y, "next": self.next_distance()})
        for c, spec in self.controls.items():
            e[c] = spec["value"]
        for s in self.systems:
            e[s.name] = s.value
        return e

    def speed(self):
        return math.sqrt(self.vx * self.vx + self.vy * self.vy)

    def next_point(self):
        if self.passed < len(self.order):
            return self.checks[self.order[self.passed]]
        if self.land:
            pads = [(x + 0.5, y + 0.5) for y in range(self.H) for x in range(self.W) if self.grid[y][x] == "pad"]
            if pads:
                return min(pads, key=lambda p: ((p[0] - self.x) ** 2 + (p[1] - self.y) ** 2, p))
        return None

    def next_distance(self):
        p = self.next_point()
        return math.sqrt((p[0] - self.x) ** 2 + (p[1] - self.y) ** 2) if p else 0.0

    def tell(self, text, role="text", seconds=2.5):
        self.note = (text, role, self.tick + int(seconds * self.rate))

    # ---- a tick ------------------------------------------------------------ #
    def step(self, c):
        self.events = []
        self.tick += 1
        if self.over:
            return
        if c.hit("ctrl-d", "ctrl-c"):
            self.result = self.over = self.result or "quit"
            return
        if self.result:
            self.ending -= 1
            if self.ending <= 0:
                self.over = self.result
            return
        if self.paused:
            if c.hit("q"):
                self.result = self.over = "quit"
            elif c.pressed and (self.paused == "ready" or c.hit("p", "esc", "enter", "space")):
                self.paused = None
            return
        if c.hit("p", "esc"):
            self.paused = "paused"
            return
        self.ticks += 1
        if self.mode == "vehicle":
            self._drive(c)
        self._controls(c)
        self._systems()
        if self.mode == "vehicle":
            self._checkpoints()
        self._goals()

    def _axis(self, c, minus, plus):
        return (1.0 if c.down(*plus) else 0.0) - (1.0 if c.down(*minus) else 0.0)

    def _drive(self, c):
        p, dt = self.p, self.dt
        ahead = self._axis(c, ("down", "s"), ("up", "w")) if self.model in ("car", "boat") else \
            self._axis(c, ("down",), ("up",))
        steer = self._axis(c, ("left", "a"), ("right", "d"))
        lift = self._axis(c, ("s", "pgdn"), ("w", "pgup"))
        empty = self.fuel <= 0
        if empty:
            ahead, lift = 0.0, 0.0
        getattr(self, "_" + ("car" if self.model == "boat" else self.model))(ahead, steer, lift, c.down("space"))
        burn = p["idle"] + p["burn"] * self.thrust
        if not empty:
            self.fuel = max(0.0, self.fuel - burn * dt)
            if self.fuel <= 0:
                self.events.append("empty")
                self.tell("Out of fuel.", "hurt")
        g = GROUND.get(self.kind(self.x, self.y), {})
        if g.get("fuel") and self.landed and self.speed() < 0.5 and self.fuel < self.fuel_max:
            if self.fuel < self.fuel_max - 0.01 and self.ticks % self.rate == 0:
                self.events.append("refuel")
            self.fuel = min(self.fuel_max, self.fuel + self.fuel_max * 0.1 * dt)

    def _move(self, impact_scale=6.0):
        """Move by the velocity; what blocks stops it (that axis) and the harder the hit, the more it hurts."""
        dt = self.dt
        nx, ny = self.x + self.vx * dt, self.y + self.vy * dt
        hit = 0.0
        if self.blocks(nx, self.y, self.z):
            hit = max(hit, abs(self.vx))
            self.vx = -self.vx * 0.2
            nx = self.x
        if self.blocks(nx, ny, self.z):
            hit = max(hit, abs(self.vy))
            self.vy = -self.vy * 0.2
            ny = self.y
        self.x, self.y = nx, ny
        if hit > 1.0:
            self._hurt((hit - 1.0) * impact_scale / float(self.p.get("toughness", 1.0)), "bump")

    def _hurt(self, n, sound="hurt"):
        self.damage = min(100.0, self.damage + n)
        self.events.append(sound)
        if self.damage >= 100:
            self._end("lost", "crashed")

    def _car(self, ahead, steer, lift, brake):
        p, dt = self.p, self.dt
        g = GROUND.get(self.kind(self.x, self.y), {})
        fx, fy = sin_u(self.heading), -cos_u(self.heading)
        along = self.vx * fx + self.vy * fy
        factor = min(1.0, abs(along) / p["turn_speed"]) * (1 if along >= 0 else -1)
        self.heading = (self.heading + units(p["turn"]) * steer * factor * dt) % TURN
        fx, fy = sin_u(self.heading), -cos_u(self.heading)       # the old way it went, seen from the new heading:
        sx, sy = cos_u(self.heading), sin_u(self.heading)        # what grip does not hold slides
        along = self.vx * fx + self.vy * fy
        side = self.vx * sx + self.vy * sy
        top = p["max_speed"] * g.get("speed", 1.0)
        self.thrust = max(0.0, ahead)
        self.throttle = self.thrust
        if ahead > 0:
            along += p["accel"] * dt
        elif ahead < 0:
            along -= (p["brake"] if along > 0.1 else p["accel"] * 0.6) * dt
        if brake:
            along -= max(-p["brake"] * dt, min(p["brake"] * dt, along))
        along -= along * (p["drag"] + g.get("drag", 0.0)) * dt
        along = max(-p["reverse"], min(top, along))
        side -= side * min(1.0, p["grip"] * g.get("grip", 1.0) * dt)
        self.vx, self.vy = fx * along + sx * side, fy * along + sy * side
        self._move()

    def _hover(self, ahead, steer, lift, brake):
        p, dt = self.p, self.dt
        empty = self.fuel <= 0
        fx, fy = sin_u(self.heading), -cos_u(self.heading)
        ground = self.ground(self.x, self.y)
        self.thrust = min(1.0, abs(ahead) + abs(lift) * 0.6)
        self.throttle = self.thrust
        if not self.landed or lift > 0:
            self.vx += fx * p["thrust"] * ahead * dt
            self.vy += fy * p["thrust"] * ahead * dt
            self.heading = (self.heading + units(p["turn"]) * steer * dt) % TURN
        self.vx -= self.vx * p["drag"] * dt
        self.vy -= self.vy * p["drag"] * dt
        sp = self.speed()
        if sp > p["max_speed"]:
            self.vx, self.vy = self.vx * p["max_speed"] / sp, self.vy * p["max_speed"] / sp
        if empty:
            self.vz -= p["gravity"] * dt                       # it falls
        else:                                                 # W climbs, S sinks gently, neither holds
            target = p["max_climb"] if lift > 0 else (-p["descend"] if lift < 0 else 0.0)
            self.vz += (target - self.vz) * min(1.0, p["climb"] * dt)
        self.vz = max(-p["max_climb"] * 3, min(p["max_climb"], self.vz))
        if self.landed:
            self.vx = self.vy = 0.0
            if self.vz <= 0:
                self.vz = 0.0
                return
            self.landed = False
            self.events.append("lift_off")
        self.z = min(p["ceiling"], self.z + self.vz * dt)
        self._move()
        ground = self.ground(self.x, self.y)
        if self.z <= ground:
            self._touch_down(ground)

    def _touch_down(self, ground):
        p = self.p
        hard = -self.vz - p["safe_climb"]
        fast = self.speed() - p.get("safe_speed", p.get("land_speed", 2.0))
        self.z = ground
        if hard > 0 or fast > 0:
            self._hurt(max(0.0, hard) * 30 + max(0.0, fast) * 12, "crash")
        if self.result:
            return
        self.landed = True
        self.vx = self.vy = self.vz = 0.0
        self.events.append("land")
        what = GROUND.get(self.kind(self.x, self.y), {})
        if what.get("water"):
            self._end("lost", "sank")

    def _plane(self, ahead, steer, lift, brake):
        p, dt = self.p, self.dt
        empty = self.fuel <= 0
        self.throttle = max(0.0, min(1.0, self.throttle + ahead * 0.6 * dt)) if not empty else 0.0
        self.thrust = self.throttle
        fx, fy = sin_u(self.heading), -cos_u(self.heading)
        along = self.vx * fx + self.vy * fy
        along += (self.throttle * p["accel"] - along * p["drag"]) * dt
        if self.landed and brake:
            along -= min(along, 6.0 * dt)
        along = max(0.0, min(p["max_speed"], along))
        flying = along >= p["stall"]
        if self.landed:
            self.heading = (self.heading + units(p["turn"]) * 0.4 * steer * min(1.0, along / 2) * dt) % TURN
            if flying and lift > 0:
                self.landed = False
                self.vz = p["climb"] * 0.5
                self.events.append("lift_off")
        else:
            self.heading = (self.heading + units(p["turn"]) * steer * min(1.0, along / p["stall"]) * dt) % TURN
            if flying:
                target = p["climb"] * lift * min(1.0, along / p["max_speed"] * 1.5)
                self.vz += (target - self.vz) * min(1.0, 2.0 * dt)
            else:
                self.vz -= p["gravity"] * dt                     # a stall: it drops
                if self.ticks % self.rate == 0:
                    self.tell("Stall!", "hurt", 1.0)
        fx, fy = sin_u(self.heading), -cos_u(self.heading)
        self.vx, self.vy = fx * along, fy * along
        if not self.landed:
            self.z = min(p["ceiling"], self.z + self.vz * dt)
        self._move(impact_scale=10.0)
        ground = self.ground(self.x, self.y)
        if not self.landed and self.z <= ground:
            on = self.kind(self.x, self.y)
            hard = -self.vz - p["safe_climb"]
            fast = along - p["land_speed"]
            self.z = ground
            if hard > 0 or fast > 0 or on not in ("road", "pad", "ground", "grass"):
                self._hurt(max(0.0, hard) * 30 + max(0.0, fast) * 10 + (40 if on not in ("road", "pad") else 0),
                           "crash")
            if not self.result:
                self.landed, self.vz = True, 0.0
                self.events.append("land")
        elif self.landed and self.blocks(self.x, self.y, self.z):
            self._hurt(100, "crash")

    def _controls(self, c):
        for k, spec in self.controls.items():
            keys = spec.get("keys") or []
            step = float(spec.get("step", 10)) * self.dt
            if len(keys) >= 1 and c.down(keys[0]):
                spec["value"] += step
            if len(keys) >= 2 and c.down(keys[1]):
                spec["value"] -= step
            spec["value"] = max(float(spec.get("min", 0)), min(float(spec.get("max", 100)), spec["value"]))

    def _systems(self):
        if not self.systems:
            return
        env = self.env()
        for s in self.systems:
            if s.is_value:
                s.value = s.calc(env)
            else:
                s.value += s.rate(env) * self.dt
            if s.lo is not None:
                s.value = max(float(s.lo), s.value)
            if s.hi is not None:
                s.value = min(float(s.hi), s.value)
            env[s.name] = s.value
            over = s.spec.get("damage_over")
            if over is not None and s.value > float(over) and self.mode == "vehicle":
                self._hurt((s.value - float(over)) * float(s.spec.get("damage_rate", 0.5)) * self.dt, "hurt")
                if self.ticks % self.rate == 0:
                    self.tell("%s too high!" % s.spec.get("label", s.name).capitalize(), "hurt", 1.0)
        if self.ticks % max(1, self.rate // 2) == 0:
            for k in self.history:
                self.history[k].append(env.get(k, 0.0))
                del self.history[k][:-120]

    def _checkpoints(self):
        if self.passed >= len(self.order):
            return
        cx, cy = self.checks[self.order[self.passed]]
        if (cx - self.x) ** 2 + (cy - self.y) ** 2 <= 0.8 ** 2:
            self.passed += 1
            self.events.append("checkpoint")
            left = len(self.order) - self.passed
            self.tell("Checkpoint %d. %s" % (self.passed, ("%d to go." % left) if left else
                                             ("Now land on the pad." if self.land else "")), "good")

    def _goals(self):
        if self.result:
            return
        env = None
        if self.fail_if is not None:
            env = self.env()
            if self.fail_if(env):
                return self._end("lost", "failed")
        if self.mode == "vehicle" and self.fuel <= 0 and self.landed and self.speed() < 0.05 and \
                not (self.goal == "land" and GROUND.get(self.kind(self.x, self.y), {}).get("pad")):
            if not self._won():
                return self._end("lost", "fuel")
        if self._won():
            return self._end("won", "done")
        if self.time_ticks and self.ticks >= self.time_ticks:
            if self.goal == "survive":
                return self._end("won", "time")
            self._end("lost", "time")

    def _won(self):
        if self.win_if is not None and self.win_if(self.env()):
            return True
        if self.goal in ("checkpoints", "land") and self.mode == "vehicle":
            if self.passed < len(self.order):
                return False
            if not self.land:
                return self.goal == "checkpoints"
            return self.landed and bool(GROUND.get(self.kind(self.x, self.y), {}).get("pad"))
        return False

    def _end(self, result, why):
        if self.result:
            return
        self.result, self.why = result, why
        self.ending = self.rate * 2
        self.events.append("done" if result == "won" else "fail")

    # ---- what is kept ------------------------------------------------------ #
    def state(self):
        return (self.tick, self.ticks, round(self.x, 9), round(self.y, 9), round(self.z, 9), round(self.vx, 9),
                round(self.vy, 9), round(self.vz, 9), round(self.heading, 9), round(self.fuel, 9),
                round(self.damage, 9), self.passed, self.landed, self.result,
                [round(s.value, 9) for s in self.systems], [round(c["value"], 9) for c in self.controls.values()])

    def state_hash(self):
        return hashlib.sha1(repr(self.state()).encode()).hexdigest()[:16]

    def clone(self):
        import copy
        return copy.deepcopy(self)

    def stats(self):
        return {"result": self.result, "why": self.why, "seconds": round(self.ticks / float(self.rate), 1),
                "damage": round(self.damage), "fuel": round(self.fuel), "passed": self.passed}


def make(data, sid, rate=RATE):
    spec = (getattr(data, "sims", None) or {}).get(sid)
    if not isinstance(spec, dict):
        raise KeyError("no sim '%s'" % sid)
    return Sim(spec, sid, data, rate)


# --------------------------------------------------------------------------- #
# Autopilot: proof that a sim can be done
# --------------------------------------------------------------------------- #
def autopilot_keys(sim):
    """The keys a careful pilot holds now: steer for the next point, keep clear of what is high, slow
    down to land on the pad."""
    keys = set()
    if sim.mode == "systems":
        return keys
    p = sim.p
    target = sim.next_point()
    if target is None:
        if sim.model == "hover" and not sim.landed:
            keys.add("s")
        return keys
    dx, dy = target[0] - sim.x, target[1] - sim.y
    dist = math.sqrt(dx * dx + dy * dy)
    want = bearing(dx, dy)
    off = turn_to(sim.heading, want)
    if off > 6:
        keys.add("right")
    elif off < -6:
        keys.add("left")
    if sim.model in ("car", "boat"):
        if abs(off) < 160 or sim.speed() < 1.0:
            if not (dist < 3 and sim.speed() > 4):
                keys.add("up")
        elif sim.speed() > 3:
            keys.add("down")
        return keys
    if sim.model == "hover":
        final = sim.passed >= len(sim.order) and sim.land
        clear = 0.0
        ux, uy = dx / max(dist, 1e-9), dy / max(dist, 1e-9)
        for k in range(0, 7):                             # the highest thing near, and ahead on the way
            step = min(k * 0.8, dist)
            clear = max(clear, sim.ground(sim.x + ux * step, sim.y + uy * step))
        cruise = clear + 1.5
        if final and dist < 0.6 and sim.speed() < 0.8:
            return {"s"}                                   # straight down: S sinks gently
        if sim.z < cruise - 0.2:
            keys.add("w")
        elif sim.z > cruise + 0.8 and not sim.landed:
            keys.add("s")
        if sim.z >= clear + 0.6 and abs(off) < 90:
            stop = sim.speed() ** 2 / (2 * p["thrust"]) + 0.3
            if dist > stop + (0.0 if not final else 0.2):
                keys.add("up")
            elif sim.speed() > 0.3:
                keys.add("down")
        return keys
    if sim.model == "plane":
        if sim.throttle < 0.85:
            keys.add("up")
        if sim.landed or sim.z < sim.ground(sim.x, sim.y) + 3.5:
            keys.add("w")
        return keys
    return keys


def fly(sim, seconds=600, systems_every=2.0):
    """Let the autopilot do the sim; the journal of key events it made, as the real-time Recorder keeps
    them. Systems sims are run by trying the controls ahead (as far as ``seconds`` allows)."""
    from .keys import PRESS, RELEASE, REPEAT
    journal = [[0, [["enter", PRESS]]]]
    held = set()
    sim.step(Controls(0, frozenset(["enter"]), ("enter",), ()))
    tick = 1
    plan_keys = set()
    while not sim.result and sim.ticks < seconds * sim.rate:
        if sim.mode == "systems":
            if tick == 1 or (sim.ticks % int(systems_every * sim.rate) == 0):
                plan_keys = best_controls(sim, systems_every)
            keys = set(plan_keys)
        else:
            keys = autopilot_keys(sim)
        evs = [[k, RELEASE] for k in sorted(held - keys)] + [[k, PRESS] for k in sorted(keys - held)]
        if tick % 10 == 0:                                # held keys repeat, as a terminal sends them
            evs += [[k, REPEAT] for k in sorted(keys & held)]
        if tick == 1:
            evs = [["enter", RELEASE]] + evs
        if evs:
            journal.append([tick, evs])
        sim.step(Controls(tick, frozenset(keys), tuple(sorted(keys - held)), tuple(sorted(held - keys))))
        held = keys
        tick += 1
    return journal


def best_controls(sim, horizon):
    """For a systems sim: which keys to hold the next ``horizon`` seconds - each control up, down or left,
    tried a little further ahead on a copy, the best by the sim's ``score`` (and not failing)."""
    import itertools
    names = list(sim.controls)
    choices = []
    for k in names:
        keys = sim.controls[k].get("keys") or []
        choices.append([()] + [(key,) for key in keys[:2]])
    best, bs = set(), None
    for combo in itertools.product(*choices):
        keys = frozenset(k for c in combo for k in c)
        trial = sim.clone()
        for _ in range(int(horizon * 3 * sim.rate)):
            trial.step(Controls(trial.tick, keys, (), ()))
            if trial.result:
                break
        env = trial.env()
        s = (trial.score(env) if trial.score else 0.0)
        if trial.result == "lost":
            s -= 1e9
        elif trial.result == "won":
            s += 1e9
        if bs is None or s > bs:
            best, bs = set(keys), s
    return best


# --------------------------------------------------------------------------- #
# The picture
# --------------------------------------------------------------------------- #
def colour(c, default=(128, 128, 128)):
    if isinstance(c, (list, tuple)) and len(c) == 3:
        return tuple(int(v) for v in c)
    if isinstance(c, str) and len(c) == 7 and c[0] == "#":
        try:
            return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            pass
    return default


GLYPHS = {"ground": (" ", "."), "grass": ("·", ","), "road": (" ", "="), "mud": ("░", ":"), "water": ("≈", "~"),
          "rock": ("▲", "#"), "trees": ("♣", "T"), "building": ("▓", "B"), "pad": ("H", "H"), "fuel": ("F", "F")}


def map_cells(sim, cols, rows, color=True, unicode=True):
    """The map round the vehicle (north up): rows of ``(char, fg, bg)``."""
    C = {k: colour(v) for k, v in sim.colors.items()}
    cx = int(math.floor(sim.x)) - cols // 2
    cy = int(math.floor(sim.y)) - rows // 2
    out = []
    for r in range(rows):
        line = []
        for c in range(cols):
            x, y = cx + c, cy + r
            if not (0 <= x < sim.W and 0 <= y < sim.H):
                line.append((" ", None, None))
                continue
            k = sim.grid[y][x]
            ch = GLYPHS.get(k, (" ", "."))[0 if unicode else 1]
            bg = C.get(k) if color else None
            fg = tuple(min(255, int(v * 1.6) + 30) for v in bg) if bg else None
            line.append((ch, fg, bg))
        out.append(line)
    for n, i in enumerate(sim.order):
        x, y = sim.checks[i]
        c, r = int(x) - cx, int(y) - cy
        if 0 <= c < cols and 0 <= r < rows:
            role = "done" if n < sim.passed else ("next" if n == sim.passed else "checkpoint")
            line = out[r]
            line[c] = (str(i), (C[role] if color else None), line[c][2])
    target = sim.next_point()
    if target is not None:                                # an arrow at the edge toward what is next
        c, r = int(target[0]) - cx, int(target[1]) - cy
        if not (0 <= c < cols and 0 <= r < rows):
            want = bearing(target[0] - sim.x, target[1] - sim.y)
            d = int(((want + TURN / 16) % TURN) // (TURN / 8))
            ec, er = cols // 2 + int(sin_u(want) * (cols // 2 - 1)), rows // 2 - int(cos_u(want) * (rows // 2 - 1))
            ec, er = max(0, min(cols - 1, ec)), max(0, min(rows - 1, er))
            out[er][ec] = ((ARROWS if unicode else ASCII_ARROWS)[d], C["next"] if color else None, out[er][ec][2])
    d = int(((sim.heading + TURN / 16) % TURN) // (TURN / 8))
    ch = (ARROWS if unicode else ASCII_ARROWS)[d]
    r, c = rows // 2, cols // 2
    if 0 <= r < rows and 0 <= c < cols:
        hi = sim.model in ("hover", "plane") and not sim.landed
        fg = C["vehicle"] if color else None
        if hi and color:
            fg = (255, 255, 160)
        out[r][c] = (ch, fg, out[r][c][2])
    return out


def compass(deg, width):
    """A strip of the compass round a heading: ``. . W . . N . . E``."""
    marks = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}
    out = []
    half = width // 2
    for i in range(width):
        a = (deg + (i - half) * 10) % 360
        m = next((v for k, v in marks.items() if abs((a - k + 180) % 360 - 180) < 5), None)
        out.append(m[0] if m and len(m) == 1 else ("·" if a % 30 < 10 else " "))
    out[half] = "|" if out[half] == " " or out[half] == "·" else out[half]
    return "".join(out)


def gauge_line(sim, g, env, width, unicode=True):
    """A gauge as ``(text, role)``: a bar, a centred bar, a number or a compass strip."""
    show = g.get("show")
    v = float(env.get(show, 0.0))
    scale = float(g.get("scale", 1))
    label = g.get("label") or show.upper()
    style = g.get("style", "bar")
    top = g.get("max", 100)
    top = float(env.get(top, 100)) if isinstance(top, str) else float(top)
    unit = g.get("unit", "")
    if style == "compass":
        return ("%-8s%s %3d°" % ("HEADING", compass(v, max(5, width - 14)), round(v) % 360), "info")
    if style == "number":
        return ("%-8s%.1f %s" % (label, v * scale, unit), "text")
    n = max(4, width - 16)
    full, empty = ("█", "░") if unicode else ("#", "-")
    warn = g.get("warn")
    role = "text"
    if warn is not None:
        frac = v / top if top else 0
        if (warn >= 0 and frac >= warn) or (warn < 0 and frac <= -warn):
            role = "hurt"
    if style == "center":
        half = n // 2
        k = max(-half, min(half, int(round(v / top * half)))) if top else 0
        bar = [empty] * n
        for i in range(min(half, half + k), max(half, half + k)):
            bar[i] = full
        bar[half] = "|"
        return ("%-8s%s %+.1f" % (label, "".join(bar), v * scale), role)
    k = max(0, min(n, int(round(v / top * n)))) if top else 0
    num = ("%.1f" if top * scale <= 20 else "%.0f") % (v * scale)
    return ("%-8s%s %s%s" % (label, full * k + empty * (n - k), num, (" " + unit) if unit else ""), role)


def sparkline(values, width, unicode=True):
    if not values:
        return ""
    vals = values[-width:]
    lo, hi = min(vals), max(vals)
    marks = "▁▂▃▄▅▆▇█" if unicode else "_.-=#"
    if hi - lo < 1e-9:
        return marks[len(marks) // 2] * len(vals)
    return "".join(marks[int((v - lo) / (hi - lo) * (len(marks) - 1))] for v in vals)


def panel_lines(sim, width, unicode=True):
    """The instruments: ``[(text, role)]``."""
    env = sim.env()
    out = [(sim.name, "title")]
    t = sim.ticks // sim.rate
    if sim.time_ticks:
        left = max(0, sim.time_ticks - sim.ticks) // sim.rate
        out.append(("TIME %d:%02d left" % (left // 60, left % 60), "alert" if left < 20 else "info"))
    else:
        out.append(("TIME %d:%02d" % (t // 60, t % 60), "info"))
    if sim.order:
        out.append(("CHECKPOINTS %d/%d%s" % (sim.passed, len(sim.order), ", then land" if sim.land else ""),
                    "ammo"))
    out.append(("", "text"))
    for g in sim.gauges:
        out.append(gauge_line(sim, g, env, width, unicode))
    for name, c in sim.controls.items():
        g = {"show": name, "label": c.get("label", name).upper()[:7], "max": c.get("max", 100)}
        out.append(gauge_line(sim, g, env, width, unicode))
    for name, vals in sim.history.items():
        out.append(("%-8s%s" % (name.upper()[:7], sparkline(vals, max(4, width - 9), unicode)), "dim"))
    return out


def help_line(sim):
    if sim.mode == "systems":
        keys = ", ".join("%s %s/%s" % (c.get("label", k), *(list(c.get("keys", [])) + ["", ""])[:2])
                         for k, c in sim.controls.items())
        return keys + "   P pause"
    if sim.model == "hover":
        return "↑↓ thrust  ←→ turn  W/S climb, descend   P pause"
    if sim.model == "plane":
        return "↑↓ throttle  ←→ turn  W/S climb, dive  Space brakes   P pause"
    return "↑ go  ↓ brake  ←→ steer  Space handbrake   P pause"


class Runner:
    """A sim on the terminal for :class:`engine.realtime.Loop`."""

    SOUNDS = {"empty": ("hopper_stop", "locked"), "refuel": ("refuel", "pickup"), "checkpoint": ("checkpoint", "pin"),
              "land": ("land", "plate"), "lift_off": ("hopper_start", "tick"), "crash": ("crash", "hurt"),
              "bump": ("bump", "hit"), "done": ("done", "win"), "fail": ("fail", "lose")}

    def __init__(self, sim, screen=None, audio=None):
        self.sim, self.screen, self.audio = sim, screen, audio

    @property
    def over(self):
        return self.sim.over

    def step(self, c):
        self.sim.step(c)
        if self.audio is not None:
            for e in self.sim.events[:2]:
                own, fallback = self.SOUNDS.get(e, (e, None))
                try:
                    self.audio.sfx(own, fallback) if fallback else self.audio.sfx(own)
                except Exception:
                    pass

    def rows(self, W, H, depth=3, unicode=True):
        from .frame import Painter
        sim = self.sim
        paint = self.screen.paint if self.screen is not None else Painter(depth)
        mh = max(4, H - 3)
        pw = min(40, max(26, W // 3)) if sim.mode == "vehicle" else min(W, 72)
        mw = W - pw - 1 if sim.mode == "vehicle" else 0
        cells = map_cells(sim, mw, mh, color=bool(depth), unicode=unicode) if mw > 0 else []
        lines = panel_lines(sim, pw - 1, unicode)[1:]          # (the name is on the line above)
        rows = []
        for r in range(mh):
            row = list(cells[r]) if cells else []
            if mw > 0:
                row.append((" ", None, None))
            text, role = lines[r] if r < len(lines) else ("", "text")
            if row:
                rows.append(row + [(ch, None, None) for ch in " " * 0] + text_cells(paint, text, role, pw, depth))
            else:
                rows.append(paint.text([((" " + text).ljust(W)[:W], role)], W))
        header = paint.text([(sim.name, "title")], W)
        rows = [header] + rows
        for i, (text, role) in enumerate(banner(sim)):
            r = 1 + mh // 2 - 1 + i
            if r < len(rows):
                pad = max(0, (W - len(text)) // 2)
                rows[r] = paint.text([(" " * pad + text + " " * max(0, W - pad - len(text)), role)], W)
        return rows

    def draw(self):
        if self.screen is None:
            return
        scr = self.screen
        W, H = scr.size()
        unicode = scr.unicode and scr.glyphs.get("half") == "▀"
        rows = self.rows(W, H, scr.paint.depth, unicode)
        text, role, until = self.sim.note
        scr.frame(rows, status=text if text and self.sim.tick < until else "",
                  footer=scr.paint.text([(help_line(self.sim), "dim")], W))


def text_cells(paint, text, role, width, depth):
    fg = {"title": (240, 220, 140), "ammo": (240, 240, 120), "hurt": (240, 110, 110), "info": (120, 200, 240),
          "dim": (130, 130, 130), "good": (120, 230, 120), "alert": (255, 170, 80)}.get(role, (210, 210, 210))
    return [(ch, fg if depth else None, None) for ch in text.ljust(width)[:width]]


def banner(sim):
    if sim.result == "won":
        return [("MISSION DONE", "good")]
    if sim.result == "lost":
        return [({"crashed": "CRASHED", "fuel": "OUT OF FUEL", "time": "OUT OF TIME", "sank": "SANK",
                  "failed": sim.spec.get("fail_text", "FAILED")}.get(sim.why, "FAILED"), "hurt")]
    if sim.paused == "ready":
        intro = sim.spec.get("intro") or []
        return [(sim.name, "title"), ("", "text")] + [(t, "text") for t in (intro if isinstance(intro, list) else
                                                                           [intro])] + \
            [("", "text"), (help_line(sim), "dim"), ("Press any key to start.", "prompt")]
    if sim.paused:
        return [("PAUSED", "title"), ("P, Esc or Enter goes on; Q leaves.", "dim")]
    return []


def play_frame(sim, term, audio=None, keys=None, clock=None):
    from .frame import Screen
    from .keys import KeyReader
    from .realtime import Loop
    screen = Screen(term, None, {}, term.animate)
    runner = Runner(sim, screen, audio)
    loop = Loop(runner, keys or KeyReader(), sim.rate, clock=clock)
    screen.start()
    try:
        loop.run()
    except KeyboardInterrupt:
        sim.result = sim.over = sim.result or "quit"
    finally:
        screen.stop()
    return loop.recorder


TEXT_HELP = ("Hold keys for seconds, ';' between: 'up 2; up right 1.5; w 1; wait 3'. Keys: up down left right "
             "w s space (and a control's keys). 'status' shows the instruments, 'map' the map, 'quit' leaves.")


def play_text(sim, write, read):
    """A sim a typed line at a time: keys held for some seconds, then the instruments."""
    sim.paused = None
    write(sim.name)
    intro = sim.spec.get("intro") or []
    for t in intro if isinstance(intro, list) else [intro]:
        write(t)
    write(TEXT_HELP)
    held = frozenset()
    while not sim.result:
        line = read("> ")
        if line is None:
            sim.result = sim.over = "quit"
            break
        for part in (line.split(";") if line.strip() else ["wait 1"]):
            words = part.split()
            if not words:
                continue
            if words[0] in ("quit", "q"):
                sim.result = sim.over = "quit"
                break
            if words[0] == "help":
                write(TEXT_HELP)
                continue
            if words[0] in ("status", "map"):
                lines = panel_lines(sim, 40, unicode=False) if words[0] == "status" else \
                    ["".join(ch for ch, _, _ in r) for r in map_cells(sim, 40, 15, color=False, unicode=False)]
                for t in lines:
                    write(t if isinstance(t, str) else t[0])
                continue
            secs = 1.0
            keys = []
            for w in words:
                try:
                    secs = max(0.05, min(60.0, float(w)))
                except ValueError:
                    if w != "wait":
                        keys.append(w)
            now = frozenset(keys)
            for i in range(int(round(secs * sim.rate))):
                sim.step(Controls(sim.tick, now, tuple(sorted(now - held)) if i == 0 else (),
                                  tuple(sorted(held - now)) if i == 0 else ()))
                held = now
                if sim.result:
                    break
            if sim.result:
                break
        if not sim.result:
            for t, role in panel_lines(sim, 40, unicode=False)[1:]:
                if t:
                    write(t)
            text, role, until = sim.note
            if text and sim.tick < until + sim.rate * 5:
                write(text)
    if sim.result in ("won", "lost"):
        write(banner(sim)[0][0] + ".")
    sim.over = sim.result
    return sim.result


def play_scene(game, scene):
    """Play the sim of a CLIo scene, then the scene's (or the sim's) effects: done, failed (none: the
    game is lost), left (none: the game ends)."""
    from . import conditions
    w, term, settings = game.world, game.term, game.settings
    sid = scene.get("sim")
    spec = game.data.sims.get(sid) or {}
    sim = make(game.data, sid)
    size_ok = True
    try:
        cols, rows = term.size()
        size_ok = cols >= 50 and rows >= 14
    except Exception:
        pass
    if spec.get("music"):
        try:
            game.audio.music(spec["music"])
        except Exception:
            pass
    frame = term.is_tty and term.ansi and size_ok and term.inp is None and not settings.get("lines") \
        and not settings.get("scroll_levels")
    if frame:
        play_frame(sim, term, game.audio)
    else:
        def read(prompt):
            try:
                return term.read(prompt)
            except Exception as e:
                if e.__class__.__name__ == "QuitGame":
                    return None
                raise
        play_text(sim, term.line, read)
    outcome = sim.result
    w.vars.setdefault("sims", {})[sid] = sim.stats()
    if outcome == "won":
        w.flags["%s_done" % sid] = True
        effects = scene.get("on_sim_done") or spec.get("on_done")
        if effects:
            conditions.run(effects, game)
        else:
            game.say("Mission done.", "success")
    elif outcome == "lost":
        effects = scene.get("on_sim_fail") or spec.get("on_fail")
        if effects:
            conditions.run(effects, game)
        else:
            game.end_game("lose", spec.get("death_text") or "outro_lose")
    else:
        effects = scene.get("on_sim_quit")
        if effects:
            conditions.run(effects, game)
        else:
            game.over = "quit"
    if not game.over:
        game.resume_music()
    return outcome


# --------------------------------------------------------------------------- #
# Checking
# --------------------------------------------------------------------------- #
def problems(data):
    out = []
    sims = getattr(data, "sims", None) or {}
    for sid, spec in sims.items():
        where = "sim '%s'" % sid
        if not isinstance(spec, dict):
            out.append("%s should be an object" % where)
            continue
        mode = spec.get("mode", "vehicle")
        if mode not in ("vehicle", "systems"):
            out.append("%s: mode should be vehicle or systems" % where)
        veh = spec.get("vehicle") or {}
        if mode == "vehicle":
            if veh.get("model", "car") not in MODELS:
                out.append("%s: vehicle model should be one of %s" % (where, ", ".join(MODELS)))
            rows = map_rows(spec)
            if not rows:
                out.append("%s: map should be a list of lines" % where)
                continue
            legend = spec.get("legend") or {}
            known = set(TERRAIN) | set(legend) | set("@123456789")
            bad = sorted({ch for r in rows for ch in r if ch not in known})
            if bad:
                out.append("%s: the map has characters nothing says the meaning of: %s" % (where, " ".join(bad)))
            if sum(r.count("@") for r in rows) != 1:
                out.append("%s: the map should have one start (@)" % where)
            if (spec.get("land") or spec.get("goal") == "land") and not any("H" in r for r in rows):
                out.append("%s: it ends with a landing, and the map has no pad (H)" % where)
            for k in veh:
                if k not in MODELS.get(veh.get("model", "car"), {}) and k not in ("model", "heading", "altitude",
                                                                                 "fuel_start"):
                    out.append("%s: vehicle '%s' is not one of the %s model's numbers"
                               % (where, k, veh.get("model", "car")))
        names = set(MODELS.get(veh.get("model", "car"), {})) | {"speed", "forward", "altitude", "height", "climb",
                                                                  "heading", "throttle", "thrust", "fuel", "fuel_max",
                                                                  "damage", "time", "landed", "passed", "x", "y",
                                                                  "next"}
        names |= set(spec.get("systems") or {}) | set(spec.get("controls") or {})
        texts = [("systems %s rate" % k, (v if isinstance(v, dict) else {"rate": v}).get("rate"))
                 for k, v in (spec.get("systems") or {}).items()]
        texts += [("systems %s value" % k, v.get("value")) for k, v in (spec.get("systems") or {}).items()
                  if isinstance(v, dict) and "value" in v]
        texts += [(k, spec.get(k)) for k in ("win_if", "fail_if", "score")]
        for what, text in texts:
            if text is None:
                continue
            try:
                f = formula(text)
            except FormulaError as e:
                out.append("%s: %s: %s" % (where, what, e))
                continue
            unknown = sorted(getattr(f, "names", set()) - names)
            if unknown:
                out.append("%s: %s reads %s, which nothing gives" % (where, what, ", ".join(unknown)))
        for k, c in (spec.get("controls") or {}).items():
            if not isinstance(c, dict) or not c.get("keys"):
                out.append("%s: control '%s' needs keys (up, down)" % (where, k))
        if spec.get("goal") == "survive" and not spec.get("time"):
            out.append("%s: a survive goal needs a time" % where)
        if mode == "systems" and not (spec.get("win_if") or spec.get("time")):
            out.append("%s: a systems sim needs win_if or a time" % where)
    for sid, sc in (getattr(data, "scenes", None) or {}).items():
        if sc.get("sim") and sc["sim"] not in sims:
            out.append("scene '%s': unknown sim '%s'" % (sid, sc["sim"]))
    return out


def main(argv=None):
    import os
    import sys
    import time
    from .data import GameData
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    path = argv.pop(0)
    data = GameData(path if os.path.isdir(path) else os.path.join("games", path))
    bad = 0
    for sid in argv or sorted(data.sims):
        t0 = time.time()
        sim = make(data, sid)
        fly(sim)
        bad += sim.result != "won"
        print("%s: %s (%s) at %.1f seconds, damage %d, fuel %d (%.1fs)" % (
            sid, sim.result or "not done", sim.why, sim.ticks / float(sim.rate), sim.damage, sim.fuel,
            time.time() - t0))
    return 1 if bad else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
