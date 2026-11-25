# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Skirmishes: real-time strategy on a map of characters.

A skirmish (``skirmishes.json``) is a map, a line a row, and its sides::

    "map": ["####################",
            "#1.....$$.........T#",
            "#......$$....##....#",
            "#..~~~.......##..2.#",
            "####################"],
    "sides": [{"name": "You", "control": "player"}, {"name": "Rival", "control": "ai"}]

``.`` ground, ``#`` rock, ``~`` water, ``T`` trees, ``$`` crystal (mined by workers), and ``1``-``4``
where each side starts: its headquarters there and workers round it. Units and buildings are kinds
(engine defaults below; a game's own in game.json ``"rts"``): workers gather crystal and build,
buildings train units, units move, fight and hold. A side is out when its buildings are gone.

The simulation runs at a fixed 10 ticks a second on whole numbers (positions in 256ths of a tile),
nothing left to chance: orders stamped with the tick they act on play a skirmish back the same, which
is what lockstep multiplayer needs. Paths come from flow fields (one per goal, shared by every unit
going there); the computer player is a plan of economy, building and attack waves.

    python -m engine.rts GAME [SKIRMISH]     # the computer plays your side too: who wins, how fast
"""

from __future__ import annotations

import hashlib
import heapq
import math

FP = 256
RATE = 10                                            # simulation ticks a second
INF = 1 << 30
TERRAIN = {".": "ground", " ": "ground", "#": "rock", "~": "water", "T": "trees", "$": "crystal", "&": "gas"}
OPEN = ("ground",)
MINED = ("crystal", "gas")                          # what workers gather (each a tile that empties)
ROLES = ("worker", "melee", "ranged", "heavy", "air", "transport", "hq", "barracks", "factory", "airfield",
         "tower")
ORDERS = ("move", "amove", "attack", "gather", "build", "train", "research", "cancel", "stop", "hold", "rally",
          "patrol", "repair", "board", "unload")
STATS = ("hp", "armor", "speed", "damage", "range", "cooldown", "sight", "splash", "carry")
NEIGH = ((1, 0, 10), (-1, 0, 10), (0, 1, 10), (0, -1, 10), (1, 1, 14), (-1, 1, 14), (1, -1, 14), (-1, -1, 14))
SIDE_COLORS = ["#40c8ff", "#ff5a4a", "#70e070", "#ffd040"]

KINDS = {
    "hq": {"name": "Headquarters", "role": "hq", "building": True, "size": [3, 3], "hp": 1200, "armor": 2,
           "sight": 7, "cost": 400, "time": 60, "char": "H", "produces": ["worker"], "dropoff": True},
    "barracks": {"name": "Barracks", "role": "barracks", "building": True, "size": [2, 2], "hp": 600, "armor": 1,
                 "sight": 5, "cost": 150, "time": 25, "char": "B", "produces": ["soldier", "ranger"]},
    "factory": {"name": "Factory", "role": "factory", "building": True, "size": [3, 2], "hp": 700, "armor": 2,
                "sight": 5, "cost": 200, "time": 35, "char": "F", "produces": ["tank"], "needs": "barracks"},
    "tower": {"name": "Tower", "role": "tower", "building": True, "size": [1, 1], "hp": 400, "armor": 2,
              "sight": 7, "cost": 100, "time": 20, "char": "T", "damage": 9, "range": 5, "cooldown": 1.2,
              "needs": "barracks"},
    "worker": {"name": "Worker", "role": "worker", "hp": 40, "speed": 2.6, "damage": 3, "range": 1,
               "cooldown": 1.2, "sight": 5, "cost": 50, "time": 10, "char": "w", "carry": 8, "gather": 2.5},
    "soldier": {"name": "Soldier", "role": "melee", "hp": 80, "armor": 1, "speed": 2.4, "damage": 8, "range": 1,
                "cooldown": 1.0, "sight": 6, "cost": 60, "time": 12, "char": "s"},
    "ranger": {"name": "Ranger", "role": "ranged", "hp": 50, "speed": 2.4, "damage": 6, "range": 4,
               "cooldown": 1.1, "sight": 7, "cost": 75, "time": 14, "char": "r"},
    "tank": {"name": "Tank", "role": "heavy", "hp": 220, "armor": 3, "speed": 1.7, "damage": 22, "range": 5,
             "cooldown": 2.4, "splash": 1, "sight": 7, "cost": 160, "gas": 50, "time": 24, "char": "t",
             "needs": "tracks"},
    "airfield": {"name": "Airfield", "role": "airfield", "building": True, "size": [3, 2], "hp": 600, "armor": 1,
                 "sight": 6, "cost": 200, "gas": 50, "time": 35, "char": "A", "produces": ["gunship", "lifter"],
                 "needs": "factory"},
    "gunship": {"name": "Gunship", "role": "air", "air": True, "hp": 110, "armor": 1, "speed": 3.2, "damage": 9,
                "range": 3, "cooldown": 1.2, "sight": 8, "cost": 120, "gas": 60, "time": 20, "char": "g"},
    "lifter": {"name": "Lifter", "role": "transport", "air": True, "hp": 140, "armor": 2, "speed": 3.0,
               "damage": 0, "range": 1, "sight": 7, "cost": 100, "gas": 25, "time": 18, "char": "l", "carries": 6},
}
UPGRADES = {
    "weapons": {"name": "Weapons", "at": "barracks", "cost": 150, "gas": 50, "time": 40,
                "to": ["melee", "ranged", "heavy", "air"], "damage": 2},
    "plating": {"name": "Plating", "at": "barracks", "cost": 150, "gas": 50, "time": 40,
                "to": ["melee", "ranged", "heavy", "air"], "armor": 1, "hp": 10},
    "drills": {"name": "Drills", "at": "hq", "cost": 100, "time": 30, "to": ["worker"], "carry": 2},
    "tracks": {"name": "Tracks", "at": "factory", "cost": 100, "gas": 50, "time": 30, "to": ["heavy"],
               "speed": 0.3},
    "optics": {"name": "Optics", "at": "factory", "cost": 100, "gas": 25, "time": 25, "to": ["ranged", "tower"],
               "range": 1, "sight": 1, "needs": "weapons"},
}
KIND = {"hp": 50, "armor": 0, "speed": 2.0, "damage": 0, "range": 1, "cooldown": 1.0, "sight": 5, "cost": 50,
        "time": 10, "splash": 0, "carry": 0, "gather": 2.5, "size": [1, 1], "produces": [], "needs": None,
        "building": False, "dropoff": False, "faction": None, "gas": 0, "air": False, "carries": 0, "hits": None,
        "research": []}
AI = {"workers": 8,           # workers it keeps
      "gas": 2,               # of them on gas, once it has barracks
      "research": True,       # upgrades, when it has crystal to spare
      "wave": 5,              # army units in its first attack (two more each time)
      "most": 14,             # ... up to this many
      "first": 150,           # seconds before its first attack, at the soonest
      "towers": 1,            # towers by its headquarters
      "mix": {"melee": 2, "ranged": 2, "heavy": 1},
      "every": 1.0}           # seconds between its decisions
COLORS = {"ground": "#1b2418", "ground_dim": "#11160f", "rock": "#4a4a52", "rock_dim": "#2a2a30",
          "water": "#173a5c", "water_dim": "#0e2236", "trees": "#3f8f3a", "crystal": "#4ae0e0", "gas": "#d080ff",
          "fog": "#000000", "cursor": "#ffffff", "select": "#f0f0a0", "shot": "#ffffa0", "text": "#d0d0d0",
          "place_ok": "#60e060", "place_bad": "#e05050", "neutral": "#a0a0a0"}


def colour(c, default=(128, 128, 128)):
    if isinstance(c, (list, tuple)) and len(c) == 3:
        return tuple(int(v) for v in c)
    if isinstance(c, str) and len(c) == 7 and c[0] == "#":
        try:
            return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            pass
    return default


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def ticks(seconds, rate=RATE):
    return max(1, int(round(float(seconds) * rate)))


def settings_of(data):
    cfg = (getattr(data, "config", None) or {}).get("rts") or {}
    return cfg if isinstance(cfg, dict) else {}


def kinds_of(data=None, spec=None):
    """The engine's kinds, a game's over them (``"engine_kinds": false`` leaves the engine's out), a
    skirmish's over those; each filled out with the defaults."""
    cfg = settings_of(data)
    out = {} if cfg.get("engine_kinds") is False else {k: dict(v) for k, v in KINDS.items()}
    for src in (cfg.get("kinds"), (spec or {}).get("kinds")):
        for k, v in (src or {}).items():
            if isinstance(v, dict):
                out[k] = dict(out.get(k, {}), **v)
    return {k: dict(KIND, **v) for k, v in out.items()}


def upgrades_of(data=None, spec=None, kinds=None):
    """The engine's upgrades (with its kinds), a game's, a skirmish's: each ``{name, at (a building kind), cost,
    gas, time, to (kinds or roles), needs, faction}`` and what it adds (``damage``, ``armor``, ``hp``...)."""
    cfg = settings_of(data)
    out = {} if cfg.get("engine_kinds") is False else {k: dict(v) for k, v in UPGRADES.items()}
    for src in (cfg.get("upgrades"), (spec or {}).get("upgrades")):
        for k, v in (src or {}).items():
            if isinstance(v, dict):
                out[k] = dict(out.get(k, {}), **v)
    return out


def names_of(data=None, spec=None):
    """What the two things mined are called (``"names": {"crystal": "Xantrium", "gas": "Plasma"}``)."""
    n = {"crystal": "Crystal", "gas": "Gas"}
    n.update(settings_of(data).get("names") or {})
    n.update((spec or {}).get("names") or {})
    return n


def map_rows(spec):
    m = spec.get("map")
    if isinstance(m, str):
        m = m.split("\n")
    return [r for r in m if isinstance(r, str)] if isinstance(m, list) else []


class Side:
    def __init__(self, i, spec, faction):
        self.i = i
        self.name = spec.get("name") or "Side %d" % (i + 1)
        self.control = spec.get("control") if spec.get("control") in ("player", "ai", "none") else "ai"
        self.color = colour(spec.get("color"), colour(SIDE_COLORS[i % len(SIDE_COLORS)]))
        self.credits = int(spec.get("credits", 200))
        self.gas = int(spec.get("gas_start", 0))
        self.upgrades = list(spec.get("upgrades") or [])
        self.faction = faction
        self.ai = dict(AI, **(spec.get("ai") or {}))
        self.wave = int(self.ai["wave"])
        self.attacks = 0
        self.out = False
        self.start = None
        self.warned = -INF

    def key(self):
        return (self.i, self.credits, self.gas, tuple(self.upgrades), self.wave, self.attacks, self.out)


class Thing:
    """A unit or a building. Units: ``x, y`` the middle, in 256ths of a tile. Buildings: ``tx, ty`` the top
    left tile, ``w, h`` tiles; ``x, y`` their middle too."""

    def __init__(self, i, kind, spec, side):
        self.id, self.kind, self.spec, self.side = i, kind, spec, side
        self.building = bool(spec.get("building"))
        self.hp = self.max = int(spec["hp"])
        self.x = self.y = 0
        self.tx = self.ty = 0
        self.w, self.h = (int(spec["size"][0]), int(spec["size"][1])) if self.building else (1, 1)
        self.order = {"do": "idle"}
        self.engage = 0                              # an enemy it took on by itself
        self.post = None                             # where it stands when idle
        self.cool = 0
        self.carry = 0
        self.done = True                             # a building: built
        self.built = 0
        self.queue = []
        self.progress = 0
        self.rally = None
        self.shot = None                             # (x, y, tick): for the picture
        self.load = "crystal"                        # what a worker carries
        self.cargo = []                              # a transport's passengers (their ids)
        self.inside = 0                              # the transport a unit is in
        self.air = bool(spec.get("air"))

    def key(self):
        return (self.id, self.kind, self.side, self.hp, self.x, self.y, sorted(self.order.items(), key=str),
                self.engage, self.post, self.cool, self.carry, self.done, self.built, tuple(self.queue),
                self.progress, self.rally, self.load, tuple(self.cargo), self.inside)


class World:
    """One skirmish being played: :meth:`order` from the sides, :meth:`step` a tick at a time."""

    def __init__(self, spec, sid="skirmish", data=None, rate=RATE):
        self.id, self.spec, self.rate = sid, spec, rate
        self.name = spec.get("title") or spec.get("name") or sid
        self.kinds = kinds_of(data, spec)
        self.upgrades = upgrades_of(data, spec, self.kinds)
        self.names = names_of(data, spec)
        cfg = settings_of(data)
        self.colors = {k: colour(v) for k, v in dict(COLORS, **(cfg.get("colors") or {}),
                                                     **(spec.get("colors") or {})).items()}
        self.limit = int(spec.get("limit", cfg.get("limit", 40)))
        self.goal = spec.get("goal") if spec.get("goal") in ("destroy", "survive") else "destroy"
        self.time_ticks = ticks(spec["time"], rate) if spec.get("time") else 0
        rows = map_rows(spec)
        self.W = max([len(r) for r in rows] or [1])
        self.H = max(1, len(rows))
        amount = {"crystal": int(spec.get("crystal", 600)), "gas": int(spec.get("gas", 1500))}
        self.terrain = []
        self.amount = {}                             # what is left in each tile of crystal or gas
        starts = {}
        legend = spec.get("legend") or {}
        placed = []
        for y in range(self.H):
            row = rows[y] if y < len(rows) else ""
            for x in range(self.W):
                ch = row[x] if x < len(row) else "."
                t = TERRAIN.get(ch)
                if t is None and ch in legend:
                    v = legend[ch]
                    t = v if isinstance(v, str) and v in TERRAIN.values() else "ground"
                    if isinstance(v, dict):
                        placed.append((x, y, v))
                if t is None:
                    t = "ground"
                    if ch.isdigit():
                        starts[int(ch) - 1] = (x, y)
                self.terrain.append(t)
                if t in MINED:
                    self.amount[y * self.W + x] = amount[t]
        self.things = {}
        self.next_id = 1
        self.block = [0] * (self.W * self.H)         # a building's id on each tile it stands on
        self.version = 0                             # goes up when what can be walked changes
        self.fields = {}
        self.tick = 0
        self.pending = []
        self.journal = []                            # [[tick, side, order]] - the orders, as played
        self.messages = []
        self.result = self.over = self.why = None
        self.ending = 0
        self.sides = []
        for i, sspec in enumerate(spec.get("sides") or [{"control": "player"}, {"control": "ai"}]):
            sspec = sspec if isinstance(sspec, dict) else {}
            side = Side(i, sspec, sspec.get("faction"))
            self.sides.append(side)
            at = starts.get(i)
            side.start = at
            if at is None:
                continue
            hq = sspec.get("hq", self.of_role(side, "hq"))
            if hq and hq in self.kinds:
                w, h = self.kinds[hq]["size"]
                self.add(hq, i, at[0] - w // 2, at[1] - h // 2)
            worker = self.of_role(side, "worker")
            for n in range(int(sspec.get("workers", 4))):
                if worker:
                    self.spawn_near(worker, i, at, n)
            for kind, n in (sspec.get("units") or {}).items():
                for _ in range(int(n)):
                    if kind in self.kinds:
                        self.spawn_near(kind, i, at, 0)
        for x, y, v in placed:
            side = int(v.get("side", 0)) - 1
            kind = v.get("unit") or v.get("building")
            if kind in self.kinds and -1 <= side < len(self.sides):
                if self.kinds[kind]["building"]:
                    self.add(kind, side, x, y)
                else:
                    self.add(kind, side, x * FP + FP // 2, y * FP + FP // 2)
        self.player = next((s.i for s in self.sides if s.control == "player"), None)
        self.explored = [bytearray(self.W * self.H) for _ in self.sides]
        self.visible = bytearray(self.W * self.H)
        self.see()

    @property
    def crystal(self):
        """What is left in each crystal tile."""
        return {i: a for i, a in self.amount.items() if self.terrain[i] == "crystal"}

    def has(self, side, need):
        """Whether a side has what something needs: a building of a kind (built), or an upgrade."""
        if not need:
            return True
        if need in self.upgrades:
            return need in self.sides[side].upgrades
        return any(t.kind == need and t.side == side and t.done for t in self.things.values())

    def applies(self, up, t):
        to = up.get("to")
        return to is None or t.kind in to or t.spec.get("role") in to

    def stat(self, t, f):
        """A thing's number with its side's upgrades added."""
        v = t.spec.get(f) or 0
        if t.side >= 0:
            for u in self.sides[t.side].upgrades:
                up = self.upgrades.get(u)
                if up and f in up and self.applies(up, t):
                    v = v + up[f]
        return v

    def afford(self, side, spec):
        s = self.sides[side]
        return s.credits >= int(spec.get("cost") or 0) and s.gas >= int(spec.get("gas") or 0)

    def pay(self, side, spec, sign=1):
        s = self.sides[side]
        s.credits -= sign * int(spec.get("cost") or 0)
        s.gas -= sign * int(spec.get("gas") or 0)

    def price(self, spec):
        g = int(spec.get("gas") or 0)
        return "%d" % int(spec.get("cost") or 0) + ("/%d" % g if g else "")

    # ---- the map ----------------------------------------------------------- #
    def inside(self, x, y):
        return 0 <= x < self.W and 0 <= y < self.H

    def walkable(self, i):
        return self.terrain[i] in OPEN and not self.block[i]

    def of_role(self, side, role):
        """The first kind of a role a side may have (its faction's)."""
        for k, s in self.kinds.items():
            if s.get("role") == role and s.get("faction") == side.faction:
                return k
        return None

    def allowed(self, side, kind):
        s = self.kinds.get(kind)
        return s is not None and s.get("faction") == self.sides[side].faction

    def fits(self, kind, tx, ty, side=None):
        """Whether a building of ``kind`` can stand with its top left at ``tx, ty`` (on ground, on no other,
        on tiles the side has seen)."""
        w, h = self.kinds[kind]["size"]
        for y in range(ty, ty + h):
            for x in range(tx, tx + w):
                if not self.inside(x, y):
                    return False
                i = y * self.W + x
                if self.terrain[i] not in OPEN or self.block[i]:
                    return False
                if side is not None and self.sides[side].control == "player" and not self.explored[side][i]:
                    return False
        return True

    # ---- things ------------------------------------------------------------ #
    def add(self, kind, side, x, y, done=True):
        """A thing; a building at tile ``x, y`` (top left), a unit at ``x, y`` (its middle, fixed point)."""
        t = Thing(self.next_id, kind, self.kinds[kind], side)
        self.next_id += 1
        if side >= 0 and side < len(self.sides):
            t.hp = t.max = int(self.stat(t, "hp"))
        if t.building:
            t.tx, t.ty = x, y
            t.x, t.y = x * FP + t.w * FP // 2, y * FP + t.h * FP // 2
            for yy in range(y, y + t.h):
                for xx in range(x, x + t.w):
                    if self.inside(xx, yy):
                        self.block[yy * self.W + xx] = t.id
            self.version += 1
            if not done:
                t.done, t.hp = False, 1
        else:
            t.x, t.y = x, y
            t.post = (x, y)
        self.things[t.id] = t
        return t

    def spawn_near(self, kind, side, at, n=0):
        """A unit on the nearest free tile round ``at``."""
        tiles = self.free_round(at[0], at[1], 1)
        if not tiles:
            return None
        x, y = tiles[0]
        return self.add(kind, side, x * FP + FP // 2, y * FP + FP // 2)

    def free_round(self, cx, cy, n, rmax=12):
        out = []
        for r in range(0, rmax + 1):
            ring = [(cx + dx, cy + dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
                    if max(abs(dx), abs(dy)) == r]
            ring.sort(key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p[1], p[0]))
            for x, y in ring:
                if self.inside(x, y) and self.walkable(y * self.W + x) and not self.unit_on(x, y):
                    out.append((x, y))
                    if len(out) >= n:
                        return out
        return out

    def unit_on(self, x, y):
        return any(not t.building and not t.air and not t.inside and t.x // FP == x and t.y // FP == y
                   for t in self.things.values())

    def at(self, x, y, side=None, units_first=True):
        """What is on tile ``x, y``: a unit, else a building (of ``side``, if given)."""
        hit = None
        for t in self.things.values():
            if (side is not None and t.side != side) or t.inside:
                continue
            if t.building:
                if t.tx <= x < t.tx + t.w and t.ty <= y < t.ty + t.h and hit is None:
                    hit = t
            elif t.x // FP == x and t.y // FP == y:
                if units_first:
                    return t
                hit = hit or t
        return hit

    def remove(self, t, why="destroyed"):
        if t.id not in self.things:
            return
        del self.things[t.id]
        for i in t.cargo:                                 # a transport lost: its passengers with it
            self.things.pop(i, None)
        if t.building:
            for y in range(t.ty, t.ty + t.h):
                for x in range(t.tx, t.tx + t.w):
                    if self.inside(x, y) and self.block[y * self.W + x] == t.id:
                        self.block[y * self.W + x] = 0
            self.version += 1
            if t.side == self.player:
                self.say("Your %s was %s." % (t.spec["name"].lower(), why), "hurt")
            elif self.player is not None and t.side >= 0:
                self.say("%s %s %s." % (self.sides[t.side].name, t.spec["name"].lower(), why), "good")

    def say(self, text, role="text"):
        self.messages.append((self.tick, text, role))
        del self.messages[:-8]

    # ---- distances and paths ----------------------------------------------- #
    def dist2(self, a, b):
        """Squared distance from ``a``'s middle to ``b`` (its middle, or a building's nearest edge)."""
        if b.building:
            x = min(max(a.x, b.tx * FP), (b.tx + b.w) * FP - 1)
            y = min(max(a.y, b.ty * FP), (b.ty + b.h) * FP - 1)
        else:
            x, y = b.x, b.y
        return (a.x - x) ** 2 + (a.y - y) ** 2

    def in_range(self, a, b, tiles):
        r = int(float(tiles) * FP) + FP // 2
        return self.dist2(a, b) <= r * r

    def goals(self, key):
        kind = key[0]
        W = self.W
        if kind == "at":
            x, y = key[1], key[2]
            if self.inside(x, y) and self.walkable(y * W + x):
                return [y * W + x]
            key = ("by", x, y, 1, 1)
        _, x0, y0, w, h = key
        out = []
        for y in range(y0 - 1, y0 + h + 1):
            for x in range(x0 - 1, x0 + w + 1):
                if (x0 <= x < x0 + w and y0 <= y < y0 + h) or not self.inside(x, y):
                    continue
                if self.walkable(y * W + x):
                    out.append(y * W + x)
        return out

    def field(self, key):
        """Distances to a goal over what can be walked (10 a tile, 14 a diagonal): ``("at", x, y)`` a tile,
        ``("by", x, y, w, h)`` the tiles round a rectangle. Kept until the map changes."""
        k = (key, self.version)
        f = self.fields.get(k)
        if f is not None:
            return f
        W, H = self.W, self.H
        dist = [INF] * (W * H)
        heap = []
        for i in self.goals(key):
            dist[i] = 0
            heap.append((0, i))
        heapq.heapify(heap)
        terrain, block = self.terrain, self.block
        while heap:
            d, i = heapq.heappop(heap)
            if d > dist[i]:
                continue
            x, y = i % W, i // W
            for dx, dy, c in NEIGH:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < W and 0 <= ny < H):
                    continue
                j = ny * W + nx
                if terrain[j] not in OPEN or block[j]:
                    continue
                if dx and dy:
                    a, b = y * W + nx, ny * W + x
                    if terrain[a] not in OPEN or block[a] or terrain[b] not in OPEN or block[b]:
                        continue
                nd = d + c
                if nd < dist[j]:
                    dist[j] = nd
                    heapq.heappush(heap, (nd, j))
        if len(self.fields) >= 48:
            self.fields.pop(next(iter(self.fields)))
        self.fields[k] = dist
        return dist

    def clear_line(self, a, bx, by):
        dx, dy = bx - a.x, by - a.y
        n = max(abs(dx), abs(dy)) // (FP // 2) + 1
        for i in range(1, n + 1):
            x, y = (a.x + dx * i // n) // FP, (a.y + dy * i // n) // FP
            if not self.inside(x, y) or not self.walkable(y * self.W + x):
                return False
        return True

    def toward(self, u, px, py):
        """A tick's step straight at a point; never into rock, water or a building (along the wall instead)."""
        dx, dy = px - u.x, py - u.y
        sp = self.speed(u)
        n = math.isqrt(dx * dx + dy * dy)
        there = n <= sp
        nx, ny = (px, py) if there else (u.x + dx * sp // n, u.y + dy * sp // n)
        if self._open_at(nx, ny) or not self._open_at(u.x, u.y) or (u.air and self.inside(nx // FP, ny // FP)):
            u.x, u.y = nx, ny
            return there
        if self._open_at(nx, u.y):
            u.x = nx
        elif self._open_at(u.x, ny):
            u.y = ny
        return False

    def _open_at(self, x, y):
        tx, ty = x // FP, y // FP
        return self.inside(tx, ty) and self.walkable(ty * self.W + tx)

    def speed(self, u):
        sp = self.speed_of(u)
        pace = u.order.get("pace")
        return min(sp, pace) if pace else sp

    def advance(self, u, key, near=0):
        """A tick's walk toward a goal: True there (within ``near``), None if it cannot be reached."""
        if u.air:
            return self._fly(u, key, near)
        f = self.field(key)
        W = self.W
        tx, ty = u.x // FP, u.y // FP
        i = ty * W + tx
        d = f[i] if self.inside(tx, ty) else INF
        if d <= near:
            if key[0] == "at" and near == 0:
                return self.toward(u, tx * FP + FP // 2, ty * FP + FP // 2)
            return True
        if d >= INF:
            for dx, dy, _ in NEIGH:                   # standing where it cannot: out to a tile it can
                nx, ny = tx + dx, ty + dy
                if self.inside(nx, ny) and f[ny * W + nx] < INF:
                    self.toward(u, nx * FP + FP // 2, ny * FP + FP // 2)
                    return False
            return None
        best, bd = None, d
        for dx, dy, _ in NEIGH:
            nx, ny = tx + dx, ty + dy
            if 0 <= nx < W and 0 <= ny < self.H:
                nd = f[ny * W + nx]
                if nd < bd and (not (dx and dy) or (self.walkable(ty * W + nx) and self.walkable(ny * W + tx))):
                    best, bd = (nx, ny), nd                   # a diagonal only past two open sides
        if best is None:
            return True
        self.toward(u, best[0] * FP + FP // 2, best[1] * FP + FP // 2)
        return False

    def _fly(self, u, key, near=0):
        """Straight over anything: to a tile's middle, or beside a rectangle."""
        if key[0] == "at":
            px, py = key[1] * FP + FP // 2, key[2] * FP + FP // 2
            if near and (u.x - px) ** 2 + (u.y - py) ** 2 <= (near * FP // 10) ** 2:
                return True
            return self.toward(u, px, py)
        _, x0, y0, w, h = key
        px = min(max(u.x, x0 * FP - FP // 2), (x0 + w) * FP + FP // 2)
        py = min(max(u.y, y0 * FP - FP // 2), (y0 + h) * FP + FP // 2)
        if (u.x - px) ** 2 + (u.y - py) ** 2 <= (FP // 4) ** 2:
            return True
        self.toward(u, px, py)
        return False

    def hits(self, a, b):
        """Whether ``a`` can hit ``b``: fliers only by what hits the air (ranged, by default)."""
        h = a.spec.get("hits") or ("both" if float(self.stat(a, "range")) >= 2 else "ground")
        return h == "both" or (h == "air") == b.air

    # ---- orders ------------------------------------------------------------ #
    def order(self, side, order):
        """An order from a side, acted on at the next tick: ``{"do": ..., "units": [ids], ...}``."""
        self.pending.append((side, order))

    def _apply(self, side, o):
        do = o.get("do")
        mine = [self.things[i] for i in o.get("units", []) if i in self.things and self.things[i].side == side]
        units = [t for t in mine if not t.building and not t.inside]
        if do in ("move", "amove", "patrol"):
            self._group_move(units, do, tuple(o["to"]))
        elif do == "attack":
            t = self.things.get(o.get("target"))
            if t is not None:
                for u in units:
                    if self.stat(u, "damage") and self.hits(u, t):
                        u.order = {"do": "attack", "target": t.id}
                        u.engage = 0
        elif do == "gather":
            at = tuple(o["at"])
            for u in units:
                if u.spec.get("role") == "worker":
                    u.order = {"do": "gather", "at": at, "phase": "back" if u.carry else "go", "t": 0}
        elif do == "repair":
            b = self.things.get(o.get("id"))
            if b is not None and b.side == side and b.building and b.done:
                for u in units:
                    if u.spec.get("role") == "worker":
                        u.order = {"do": "repair", "id": b.id, "hp": 0}
        elif do == "board":
            t = self.things.get(o.get("id"))
            if t is not None and t.side == side and t.spec.get("carries"):
                for u in units:
                    if u is not t and not u.spec.get("carries") and not u.air:
                        u.order = {"do": "board", "id": t.id}
        elif do == "unload":
            for u in units:
                if u.cargo:
                    u.order = {"do": "unload", "to": tuple(o["to"])}
        elif do == "build":
            kind, (tx, ty) = o.get("kind"), o.get("at", (0, 0))
            builders = [u for u in units if u.spec.get("role") == "worker"]
            if o.get("id") in self.things:                  # help build one begun
                b = self.things[o["id"]]
                if b.side == side and not b.done:
                    for u in builders:
                        u.order = {"do": "build", "kind": b.kind, "at": (b.tx, b.ty), "id": b.id, "paid": 0}
                return
            if not builders or not self.allowed(side, kind) or not self.kinds[kind]["building"]:
                return
            spec = self.kinds[kind]
            if not self.has(side, spec.get("needs")):
                return self.tell(side, "A %s needs %s first." % (spec["name"].lower(), self.what(spec["needs"])))
            if not self.afford(side, spec):
                return self.tell(side, "Not enough (%s)." % self.price(spec))
            if not self.fits(kind, tx, ty, side):
                return self.tell(side, "It cannot stand there.")
            self.pay(side, spec)
            u = builders[0]
            u.order = {"do": "build", "kind": kind, "at": (tx, ty), "id": 0, "paid": 1}
            for v in builders[1:]:
                v.order = {"do": "build", "kind": kind, "at": (tx, ty), "id": 0, "paid": 0, "wait": u.id}
        elif do in ("train", "research"):
            b = self.things.get(o.get("building"))
            if b is None or b.side != side or not b.building or not b.done or len(b.queue) >= 5:
                return
            if do == "train":
                kind = o.get("kind")
                if kind not in b.spec.get("produces", []) or not self.allowed(side, kind):
                    return
                spec, item = self.kinds[kind], kind
                count = sum(1 for t in self.things.values() if t.side == side and not t.building) + \
                    sum(sum(1 for q in t.queue if not q.startswith("up:"))
                        for t in self.things.values() if t.side == side and t.building)
                if count >= self.limit:
                    return self.tell(side, "No more units (%d at most)." % self.limit)
            else:
                uid = o.get("upgrade")
                spec = self.upgrades.get(uid)
                if spec is None or uid not in self.researchable(b):
                    return
                item = "up:" + uid
            if not self.has(side, spec.get("needs")):
                return self.tell(side, "%s needs %s first." % (spec["name"], self.what(spec["needs"])))
            if not self.afford(side, spec):
                return self.tell(side, "Not enough (%s)." % self.price(spec))
            self.pay(side, spec)
            b.queue.append(item)
        elif do == "cancel":
            b = self.things.get(o.get("building"))
            if b is not None and b.side == side and b.queue:
                item = b.queue.pop()
                self.pay(side, self.upgrades[item[3:]] if item.startswith("up:") else self.kinds[item], -1)
                if not b.queue:
                    b.progress = 0
        elif do == "rally":
            for b in mine:
                if b.building:
                    b.rally = tuple(o["to"])
        elif do in ("stop", "hold"):
            for u in units:
                u.order = {"do": "idle" if do == "stop" else "hold"}
                u.post = (u.x, u.y)
                u.engage = 0

    def what(self, need):
        if need in self.upgrades:
            return "the %s upgrade" % self.upgrades[need]["name"]
        return "a %s" % self.kinds[need]["name"].lower() if need in self.kinds else need

    def researchable(self, b):
        """The upgrades a building can still make for its side (not made, not being made)."""
        side = self.sides[b.side]
        doing = {q[3:] for t in self.things.values() if t.side == b.side and t.building for q in t.queue
                 if q.startswith("up:")}
        return [u for u, up in self.upgrades.items() if up.get("at") in (b.kind, b.spec.get("role"))
                and up.get("faction") in (None, side.faction) and u not in side.upgrades and u not in doing]

    def _group_move(self, units, do, to):
        """Units sent together: each to its place in the group's shape round ``to`` (kept tight), all at the
        slowest one's pace."""
        if not units:
            return
        pace = min(self.speed_of(u) for u in units) if len(units) > 1 else 0
        cx = sum(u.x for u in units) // len(units) // FP
        cy = sum(u.y for u in units) // len(units) // FP
        reach = 1 + math.isqrt(len(units)) // 2
        for u in units:
            dx = max(-reach, min(reach, u.x // FP - cx))
            dy = max(-reach, min(reach, u.y // FP - cy))
            x, y = to[0] + dx, to[1] + dy
            spot, near = (x, y), 0
            if len(units) < 2 or not self.inside(x, y) or not (u.air or self.walkable(y * self.W + x)):
                spot, near = to, (0 if len(units) < 2 else 10 * reach)
            u.order = {"do": do, "to": spot, "near": near}
            if pace:
                u.order["pace"] = pace
            if do == "patrol":
                u.order["back"] = (u.x // FP, u.y // FP)
            u.engage = 0

    def speed_of(self, u):
        return max(1, int(round(float(self.stat(u, "speed")) * FP / self.rate)))

    def tell(self, side, text):
        if side == self.player:
            self.say(text, "alert")

    # ---- a tick ------------------------------------------------------------ #
    def step(self):
        """One tick: the orders, the computer players, the units, the buildings, who is out."""
        self.tick += 1
        if self.over:
            return
        if self.result:
            self.ending -= 1
            if self.ending <= 0:
                self.over = self.result
            return
        for side, o in self.pending:
            if self.sides[side].control != "ai":       # the computer's own are made again on replay
                self.journal.append([self.tick, side, o])
            self._apply(side, o)
        self.pending = []
        for s in self.sides:
            if s.control == "ai" and not s.out and (self.tick + s.i * 3) % ticks(s.ai["every"], self.rate) == 0:
                plan(self, s)
        for t in list(self.things.values()):
            if t.id not in self.things or t.inside:
                continue
            if t.building:
                self._building(t)
            else:
                self._unit(t)
        self._apart()
        if self.tick % 2 == 0:
            self.see()
        self._who_is_out()

    def _who_is_out(self):
        alive = set()
        for t in self.things.values():
            if t.building and t.side >= 0:
                alive.add(t.side)
        for s in self.sides:
            if not s.out and s.i not in alive and s.control != "none":
                s.out = True
                if s.i != self.player:
                    self.say("%s is out." % s.name, "good")
        if self.player is None:
            standing = [s for s in self.sides if not s.out and s.control != "none"]
            if len(standing) <= 1:
                self._end("won" if standing else "lost", standing[0].i if standing else None)
            return
        me = self.sides[self.player]
        if me.out:
            self._end("lost", "out")
        elif self.goal == "survive" and self.tick >= self.time_ticks:
            self._end("won", "time")
        else:
            rivals = [s for s in self.sides if s.i != self.player and s.control != "none"]
            if rivals and all(s.out for s in rivals):       # (with none, a sandbox: no end but the time)
                self._end("won", "destroyed")

    def _end(self, result, why):
        self.result, self.why = result, why
        self.ending = self.rate * 2

    def enemy(self, a, b):
        return b.side != a.side and b.side >= 0 and a.side >= 0

    def acquire(self, u, tiles):
        r = int(float(tiles) * FP) + FP // 2
        best, bd = None, r * r + 1
        for t in self.things.values():
            if t.inside or not self.enemy(u, t) or not self.hits(u, t):
                continue
            d = self.dist2(u, t) + (FP * FP * 4 if t.building else 0)    # units before buildings
            if d < bd or (d == bd and best is not None and t.id < best.id):
                best, bd = t, d
        return best

    def _fire(self, u, t):
        if u.cool > 0:
            return
        dmg = max(1, int(self.stat(u, "damage")) - int(self.stat(t, "armor")))
        u.cool = ticks(self.stat(u, "cooldown"), self.rate)
        u.shot = (t.x, t.y, self.tick)
        self._hurt(t, dmg, u)
        splash = int(self.stat(u, "splash") or 0)
        if splash:
            r = splash * FP + FP // 2
            for o in list(self.things.values()):
                if o is not t and not o.inside and o.air == t.air and self.enemy(u, o) and self.dist2(t, o) <= r * r:
                    self._hurt(o, max(1, dmg // 2 - int(self.stat(o, "armor"))), u)

    def _hurt(self, t, dmg, by):
        t.hp -= dmg
        if t.side == self.player and self.tick - self.sides[t.side].warned > self.rate * 15:
            self.sides[t.side].warned = self.tick
            self.say("Under attack near %d,%d." % (t.x // FP, t.y // FP), "hurt")
        if t.hp <= 0:
            self.remove(t)
        elif not t.building and t.order["do"] in ("idle", "hold") and not t.engage and self.stat(t, "damage") \
                and t.spec.get("role") != "worker" and self.hits(t, by):
            t.engage = by.id                                 # hit back

    def _fight(self, u, t, chase=True):
        """Shoot ``t`` if in range, else (if it may) go for it; False when it cannot."""
        if not self.hits(u, t) or t.inside:
            return False
        if self.in_range(u, t, self.stat(u, "range")):
            self._fire(u, t)
            return True
        if not chase:
            return False
        if u.air or (self.dist2(u, t) <= (10 * FP) ** 2 and self.clear_line(u, t.x, t.y) and not t.building):
            if t.building:
                return self._fly(u, ("by", t.tx, t.ty, t.w, t.h)) is not None
            self.toward(u, t.x, t.y)
            return True
        key = ("by", t.tx, t.ty, t.w, t.h) if t.building else ("at", t.x // FP, t.y // FP)
        return self.advance(u, key, near=0 if t.building else 14) is not None

    def _unit(self, u):
        if u.cool > 0:
            u.cool -= 1
        o = u.order
        do = o["do"]
        if do in ("gather", "build", "repair", "board", "unload"):
            return getattr(self, "_" + do)(u, o)
        if do == "attack":
            t = self.things.get(o["target"])
            if t is None or not self._fight(u, t):
                u.order, u.post = {"do": "idle"}, (u.x, u.y)
            return
        fights = self.stat(u, "damage") and u.spec.get("role") != "worker"
        if u.engage:
            t = self.things.get(u.engage)
            sight = int(self.stat(u, "sight")) + 2
            if t is None or (do != "hold" and self.dist2(u, t) > (sight * FP) ** 2):
                u.engage = 0
            elif not self._fight(u, t, chase=do != "hold"):
                u.engage = 0
            else:
                return
        if fights and do in ("idle", "hold", "amove", "patrol") and (self.tick + u.id) % 3 == 0:
            t = self.acquire(u, self.stat(u, "range") if do == "hold" else self.stat(u, "sight"))
            if t is not None:
                u.engage = t.id
                self._fight(u, t, chase=do != "hold")
                return
        if do in ("move", "amove", "patrol"):
            tx, ty = o["to"]
            got = self.advance(u, ("at", tx, ty), o.get("near", 0))
            if do == "patrol" and got:
                o["to"], o["back"] = o["back"], o["to"]      # and back again
            elif got or got is None:
                u.order, u.post = {"do": "idle"}, (u.x, u.y)
        elif do == "idle" and u.post and (abs(u.x - u.post[0]) > FP or abs(u.y - u.post[1]) > FP):
            if self.advance(u, ("at", u.post[0] // FP, u.post[1] // FP), 10) in (True, None):
                u.post = (u.x, u.y)

    def _idle(self, u):
        u.order = {"do": "idle"}
        u.post = (u.x, u.y)

    def _gather(self, u, o):
        side = self.sides[u.side]
        if o["phase"] == "go":
            cx, cy = o["at"]
            i = cy * self.W + cx
            kind = self.terrain[i] if self.inside(cx, cy) else None
            if kind not in MINED:
                more = self.nearest_crystal(cx, cy, 10, kind=o.get("kind", "crystal"))
                if more is None:
                    return self._idle(u)
                o["at"] = more
                return
            o["kind"] = kind
            got = self.advance(u, ("by", cx, cy, 1, 1))
            if got is None:
                o["at"] = self.nearest_crystal(cx, cy, 10, skip=(cx, cy), kind=kind) or o["at"]
                if o["at"] == (cx, cy):
                    self._idle(u)
                return
            if got:
                o["phase"], o["t"] = "mine", ticks(u.spec["gather"], self.rate)
        elif o["phase"] == "mine":
            o["t"] -= 1
            if o["t"] > 0:
                return
            cx, cy = o["at"]
            i = cy * self.W + cx
            left = self.amount.get(i, 0)
            take = min(int(self.stat(u, "carry")) or 1, left)
            if take:
                self.amount[i] = left - take
                u.carry, u.load = u.carry + take, self.terrain[i]
                if self.amount[i] <= 0:
                    del self.amount[i]
                    self.terrain[i] = "ground"
                    self.version += 1
            o["phase"] = "back" if u.carry else "go"
        else:
            drop = self.dropoff(u)
            if drop is None:
                return self._idle(u)
            got = self.advance(u, ("by", drop.tx, drop.ty, drop.w, drop.h))
            if got:
                if u.load == "gas":
                    side.gas += u.carry
                else:
                    side.credits += u.carry
                u.carry = 0
                o["phase"] = "go"
            elif got is None:
                self._idle(u)

    def nearest_crystal(self, cx, cy, r, skip=None, kind="crystal"):
        """The nearest tile of crystal (or ``kind``) within ``r`` of a tile."""
        best, bd = None, INF
        for i in self.amount:
            if self.terrain[i] != kind:
                continue
            x, y = i % self.W, i // self.W
            d = (x - cx) ** 2 + (y - cy) ** 2
            if d <= r * r and (x, y) != skip and (d < bd or (d == bd and i < best[1] * self.W + best[0])):
                best, bd = (x, y), d
        return best

    def dropoff(self, u):
        best, bd = None, INF
        for t in self.things.values():
            if t.building and t.side == u.side and t.done and t.spec.get("dropoff"):
                d = self.dist2(u, t)
                if d < bd:
                    best, bd = t, d
        return best

    def _build(self, u, o):
        spec = self.kinds[o["kind"]]
        tx, ty = o["at"]
        b = self.things.get(o.get("id")) if o.get("id") else None
        if o.get("id") and b is None:
            return self._idle(u)                         # it was destroyed
        if b is None and o.get("wait"):
            lead = self.things.get(o["wait"])
            if lead is not None and lead.order.get("do") == "build" and lead.order.get("id"):
                o["id"], o["wait"] = lead.order["id"], None
            elif lead is None or lead.order.get("do") != "build":
                self._idle(u)
            else:
                self.advance(u, ("by", tx, ty, spec["size"][0], spec["size"][1]))
            return
        got = self.advance(u, ("by", tx, ty, spec["size"][0], spec["size"][1]))
        if got is None:
            if o.get("paid"):
                self.pay(u.side, spec, -1)
            return self._idle(u)
        if not got:
            return
        if b is None:
            if not self.fits(o["kind"], tx, ty):
                if o.get("paid"):
                    self.pay(u.side, spec, -1)
                self.tell(u.side, "Something stands in the way: the %s is not begun." % spec["name"].lower())
                return self._idle(u)
            b = self.add(o["kind"], u.side, tx, ty, done=False)
            o["id"], o["paid"] = b.id, 0
            for t in self.things.values():                # anyone standing there steps out
                if not t.building and not t.air and not t.inside and tx <= t.x // FP < tx + b.w \
                        and ty <= t.y // FP < ty + b.h:
                    out = self.free_round(t.x // FP, t.y // FP, 1)
                    if out:
                        t.x, t.y = out[0][0] * FP + FP // 2, out[0][1] * FP + FP // 2
        if b.done:
            return self._idle(u)
        total = ticks(spec["time"], self.rate)
        b.built += 1
        b.hp = min(b.max, b.hp + b.max * b.built // total - b.max * (b.built - 1) // total)
        if b.built >= total:
            b.done = True
            if b.side == self.player:
                self.say("%s ready." % spec["name"], "good")
            self._idle(u)

    def _repair(self, u, o):
        """Mend a building of its side: a tenth of its hit points every few seconds, for crystal (half its cost
        for the whole of it)."""
        b = self.things.get(o["id"])
        if b is None or b.hp >= b.max:
            return self._idle(u)
        got = self.advance(u, ("by", b.tx, b.ty, b.w, b.h))
        if got is None:
            return self._idle(u)
        if not got:
            return
        side = self.sides[u.side]
        step = max(1, b.max // ticks(b.spec["time"], self.rate))
        per = max(1, 2 * b.max // max(1, int(b.spec.get("cost") or 1)))   # hit points a crystal buys
        o["hp"] += step
        while o["hp"] >= per:
            if side.credits <= 0:
                self.tell(u.side, "No crystal left to repair with.")
                return self._idle(u)
            side.credits -= 1
            o["hp"] -= per
        b.hp = min(b.max, b.hp + step)

    def _board(self, u, o):
        t = self.things.get(o["id"])
        if t is None or len(t.cargo) >= int(t.spec.get("carries") or 0):
            return self._idle(u)
        if self.dist2(u, t) <= (FP * 3 // 2) ** 2:
            u.inside, u.engage = t.id, 0
            t.cargo.append(u.id)
            u.order = {"do": "idle"}
            return
        if self.dist2(u, t) <= (3 * FP) ** 2 and self.clear_line(u, t.x, t.y):
            self.toward(u, t.x, t.y)                        # the last steps, straight in
        elif self.advance(u, ("at", t.x // FP, t.y // FP), 14) is None and not t.air:
            self._idle(u)

    def _unload(self, u, o):
        x, y = o["to"]
        if not u.cargo:
            return self._idle(u)
        got = self.advance(u, ("at", x, y), 14 if not u.air else 0)
        if got is None:
            return self._idle(u)
        if not got:
            return
        here = (u.x // FP, u.y // FP)
        spots = self.free_round(here[0], here[1], len(u.cargo), rmax=4)
        while u.cargo and spots:
            p = self.things.get(u.cargo.pop(0))
            sx, sy = spots.pop(0)
            if p is not None:
                p.inside = 0
                p.x, p.y = sx * FP + FP // 2, sy * FP + FP // 2
                self._idle(p)
        if u.cargo:
            self.tell(u.side, "No room to set them all down here.")
        self._idle(u)

    def _building(self, b):
        if not b.done:
            return
        if b.cool > 0:
            b.cool -= 1
        if self.stat(b, "damage") and (self.tick + b.id) % 2 == 0:
            t = self.things.get(b.engage)
            if t is None or t.inside or not self.in_range(b, t, self.stat(b, "range")):
                t = self.acquire(b, self.stat(b, "range"))
                b.engage = t.id if t else 0
            if t is not None:
                self._fire(b, t)
        if not b.queue:
            return
        item = b.queue[0]
        spec = self.upgrades[item[3:]] if item.startswith("up:") else self.kinds[item]
        b.progress += 1
        if b.progress < ticks(spec["time"], self.rate):
            return
        if item.startswith("up:"):
            b.queue.pop(0)
            b.progress = 0
            self._upgraded(b.side, item[3:])
            return
        kind = item
        rx, ry = b.rally or (b.tx + b.w // 2, b.ty + b.h)
        spots = sorted(self.goals(("by", b.tx, b.ty, b.w, b.h)),
                       key=lambda i: ((i % self.W - rx) ** 2 + (i // self.W - ry) ** 2, i))
        spot = next((i for i in spots if not self.unit_on(i % self.W, i // self.W)), spots[0] if spots else None)
        if spot is None:
            return                                         # nowhere to stand: it waits
        b.queue.pop(0)
        b.progress = 0
        u = self.add(kind, b.side, (spot % self.W) * FP + FP // 2, (spot // self.W) * FP + FP // 2)
        if b.rally:
            rx, ry = b.rally
            if u.spec.get("role") == "worker" and self.inside(rx, ry) and self.terrain[ry * self.W + rx] in MINED:
                u.order = {"do": "gather", "at": b.rally, "phase": "go", "t": 0}
            else:
                u.order = {"do": "amove", "to": b.rally, "near": 10}

    def _upgraded(self, side, uid):
        up = self.upgrades[uid]
        self.sides[side].upgrades.append(uid)
        if up.get("hp"):                                  # those there already get it too
            for t in self.things.values():
                if t.side == side and self.applies(up, t):
                    t.max += int(up["hp"])
                    t.hp += int(up["hp"])
        if side == self.player:
            self.say("%s upgraded." % up["name"], "good")

    def _apart(self):
        """Units on one tile step apart a little (they never block each other); fliers among fliers."""
        by = {}
        for t in self.things.values():
            if not t.building and not t.inside:
                by.setdefault((t.x // FP, t.y // FP, t.air), []).append(t)
        gap = FP * 3 // 8
        for key, us in by.items():
            if len(us) < 2:
                continue
            us.sort(key=lambda t: t.id)
            for n, a in enumerate(us):
                for b in us[n + 1:]:
                    dx, dy = b.x - a.x, b.y - a.y
                    if abs(dx) + abs(dy) >= gap:
                        continue
                    if dx == 0 and dy == 0:
                        dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[(a.id + b.id) % 4]
                    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
                    for t, k in ((a, -1), (b, 1)):
                        nx, ny = t.x + k * sx * 12, t.y + k * sy * 12
                        if self.inside(nx // FP, ny // FP) and (t.air or self.walkable((ny // FP) * self.W + nx // FP)):
                            t.x, t.y = nx, ny

    def see(self):
        """What the player's side sees now, and has seen."""
        if self.player is None:
            return
        vis = bytearray(self.W * self.H)
        exp = self.explored[self.player]
        W, H = self.W, self.H
        for t in self.things.values():
            if t.side != self.player or t.inside:
                continue
            r = int(self.stat(t, "sight")) + (max(t.w, t.h) // 2 if t.building else 0)
            cx, cy = t.x // FP, t.y // FP
            for y in range(max(0, cy - r), min(H, cy + r + 1)):
                dy = y - cy
                span = math.isqrt(max(0, r * r - dy * dy))
                x0, x1 = max(0, cx - span), min(W - 1, cx + span)
                vis[y * W + x0: y * W + x1 + 1] = b"\x01" * (x1 - x0 + 1)
        for i in range(W * H):
            if vis[i]:
                exp[i] = 1
        self.visible = vis

    def seen(self, t):
        """Whether the player sees ``t`` now."""
        if self.player is None or t.side == self.player:
            return True
        if t.building:
            return any(self.visible[y * self.W + x] for y in range(t.ty, t.ty + t.h) for x in range(t.tx, t.tx + t.w)
                       if self.inside(x, y))
        return self.inside(t.x // FP, t.y // FP) and bool(self.visible[(t.y // FP) * self.W + t.x // FP])

    # ---- what is kept ------------------------------------------------------ #
    def state_hash(self):
        parts = (self.tick, self.result, [s.key() for s in self.sides], [t.key() for t in self.things.values()],
                 sorted(self.crystal.items()), self.next_id, [bytes(e) for e in self.explored])
        return hashlib.sha1(repr(parts).encode()).hexdigest()[:16]

    def stats(self):
        mine = [t for t in self.things.values() if t.side == self.player]
        return {"result": self.result, "seconds": round(self.tick / float(self.rate), 1),
                "units": sum(1 for t in mine if not t.building), "buildings": sum(1 for t in mine if t.building),
                "credits": self.sides[self.player].credits if self.player is not None else 0}

    def units_of(self, side, role=None):
        return [t for t in self.things.values() if t.side == side and not t.building
                and (role is None or t.spec.get("role") == role)]

    def buildings_of(self, side, role=None):
        return [t for t in self.things.values() if t.side == side and t.building
                and (role is None or t.spec.get("role") == role)]


def make(data, sid, rate=RATE):
    spec = (getattr(data, "skirmishes", None) or {}).get(sid)
    if not isinstance(spec, dict):
        raise KeyError("no skirmish '%s'" % sid)
    return World(spec, sid, data, rate)


def replay(world, journal, until=None):
    """Play orders back: ``[[tick, side, order]]``, each given to the world just before its tick."""
    by = {}
    for t, side, o in journal:
        by.setdefault(int(t), []).append((side, o))
    end = until if until is not None else (max(by) if by else 0)
    while world.tick < end and not world.over:
        for side, o in by.get(world.tick + 1, ()):
            world.order(side, o)
        world.step()
    return world


# --------------------------------------------------------------------------- #
# The computer player
# --------------------------------------------------------------------------- #
def place_near(w, kind, side, cx, cy, rmin=3, rmax=10):
    """A place for a building near ``cx, cy``, a tile clear all round it (rings outward, in a fixed order)."""
    sw, sh = w.kinds[kind]["size"]
    for r in range(rmin, rmax + 1):
        ring = [(cx + dx, cy + dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1) if max(abs(dx), abs(dy)) == r]
        ring.sort(key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p[1], p[0]))
        for x, y in ring:
            if w.fits(kind, x, y) and all(
                    not w.inside(xx, yy) or (not w.block[yy * w.W + xx] and w.terrain[yy * w.W + xx] != "crystal")
                    for yy in range(y - 1, y + sh + 1) for xx in range(x - 1, x + sw + 1)):
                return x, y
    return None


def plan(w, s):
    """The computer's decisions for side ``s``: workers to the crystal (and some to gas), more workers, the
    buildings in turn, upgrades with what is spare, an army in its mix, and an attack when the army is big
    enough (bigger each time)."""
    ai = s.ai
    hq = next((b for b in w.buildings_of(s.i, "hq") if b.done), None)
    workers = w.units_of(s.i, "worker")
    army = [u for u in w.units_of(s.i) if u.spec.get("role") not in ("worker", "transport") and not u.inside]
    base = (hq.tx + hq.w // 2, hq.ty + hq.h // 2) if hq else s.start
    if base is None:
        return
    have = {}
    for b in w.buildings_of(s.i):
        have[b.spec.get("role")] = have.get(b.spec.get("role"), 0) + 1
    on_gas = [u for u in workers if u.order["do"] == "gather" and u.order.get("kind") == "gas"]
    want_gas = int(ai.get("gas", 2)) if have.get("barracks") and s.gas < 250 else 0
    if s.gas > 400 and on_gas:                            # plenty: one back to the crystal
        c = w.nearest_crystal(base[0], base[1], 14) or w.nearest_crystal(base[0], base[1], 60)
        if c:
            w.order(s.i, {"do": "gather", "units": [on_gas[-1].id], "at": list(c)})
    for u in workers:
        if u.order["do"] == "idle":
            c = None
            if len(on_gas) < want_gas:
                c = w.nearest_crystal(base[0], base[1], 16, kind="gas")
                if c:
                    on_gas.append(u)
            c = c or w.nearest_crystal(base[0], base[1], 14) or w.nearest_crystal(u.x // FP, u.y // FP, 60)
            if c:
                w.order(s.i, {"do": "gather", "units": [u.id], "at": list(c)})
    if hq and len(workers) + len(hq.queue) < int(ai["workers"]) and len(hq.queue) < 1:
        k = w.of_role(s, "worker")
        if k and w.afford(s.i, w.kinds[k]):
            w.order(s.i, {"do": "train", "building": hq.id, "kind": k})
    building = any(u.order["do"] == "build" for u in workers)
    mix = ai.get("mix") or {}
    want = [("barracks", 1), ("tower", int(ai["towers"])), ("factory", 1 if len(army) >= 4 else 0),
            ("airfield", 1 if mix.get("air") and len(army) >= 6 else 0), ("barracks", 2 if s.credits > 500 else 1)]
    if not building and workers and len(workers) >= 3:
        for role, n in want:
            k = w.of_role(s, role)
            if not k or have.get(role, 0) >= n:
                continue
            spec = w.kinds[k]
            if not w.has(s.i, spec.get("needs")):
                continue
            if not w.afford(s.i, spec):
                break
            at = place_near(w, k, s.i, base[0], base[1], 2 if role == "tower" else 3)
            if at:
                u = min((u for u in workers if u.carry == 0), key=lambda u: u.id, default=workers[0])
                w.order(s.i, {"do": "build", "units": [u.id], "kind": k, "at": list(at)})
            break
    count = {}
    for u in army:
        count[u.spec.get("role")] = count.get(u.spec.get("role"), 0) + 1
    for b in w.buildings_of(s.i):
        if not b.done or len(b.queue) >= 1:
            continue
        ups = [u for u in w.researchable(b) if w.has(s.i, w.upgrades[u].get("needs"))] if ai.get("research") else []
        if ups and s.credits > 350 + int(w.upgrades[ups[0]].get("cost") or 0) and w.afford(s.i, w.upgrades[ups[0]]):
            w.order(s.i, {"do": "research", "building": b.id, "upgrade": ups[0]})
            continue
        if b.spec.get("role") == "hq":
            continue
        options = [k for k in b.spec.get("produces", []) if w.allowed(s.i, k) and w.has(s.i, w.kinds[k].get("needs"))
                   and mix.get(w.kinds[k]["role"], 1)]
        if not options:
            continue
        options.sort(key=lambda k: (count.get(w.kinds[k]["role"], 0) / float(mix.get(w.kinds[k]["role"], 1) or 1), k))
        k = options[0]
        if s.credits >= w.kinds[k]["cost"] + (60 if len(workers) < int(ai["workers"]) else 0) \
                and w.afford(s.i, w.kinds[k]):
            w.order(s.i, {"do": "train", "building": b.id, "kind": k})
            count[w.kinds[k]["role"]] = count.get(w.kinds[k]["role"], 0) + 1
    for b in w.buildings_of(s.i):                         # mend what was hurt, when there is peace
        if b.done and b.hp < b.max * 2 // 3 and s.credits > 150:
            idle = [u for u in workers if u.order["do"] in ("idle", "gather") and u.carry == 0]
            if idle and not any(u.order["do"] == "repair" for u in workers):
                w.order(s.i, {"do": "repair", "units": [idle[0].id], "id": b.id})
            break
    near = None
    mine = w.buildings_of(s.i)
    for t in w.things.values():
        if t.side >= 0 and t.side != s.i and not t.building and not t.inside \
                and any(w.dist2(t, b) <= (9 * FP) ** 2 for b in mine):
            near = t
            break
    home = [u for u in army if u.order["do"] in ("idle", "hold")]
    if near is not None and home:
        w.order(s.i, {"do": "amove", "units": [u.id for u in home if w.hits(u, near)] or [u.id for u in home],
                      "to": [near.x // FP, near.y // FP]})
        return
    dry = s.credits < 100 and w.nearest_crystal(base[0], base[1], 30) is None     # nothing more coming
    if (len(home) >= min(s.wave, int(ai.get("most", 14))) or (dry and home)) \
            and w.tick >= ticks(ai["first"], w.rate):
        target = target_for(w, s)
        if target:
            w.order(s.i, {"do": "amove", "units": [u.id for u in home], "to": list(target)})
            s.wave += 2
            s.attacks += 1
            if w.player is not None and s.i != w.player:
                w.say("%s attacks." % s.name, "alert")


def target_for(w, s):
    """Where to attack: beside the nearest building of a side still in (the side of it facing home)."""
    best, bd = None, INF
    me = s.start or (0, 0)
    for t in w.things.values():
        if t.building and t.side >= 0 and t.side != s.i and not w.sides[t.side].out:
            d = (t.tx - me[0]) ** 2 + (t.ty - me[1]) ** 2
            if d < bd:
                best, bd = t, d
    if best is None:
        return None
    spots = w.goals(("by", best.tx, best.ty, best.w, best.h))
    if not spots:
        return best.tx, best.ty
    i = min(spots, key=lambda i: ((i % w.W - me[0]) ** 2 + (i // w.W - me[1]) ** 2, i))
    return i % w.W, i // w.W


# --------------------------------------------------------------------------- #
# The picture and the controls
# --------------------------------------------------------------------------- #
GLYPH = {"ground": ".", "rock": "#", "water": "~", "trees": '"', "crystal": "$", "gas": "&"}
UGLYPH = {"ground": " ", "rock": " ", "water": "≈", "trees": "♣", "crystal": "◆", "gas": "◊"}
PANEL = 26


class UI:
    """The player's view of a skirmish and what the keys and the mouse do: a cursor, a selection, a
    camera, a build menu. The picture is the UI's; the orders it gives go into the world."""

    def __init__(self, world):
        self.w = world
        self.side = world.player if world.player is not None else 0
        hq = next(iter(world.buildings_of(self.side, "hq")), None)
        start = world.sides[self.side].start or (world.W // 2, world.H // 2)
        self.cursor = [hq.tx + hq.w // 2, hq.ty + hq.h] if hq else list(start)
        self.cam = None
        self.view = (40, 20)
        self.selected = []
        self.mode = None                             # None, "box", "menu", ("place", kind), "paused"
        self.anchor = None
        self.repeat = {}
        self.drag = None
        self.paused = False
        self.map_top = 1
        self.groups = {}                             # control groups: a digit -> ids
        self.recalled = (None, -99)
        self.clock = 0

    # -- the selection --
    def chosen(self):
        self.selected = [i for i in self.selected if i in self.w.things]
        return [self.w.things[i] for i in self.selected]

    def select_at(self, x, y):
        t = self.w.at(x, y, self.side)
        self.selected = [t.id] if t else []
        return t

    def select_box(self, a, b):
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        units = [t.id for t in self.w.units_of(self.side) if x0 <= t.x // FP <= x1 and y0 <= t.y // FP <= y1]
        if units:
            self.selected = units
        else:
            self.selected = [t.id for t in self.w.buildings_of(self.side) if x0 <= t.tx + t.w // 2 <= x1
                             and y0 <= t.ty + t.h // 2 <= y1][:1]

    def units(self):
        return [t for t in self.chosen() if not t.building]

    def give(self, order):
        self.w.order(self.side, order)

    def smart(self, x, y):
        """What a click (or Enter) on a tile means for the units chosen: attack an enemy, gather crystal,
        help build, bring crystal home, else go there."""
        units = self.units()
        if not units:
            for b in self.chosen():
                if b.building:
                    self.give({"do": "rally", "units": [b.id], "to": [x, y]})
            return
        ids = [u.id for u in units]
        w = self.w
        t = w.at(x, y)
        workers = [u.id for u in units if u.spec.get("role") == "worker"]
        riders = [u.id for u in units if not u.air and not u.spec.get("carries")]
        if t is not None and w.enemy(units[0], t) and w.seen(t):
            self.give({"do": "attack", "units": ids, "target": t.id})
        elif t is not None and t.side == self.side and t.spec.get("carries") and riders and t.id not in ids:
            self.give({"do": "board", "units": riders, "id": t.id})
        elif workers and t is not None and t.building and t.side == self.side and t.done and t.hp < t.max:
            self.give({"do": "repair", "units": workers, "id": t.id})
        elif workers and w.inside(x, y) and w.terrain[y * w.W + x] in MINED:
            self.give({"do": "gather", "units": workers, "at": [x, y]})
            rest = [i for i in ids if i not in workers]
            if rest:
                self.give({"do": "move", "units": rest, "to": [x, y]})
        elif workers and t is not None and t.building and t.side == self.side and not t.done:
            self.give({"do": "build", "units": workers, "id": t.id})
        elif workers and t is not None and t.building and t.side == self.side and t.spec.get("dropoff"):
            c = w.nearest_crystal(x, y, 12)
            self.give({"do": "gather", "units": workers, "at": list(c) if c else [x, y]})
        else:
            self.give({"do": "move", "units": ids, "to": [x, y]})

    def buildable(self):
        """The kinds the chosen workers may build: ``[(kind, spec)]``."""
        if not any(u.spec.get("role") == "worker" for u in self.units()):
            return []
        return [(k, s) for k, s in self.w.kinds.items() if s["building"] and self.w.allowed(self.side, k)]

    def trainable(self):
        """The chosen building and what it can make: kinds, and upgrades as ``"up:ID"``."""
        b = next((t for t in self.chosen() if t.building), None)
        if b is None or not b.done:
            return None, []
        return b, [k for k in b.spec.get("produces", []) if self.w.allowed(self.side, k)] + \
            ["up:" + u for u in self.w.researchable(b)]

    def move_cursor(self, dx, dy):
        self.cursor[0] = max(0, min(self.w.W - 1, self.cursor[0] + dx))
        self.cursor[1] = max(0, min(self.w.H - 1, self.cursor[1] + dy))

    # -- keys --
    def key(self, k):
        """One key; False when it means nothing here."""
        w = self.w
        x, y = self.cursor
        if self.paused:
            if k == "q":
                w.result = w.over = "quit"
            elif k in ("p", "esc", "enter", "space"):
                self.paused = False
            return True
        if isinstance(self.mode, tuple):
            kind = self.mode[1]
            if k in ("enter", "space"):
                self.give({"do": "build", "units": [u.id for u in self.units()], "kind": kind, "at": [x, y]})
                self.mode = None
            elif k == "esc":
                self.mode = None
            return True
        if self.mode == "menu":
            opts = self.buildable()
            if k.isdigit() and 1 <= int(k) <= len(opts):
                self.mode = ("place", opts[int(k) - 1][0])
            else:
                self.mode = None
            return True
        if self.mode == "group":
            self.mode = None
            if k.isdigit():
                self.groups[k] = list(self.selected)
            return True
        if k.startswith("ctrl-") and k[5:].isdigit():
            self.groups[k[5:]] = list(self.selected)
            return True
        if k == "G":
            self.mode = "group"
            return True
        if k in ("enter", "space"):
            own = w.at(x, y, self.side)
            if self.mode == "box":
                self.select_box(self.anchor, self.cursor)
                self.mode = None
            elif k == "space" or not self.selected or (own is not None and not own.building):
                self.select_at(x, y)                       # Space chooses (and Enter, on a unit of yours)
            else:
                self.smart(x, y)                           # Enter acts
            return True
        if k == "v":
            if self.mode == "box":
                self.select_box(self.anchor, self.cursor)
                self.mode = None
            else:
                self.mode, self.anchor = "box", list(self.cursor)
            return True
        if k == "esc":
            if self.mode:
                self.mode = None
            else:
                self.paused = True
            return True
        if k == "p":
            self.paused = True
            return True
        ids = [u.id for u in self.units()]
        if k in ("a", "m") and ids:
            self.give({"do": "amove" if k == "a" else "move", "units": ids, "to": [x, y]})
        elif k in ("s", "h") and ids:
            self.give({"do": "stop" if k == "s" else "hold", "units": ids})
        elif k == "g" and ids:
            c = w.nearest_crystal(x, y, 12)
            if c:
                self.give({"do": "gather", "units": ids, "at": list(c)})
        elif k == "b":
            if self.buildable():
                self.mode = "menu"
        elif k == "tab":
            idle = [u for u in w.units_of(self.side, "worker") if u.order["do"] == "idle"]
            if idle:
                last = self.selected[0] if self.selected else 0
                u = next((u for u in idle if u.id > last), idle[0])
                self.selected = [u.id]
                self.cursor = [u.x // FP, u.y // FP]
        elif k == "u":
            self.selected = [u.id for u in w.units_of(self.side) if u.spec.get("role") != "worker"]
        elif k == "e":
            kinds = {t.kind for t in self.chosen()}
            self.selected = [t.id for t in w.things.values() if t.side == self.side and t.kind in kinds]
        elif k == "home":
            hq = next(iter(w.buildings_of(self.side, "hq")), None)
            if hq:
                self.cursor = [hq.tx + hq.w // 2, hq.ty + hq.h // 2]
        elif k == "o" and ids:
            self.give({"do": "patrol", "units": ids, "to": [x, y]})
        elif k == "d" and ids:
            self.give({"do": "unload", "units": ids, "to": [x, y]})
        elif k.isdigit():
            b, opts = self.trainable()
            if b is not None and opts:
                if 1 <= int(k) <= len(opts):
                    item = opts[int(k) - 1]
                    if item.startswith("up:"):
                        self.give({"do": "research", "building": b.id, "upgrade": item[3:]})
                    else:
                        self.give({"do": "train", "building": b.id, "kind": item})
            elif self.groups.get(k):
                self.selected = [i for i in self.groups[k] if i in w.things]
                if self.recalled[0] == k and self.clock - self.recalled[1] <= 8 and self.chosen():
                    t = self.chosen()[0]
                    self.cursor = [t.x // FP, t.y // FP]
                self.recalled = (k, self.clock)
        elif k == "c":
            b, _ = self.trainable()
            if b is not None:
                self.give({"do": "cancel", "building": b.id})
        elif k == "r":
            for b in self.chosen():
                if b.building:
                    self.give({"do": "rally", "units": [b.id], "to": [x, y]})
        else:
            return False
        return True

    def mouse(self, name):
        """A mouse report (engine/keys.py names): the left button chooses (drag: a box), the right one
        gives the order a click means."""
        kind, b, cx, cy = name.split(":")
        b, cx, cy = int(b), int(cx), int(cy)
        mx, my = self.view
        if not (0 <= cx < mx and self.map_top <= cy < self.map_top + my):
            return
        cam = self.cam or (0, 0)
        x, y = cam[0] + cx, cam[1] + cy - self.map_top
        if not self.w.inside(x, y):
            return
        self.cursor = [x, y]
        button = b & 3
        if self.paused:
            return
        if kind == "mouse" and button == 0 and not b & 32:
            if isinstance(self.mode, tuple):
                self.key("enter")
            else:
                self.drag = [x, y]
        elif kind == "mouseup" and button == 0 and self.drag is not None:
            if self.drag != [x, y]:
                self.select_box(self.drag, [x, y])
            else:
                self.select_at(x, y)
            self.drag = None
        elif kind == "mouse" and button == 2:
            if isinstance(self.mode, tuple) or self.mode:
                self.mode = None
            else:
                self.smart(x, y)

    def controls(self, c):
        """A tick of keys (engine/realtime.py Controls): the arrows move the cursor, held they run on."""
        self.clock += 1
        for name, kind in getattr(c, "events", ()):
            if name.startswith(("mouse:", "mouseup:")):
                self.mouse(name)
        steps = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        for k, (dx, dy) in steps.items():
            for name, mult in ((k, 1), ("shift-" + k, 5), ("ctrl-" + k, 5)):
                if name in c.pressed:
                    self.move_cursor(dx * mult, dy * mult)
                    self.repeat[name] = 0
                elif name in c.held:
                    self.repeat[name] = self.repeat.get(name, 0) + 1
                    if self.repeat[name] >= 5 and self.repeat[name] % 2 == 0:
                        self.move_cursor(dx * mult, dy * mult)
                else:
                    self.repeat.pop(name, None)
        for k in c.pressed:
            if k in steps or k.startswith(("shift-", "ctrl-", "mouse")):
                continue
            if k in ("ctrl-d", "ctrl-c"):
                self.w.result = self.w.over = self.w.result or "quit"
                continue
            self.key(k)

    # -- the picture --
    def camera(self, mw, mh):
        w = self.w
        cx, cy = self.cam or (self.cursor[0] - mw // 2, self.cursor[1] - mh // 2)
        m = 3
        x, y = self.cursor
        if x < cx + m:
            cx = x - m
        elif x >= cx + mw - m:
            cx = x - mw + m + 1
        if y < cy + m:
            cy = y - m
        elif y >= cy + mh - m:
            cy = y - mh + m + 1
        cx = max(0, min(cx, w.W - mw)) if w.W > mw else -((mw - w.W) // 2)
        cy = max(0, min(cy, w.H - mh)) if w.H > mh else -((mh - w.H) // 2)
        self.cam = (cx, cy)
        self.view = (mw, mh)
        return cx, cy

    def cells(self, mw, mh, color=True, unicode=True):
        """The map: rows of ``(char, fg, bg)``."""
        w, C = self.w, self.w.colors
        cx, cy = self.camera(mw, mh)
        exp = w.explored[self.side] if w.player is not None else None
        vis = w.visible if w.player is not None else None
        glyph = UGLYPH if unicode else GLYPH
        rows = []
        for r in range(mh):
            y = cy + r
            row = []
            for c in range(mw):
                x = cx + c
                if not w.inside(x, y):
                    row.append((" ", None, None))
                    continue
                i = y * w.W + x
                if exp is not None and not exp[i]:
                    row.append((" ", None, C["fog"] if color else None))
                    continue
                lit = vis is None or vis[i]
                t = w.terrain[i]
                base = t if t in ("rock", "water") else "ground"
                bg = C[base] if lit else C[base + "_dim"]
                fg = C.get(t, C["text"])
                if t in MINED:
                    fg = shade(fg, 0.5 + 0.5 * min(1.0, w.amount.get(i, 0) / 400.0))
                if not lit:
                    fg = shade(fg, 0.5)
                ch = glyph.get(t, " ")
                row.append((ch, fg if color else None, bg if color else None))
            rows.append(row)
        sel = set(self.selected)
        for t in sorted(w.things.values(), key=lambda t: (not t.building, t.air, t.id)):
            if t.inside or not w.seen(t):
                continue
            side = w.sides[t.side].color if t.side >= 0 else C["neutral"]
            mine = t.side == self.side
            if t.building:
                for yy in range(t.ty, t.ty + t.h):
                    for xx in range(t.tx, t.tx + t.w):
                        c, r = xx - cx, yy - cy
                        if 0 <= c < mw and 0 <= r < mh:
                            top = xx == t.tx and yy == t.ty
                            if color:
                                ch = t.spec["char"] if top else ("░" if not t.done and unicode else " ")
                                bg = shade(side, 0.45 if t.done else 0.25)
                                if t.id in sel:
                                    bg = shade(side, 0.7)
                                rows[r][c] = (ch, (255, 255, 255), bg)
                            else:
                                ch = t.spec["char"] if top else ("=" if mine else "%")
                                rows[r][c] = (ch if t.done or top else ":", None, None)
                continue
            c, r = t.x // FP - cx, t.y // FP - cy
            if 0 <= c < mw and 0 <= r < mh:
                ch = t.spec["char"]
                if color:
                    bg = C["select"] if t.id in sel else rows[r][c][2]
                    fg = (20, 20, 20) if t.id in sel else side
                    rows[r][c] = (ch, fg, bg)
                else:
                    rows[r][c] = (ch.lower() if mine else ch.upper(), None, None)
        for t in w.things.values():                       # shots of the last moments
            if t.shot and w.tick - t.shot[2] <= 1 and w.seen(t):
                c, r = t.shot[0] // FP - cx, t.shot[1] // FP - cy
                if 0 <= c < mw and 0 <= r < mh:
                    ch, fg, bg = rows[r][c]
                    rows[r][c] = ("*", C["shot"] if color else None, bg)
        if isinstance(self.mode, tuple):
            kind = self.mode[1]
            sw, sh = w.kinds[kind]["size"]
            ok = w.fits(kind, self.cursor[0], self.cursor[1], self.side)
            for yy in range(self.cursor[1], self.cursor[1] + sh):
                for xx in range(self.cursor[0], self.cursor[0] + sw):
                    c, r = xx - cx, yy - cy
                    if 0 <= c < mw and 0 <= r < mh:
                        rows[r][c] = ("+", (0, 0, 0) if color else None,
                                      (C["place_ok"] if ok else C["place_bad"]) if color else None)
        boxes = []
        if self.mode == "box":
            boxes.append((self.anchor, self.cursor))
        if self.drag is not None and self.drag != self.cursor:
            boxes.append((self.drag, self.cursor))
        for a, b in boxes:
            x0, x1 = sorted((a[0], b[0]))
            y0, y1 = sorted((a[1], b[1]))
            for yy in range(y0, y1 + 1):
                for xx in range(x0, x1 + 1):
                    if xx in (x0, x1) or yy in (y0, y1):
                        c, r = xx - cx, yy - cy
                        if 0 <= c < mw and 0 <= r < mh:
                            ch, fg, bg = rows[r][c]
                            rows[r][c] = (ch if ch.strip() else "·", fg, C["select"] if color else None)
        c, r = self.cursor[0] - cx, self.cursor[1] - cy
        if 0 <= c < mw and 0 <= r < mh:
            ch, fg, bg = rows[r][c]
            rows[r][c] = (ch, (0, 0, 0), C["cursor"]) if color else ("X" if not ch.strip() or ch in ".~#" else ch,
                                                                      None, None)
        return rows

    def minimap(self, pw, ph):
        """Rows of half-block cells: the whole map small, the view's frame on it."""
        w, C = self.w, self.w.colors
        px, py = pw, ph * 2
        sx = max(1, -(-w.W // px))
        sy = max(1, -(-w.H // py))
        s = max(sx, sy)
        exp = w.explored[self.side] if w.player is not None else None
        owner = {}
        for t in w.things.values():
            if w.seen(t):
                owner[((t.x // FP) // s, (t.y // FP) // s)] = w.sides[t.side].color if t.side >= 0 else C["neutral"]
        buf = []
        for yy in range(py):
            row = []
            for xx in range(px):
                tx, ty = xx * s, yy * s
                if not w.inside(tx, ty):
                    row.append((0, 0, 0))
                    continue
                i = ty * w.W + tx
                if (xx, yy) in owner:
                    row.append(owner[(xx, yy)])
                elif exp is not None and not exp[i]:
                    row.append((0, 0, 0))
                else:
                    t = w.terrain[i]
                    row.append(C["crystal"] if t == "crystal" else C["gas"] if t == "gas" else
                               C["rock"] if t == "rock" else
                               C["water"] if t == "water" else C["trees"] if t == "trees" else C["ground"])
            buf.append(row)
        if self.cam:
            cx, cy = self.cam
            mw, mh = self.view
            for yy in range(py):
                for xx in range(px):
                    tx, ty = xx * s, yy * s
                    edge_x = tx in (max(0, cx) // s * s, (cx + mw - 1) // s * s)
                    edge_y = ty in (max(0, cy) // s * s, (cy + mh - 1) // s * s)
                    if (edge_x and cy <= ty < cy + mh) or (edge_y and cx <= tx < cx + mw):
                        buf[yy][xx] = (200, 200, 200)
        return [[(None, buf[2 * r][x], buf[2 * r + 1][x]) for x in range(px)] for r in range(ph)]

    def describe(self, x, y):
        w = self.w
        if not w.inside(x, y):
            return ""
        i = y * w.W + x
        if w.player is not None and not w.explored[self.side][i]:
            return "%d,%d: not seen yet" % (x, y)
        t = w.at(x, y)
        if t is not None and w.seen(t):
            who = "yours" if t.side == self.side else (w.sides[t.side].name if t.side >= 0 else "nobody's")
            return "%d,%d: %s (%s) %d/%d" % (x, y, t.spec["name"], who, max(0, t.hp), t.max)
        ter = w.terrain[i]
        if ter in MINED:
            return "%d,%d: %s, %d left" % (x, y, w.names[ter].lower(), w.amount.get(i, 0))
        return "%d,%d: %s" % (x, y, ter)

    def panel(self, height, unicode=True):
        """The lines beside the map: ``[[(text, role)]]``."""
        w = self.w
        s = w.sides[self.side]
        lines = [[(w.name, "title")],
                 [("%s %d  %s %d" % (w.names["crystal"].upper(), s.credits, w.names["gas"].upper(), s.gas), "ammo")],
                 [("UNITS %d/%d" % (len(w.units_of(self.side)), w.limit), "text")]]
        if w.goal == "survive" and w.time_ticks:
            left = max(0, w.time_ticks - w.tick) // w.rate
            lines.append([("HOLD %d:%02d" % (left // 60, left % 60), "alert")])
        else:
            sec = w.tick // w.rate
            lines.append([("TIME %d:%02d" % (sec // 60, sec % 60), "info")])
        lines.append([("", "text")])
        chosen = self.chosen()
        if self.mode == "group":
            lines.append([("Group: a digit to keep", "title")])
        elif self.mode == "menu":
            lines.append([("Build:", "title")])
            for n, (k, spec) in enumerate(self.buildable(), 1):
                lines.append([("%d %s %s" % (n, spec["name"], w.price(spec)), "text" if w.has(self.side, spec.get(
                    "needs")) else "dim")])
            lines.append([("Esc: none", "dim")])
        elif isinstance(self.mode, tuple):
            spec = w.kinds[self.mode[1]]
            lines += [[("Place: %s" % spec["name"], "title")], [("Enter: here, Esc: not", "dim")]]
        elif not chosen:
            lines.append([("Nothing chosen.", "dim")])
        elif len(chosen) == 1:
            t = chosen[0]
            lines.append([(t.spec["name"], "title")])
            lines.append([(bar(t.hp, t.max, 12, unicode) + " %d/%d" % (max(0, t.hp), t.max), "hurt")])
            if t.building:
                if not t.done:
                    total = ticks(t.spec["time"], w.rate)
                    lines.append([("Building %d%%" % (100 * t.built // total), "info")])
                else:
                    b, opts = self.trainable()
                    def spec_of(item):
                        return w.upgrades[item[3:]] if item.startswith("up:") else w.kinds[item]
                    if t.queue:
                        total = ticks(spec_of(t.queue[0])["time"], w.rate)
                        lines.append([("Making %s %d%%" % (spec_of(t.queue[0])["name"], 100 * t.progress // total),
                                       "info")])
                        if len(t.queue) > 1:
                            lines.append([("then " + ", ".join(spec_of(k)["name"] for k in t.queue[1:]), "dim")])
                    for n, k in enumerate(opts, 1):
                        sp = spec_of(k)
                        ok = w.has(self.side, sp.get("needs"))
                        lines.append([("%d %s%s %s" % (n, "+" if k.startswith("up:") else "", sp["name"], w.price(sp)),
                                       "text" if ok else "dim")])
                    if opts:
                        lines.append([("c cancel  r rally", "dim")])
            else:
                lines.append([(doing(t), "info")])
                if t.carry:
                    lines.append([("carries %d %s" % (t.carry, w.names[t.load].lower()), "ammo")])
                if t.spec.get("carries"):
                    lines.append([("aboard %d/%d" % (len(t.cargo), t.spec["carries"]), "text")])
        else:
            count = {}
            for t in chosen:
                count[t.spec["name"]] = count.get(t.spec["name"], 0) + 1
            lines.append([("%d chosen" % len(chosen), "title")])
            for name, n in sorted(count.items()):
                lines.append([("%d %s" % (n, name), "text")])
        lines.append([("", "text")])
        if self.groups:
            lines.append([("groups " + " ".join(sorted(k for k, v in self.groups.items() if v)), "dim")])
        help_ = ["arrows cursor", "Space choose  Enter go", "v box   Tab idle worker", "a attack  m move",
                 "s stop  h hold  g gather", "o patrol  d unload", "b build  u army  e alike", "G+digit group",
                 "p pause"]
        lines += [[(h, "dim")] for h in help_]
        return lines[:height]


def bar(v, top, n, unicode=True):
    full = max(0, min(n, (max(0, v) * n + top - 1) // max(1, top)))
    return ("█" * full + "░" * (n - full)) if unicode else ("#" * full + "-" * (n - full))


def doing(t):
    do = t.order["do"]
    return {"idle": "idle", "hold": "holding", "move": "moving", "amove": "attacking (on the way)",
            "patrol": "patrolling", "repair": "repairing", "board": "boarding", "unload": "to set them down",
            "attack": "attacking", "build": "building", "gather": {"go": "to the crystal", "mine": "mining",
                                                                  "back": "carrying it home"}.get(
                t.order.get("phase"), "gathering")}.get(do, do)


class Runner:
    """A skirmish on the terminal for :class:`engine.realtime.Loop`: the keys a tick at a time (20 a
    second), the world stepped every other tick (10 a second), the picture drawn."""

    def __init__(self, world, screen=None, audio=None, rate=20):
        self.world, self.screen, self.audio = world, screen, audio
        self.ui = UI(world)
        self.every = max(1, rate // world.rate)
        self.ticks = 0
        self.heard = 0

    @property
    def over(self):
        return self.world.over

    def pause_key(self, name):
        """Whether this key, pressed now, stops the battle for the game's menu (the loop asks): P, and
        Esc when there is nothing for it to call off."""
        ui = self.ui
        if not self.__dict__.get("menu_on", False) or ui.paused or self.world.over:
            return False
        return name == "p" or (name == "esc" and not ui.mode)

    def backdrop(self):
        scr = self.screen
        W, H = scr.size()
        return self.rows(W, H, scr.paint.depth, scr.unicode and scr.glyphs.get("half") == "▀")

    def step(self, c):
        self.ui.controls(c)
        self.ticks += 1
        if not self.ui.paused and self.ticks % self.every == 0:
            self.world.step()
            if self.audio is not None:
                for t, text, role in self.world.messages[self.heard:]:
                    try:
                        self.audio.sfx({"hurt": "hurt", "good": "pickup", "alert": "locked"}.get(role, "tick"))
                    except Exception:
                        pass
                    break
            self.heard = len(self.world.messages)

    def rows(self, W, H, depth=3, unicode=True):
        from .frame import Painter
        paint = self.screen.paint if self.screen is not None else Painter(depth)
        ui, w = self.ui, self.world
        panel = PANEL if W >= 64 else 0
        mw, mh = W - panel - (1 if panel else 0), max(4, H - 3)
        ui.map_top = 1
        cells = ui.cells(mw, mh, color=bool(depth), unicode=unicode)
        s = w.sides[ui.side]
        hud = [(w.name + "   ", "title"), ("%s %d   " % (w.names["crystal"].upper(), s.credits), "ammo"),
               ("%s %d   " % (w.names["gas"].upper(), s.gas), "ammo"),
               ("UNITS %d/%d" % (len(w.units_of(ui.side)), w.limit), "text")]
        rows = [paint.text(hud, W)]
        side_lines = ui.panel(mh, unicode) if panel else []
        mini = []
        if panel and depth and unicode:
            mini = ui.minimap(PANEL - 2, 6)
            side_lines = side_lines[:5] + [None] * 7 + side_lines[5:]
        for r in range(mh):
            row = list(cells[r])
            if panel:
                row.append((" ", None, None))
                line = side_lines[r] if r < len(side_lines) else [("", "text")]
                if line is None:
                    k = r - 5
                    if 0 <= k < len(mini):
                        row += [(" ", None, None)] + mini[k] + [(" ", None, None)]
                    else:
                        row += [(" ", None, None)] * PANEL
                    rows.append(row)
                    continue
                text = "".join(t for t, _ in line)[:PANEL - 1]
                role = line[0][1] if line else "text"
                fg = paint_role(paint, role) if depth else None
                row += [(ch, fg, None) for ch in (" " + text).ljust(PANEL)[:PANEL]]
            rows.append(row)
        banner = self.banner()
        if banner:
            top = 1 + max(0, (mh - len(banner)) // 2)
            for i, (text, role) in enumerate(banner):
                if top + i < len(rows):
                    pad = max(0, (W - len(text)) // 2)
                    rows[top + i] = paint.text([(" " * pad + text + " " * max(0, W - pad - len(text)), role)], W)
        return rows

    def banner(self):
        w, ui = self.world, self.ui
        if w.result == "won":
            return [("VICTORY", "good"), ("%d:%02d" % (w.tick // w.rate // 60, w.tick // w.rate % 60), "text")]
        if w.result == "lost":
            return [("DEFEAT", "hurt")]
        if ui.paused:
            return [("PAUSED", "title"), ("P, Esc or Enter goes on; Q leaves.", "dim")]
        return []

    def status(self):
        w = self.world
        for tick, text, role in reversed(w.messages):
            if w.tick - tick <= w.rate * 4:
                return text
        return self.ui.describe(*self.ui.cursor)

    def draw(self):
        if self.screen is None:
            return
        scr = self.screen
        W, H = scr.size()
        unicode = scr.unicode and scr.glyphs.get("half") == "▀"
        rows = self.rows(W, H, scr.paint.depth, unicode)
        help_ = "arrows/mouse  Space/click choose  Enter/right-click go  v box  b build  1-5 train  " + \
            ("p menu" if self.__dict__.get("menu_on") else "p pause")
        scr.frame(rows, status=self.status(), footer=scr.paint.text([(help_, "dim")], W))


def paint_role(paint, role):
    """The colour a theme gives a role, as an (r, g, b), or None."""
    try:
        c = paint.theme.get(role) if hasattr(paint, "theme") else None
    except Exception:
        c = None
    return colour(c, (200, 200, 200)) if c else {"title": (240, 220, 140), "ammo": (240, 240, 120),
                                                  "hurt": (240, 110, 110), "info": (120, 200, 240),
                                                  "dim": (130, 130, 130), "good": (120, 230, 120),
                                                  "alert": (255, 170, 80)}.get(role, (210, 210, 210))


HELP_LINES = [("Arrows, mouse", "The cursor"), ("Spc, click", "Choose"), ("Enter, right click", "Go there, attack"),
              ("V", "A box round many"), ("B", "Build"), ("1 to 5", "Train"), ("A / S / H", "Attack on the way, stop, hold")]


def play_frame(world, term, audio=None, keys=None, clock=None, game=None):
    """Play a skirmish on the terminal's screen (keys, and the mouse where the terminal reports it).
    ``game``: the game round it - P, and Esc with nothing to call off, then open its menu, time standing."""
    from . import menu as menus
    from .frame import Screen
    from .keys import KeyReader
    from .realtime import Loop
    screen = Screen(term, None, {}, term.animate)
    runner = Runner(world, screen, audio)
    opened = None
    if game is not None:
        runner.menu_on = True

        def opened(loop):
            if menus.paused(game, screen, loop.keys, runner.backdrop, title=getattr(world, "name", None),
                            help_lines=HELP_LINES, leave="Leave the battle",
                            sure="Leave the battle? It ends as it stands.",
                            after="\x1b[?1002h\x1b[?1006h") == "quit":
                world.result = world.over = world.result or "quit"
    loop = Loop(runner, keys or KeyReader(), 20, clock=clock, menu=opened)
    screen.start()
    out = getattr(term, "out", None)
    try:
        if out is not None:
            out.write("\x1b[?1002h\x1b[?1006h")           # mouse: buttons, drags; SGR numbers
            out.flush()
        loop.run()
    except KeyboardInterrupt:
        world.result = world.over = world.result or "quit"
    finally:
        if out is not None:
            out.write("\x1b[?1002l\x1b[?1006l")
            out.flush()
        screen.stop()
    return loop.recorder


# --------------------------------------------------------------------------- #
# A line at a time
# --------------------------------------------------------------------------- #
TEXT_HELP = ("Commands (';' between them): select all|army|workers|idle|KIND|X,Y [X2,Y2]; move X,Y; "
             "attack X,Y; patrol X,Y; gather [X,Y]; build KIND X,Y; repair X,Y; train KIND [N]; research NAME; "
             "board X,Y; unload X,Y; stop; hold; rally X,Y; group N; recall N; "
             "wait [SECONDS] (an empty line waits 5); look [X,Y]; map; status; quit.")


def text_map(world, ui, cx=None, cy=None, cols=48, rows=18):
    """The map round a tile as plain lines, with the columns' and rows' numbers."""
    if cx is not None:
        ui.cursor = [max(0, min(world.W - 1, cx)), max(0, min(world.H - 1, cy))]
        ui.cam = None
    cells = ui.cells(min(cols, world.W), min(rows, world.H), color=False, unicode=False)
    x0, y0 = ui.cam
    head = "    " + "".join(str((x0 + c) // 10 % 10) if (x0 + c) % 10 == 0 else " " for c in range(len(cells[0])))
    head2 = "    " + "".join(str((x0 + c) % 10) for c in range(len(cells[0])))
    out = [head, head2]
    for r, row in enumerate(cells):
        out.append("%3d " % (y0 + r) + "".join(ch for ch, _, _ in row))
    return out


def status_lines(world, ui):
    s = world.sides[ui.side]
    sec = world.tick // world.rate
    out = ["%s - %d:%02d - %s %d - %s %d - units %d/%d" % (
        world.name, sec // 60, sec % 60, world.names["crystal"].lower(), s.credits, world.names["gas"].lower(),
        s.gas, len(world.units_of(ui.side)), world.limit)]
    if s.upgrades:
        out.append("Upgrades: " + ", ".join(world.upgrades[u]["name"] for u in s.upgrades))
    count = {}
    for t in world.things.values():
        if t.side == ui.side:
            key = t.spec["name"] + ("" if t.done else " (building)")
            count[key] = count.get(key, 0) + 1
    out.append("Yours: " + ", ".join("%d %s" % (n, k) for k, n in sorted(count.items())))
    for o in world.sides:
        if o.i != ui.side and o.control != "none":
            seen = [t for t in world.things.values() if t.side == o.i and world.seen(t)]
            out.append("%s: %s%s" % (o.name, "out" if o.out else "in", (", %d seen" % len(seen)) if seen else ""))
    chosen = ui.chosen()
    if chosen:
        out.append("Chosen: " + ", ".join("%s %d,%d %s" % (t.spec["name"], t.x // FP, t.y // FP,
                                                           doing(t) if not t.building else "")
                                          for t in chosen[:6]) + (" ..." if len(chosen) > 6 else ""))
    return out


def coords(word):
    try:
        x, y = word.split(",")
        return int(x), int(y)
    except ValueError:
        return None


def command(world, ui, line):
    """One typed command; returns ``(seconds to wait, what to say)``."""
    words = line.replace(";", " ; ").split()
    if not words:
        return 5.0, []
    verb, rest = words[0].lower(), words[1:]
    w = world
    say = []
    if verb in ("q", "quit"):
        w.result = w.over = "quit"
    elif verb == "help" or verb == "?":
        say.append(TEXT_HELP)
    elif verb == "wait":
        try:
            return max(0.1, min(120.0, float(rest[0]))) if rest else 5.0, []
        except ValueError:
            say.append("wait SECONDS")
    elif verb == "select":
        what = rest[0].lower() if rest else "all"
        mine = [t for t in w.things.values() if t.side == ui.side]
        if coords(what):
            a = coords(what)
            b = coords(rest[1]) if len(rest) > 1 else None
            if b:
                ui.select_box(a, b)
            else:
                ui.select_at(*a)
        elif what == "all":
            ui.selected = [t.id for t in mine if not t.building]
        elif what == "army":
            ui.selected = [t.id for t in mine if not t.building and t.spec.get("role") != "worker"]
        elif what in ("workers", "worker"):
            ui.selected = [t.id for t in mine if t.spec.get("role") == "worker"]
        elif what == "idle":
            ui.selected = [t.id for t in mine if not t.building and t.order["do"] == "idle"]
        else:
            ui.selected = [t.id for t in mine if what in (t.kind, t.spec["name"].lower(), t.spec.get("role"))]
        say.append("%d chosen." % len(ui.chosen()))
    elif verb in ("group", "recall") and rest and rest[0].isdigit():
        if verb == "group":
            ui.groups[rest[0]] = list(ui.selected)
        else:
            ui.selected = [i for i in ui.groups.get(rest[0], []) if i in w.things]
        say.append("%d chosen." % len(ui.chosen()))
    elif verb == "research" and rest:
        uid = next((u for u, up in w.upgrades.items() if rest[0].lower() in (u, up["name"].lower())), None)
        b = next((t for t in w.buildings_of(ui.side) if t.done and uid in w.researchable(t)), None)
        if uid is None or b is None:
            say.append("Nothing of yours can make that upgrade now.")
        else:
            ui.give({"do": "research", "building": b.id, "upgrade": uid})
    elif verb in ("board", "unload", "repair") and rest and coords(rest[0]):
        x, y = coords(rest[0])
        t = w.at(x, y, ui.side)
        ids = [u.id for u in ui.units()]
        if verb == "unload":
            ui.give({"do": "unload", "units": ids, "to": [x, y]})
        elif t is None:
            say.append("Nothing of yours there.")
        else:
            ui.give({"do": verb, "units": ids, "id": t.id})
    elif verb in ("move", "attack", "rally", "patrol") and rest and coords(rest[0]):
        x, y = coords(rest[0])
        ids = [t.id for t in ui.units()]
        t = w.at(x, y)
        if verb == "patrol":
            ui.give({"do": "patrol", "units": ids, "to": [x, y]})
        elif verb == "rally":
            ui.give({"do": "rally", "units": [b.id for b in ui.chosen() if b.building], "to": [x, y]})
        elif verb == "attack" and t is not None and ui.units() and w.enemy(ui.units()[0], t) and w.seen(t):
            ui.give({"do": "attack", "units": ids, "target": t.id})
        else:
            ui.give({"do": "amove" if verb == "attack" else "move", "units": ids, "to": [x, y]})
    elif verb == "gather":
        at = coords(rest[0]) if rest else None
        units = ui.units()
        if at is None and units:
            at = w.nearest_crystal(units[0].x // FP, units[0].y // FP, 20)
        elif at is not None and w.terrain[at[1] * w.W + at[0]] not in MINED:
            at = w.nearest_crystal(at[0], at[1], 12)
        if at:
            ui.give({"do": "gather", "units": [u.id for u in units], "at": list(at)})
        else:
            say.append("No crystal near.")
    elif verb == "build" and len(rest) >= 2 and coords(rest[1]):
        kind = next((k for k, s in w.kinds.items() if rest[0].lower() in (k, s["name"].lower())), None)
        if kind is None:
            say.append("No such building: %s." % rest[0])
        else:
            ui.give({"do": "build", "units": [u.id for u in ui.units() if u.spec.get("role") == "worker"][:1] or
                     [u.id for u in w.units_of(ui.side, "worker")][:1], "kind": kind, "at": list(coords(rest[1]))})
    elif verb == "train" and rest:
        kind = next((k for k, s in w.kinds.items() if rest[0].lower() in (k, s["name"].lower())), None)
        n = int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else 1
        b = next((t for t in ui.chosen() if t.building and kind in t.spec.get("produces", [])), None) or \
            next((t for t in w.buildings_of(ui.side) if t.done and kind in t.spec.get("produces", [])), None)
        if b is None:
            say.append("Nothing of yours makes that.")
        else:
            for _ in range(max(1, min(5, n))):
                ui.give({"do": "train", "building": b.id, "kind": kind})
    elif verb in ("stop", "hold"):
        ui.give({"do": verb, "units": [u.id for u in ui.units()]})
    elif verb == "look":
        at = coords(rest[0]) if rest else None
        say += text_map(w, ui, *(at or ui.cursor))
    elif verb == "map":
        say += text_map(w, ui, w.W // 2, w.H // 2, cols=w.W, rows=w.H)
    elif verb == "status":
        say += status_lines(w, ui)
    else:
        say.append("Not a command: %s. Type help." % verb)
    return 0.0, say


def play_text(world, write, read):
    """A skirmish a typed line at a time: commands, then time passes (``wait``)."""
    ui = UI(world)
    write(world.name)
    for t in (world.spec.get("intro") or []) if isinstance(world.spec.get("intro"), list) else \
            [world.spec.get("intro")] if world.spec.get("intro") else []:
        write(t)
    write(TEXT_HELP)
    for line in text_map(world, ui) + status_lines(world, ui):
        write(line)
    heard = len(world.messages)
    while not world.result:
        line = read("> ")
        if line is None:
            world.result = world.over = "quit"
            break
        waited = 0.0
        for part in (line.split(";") if line.strip() else [""]):
            sec, said = command(world, ui, part)
            for s in said:
                write(s)
            waited += sec
            if world.result:
                break
        if waited and not world.result:
            for _ in range(ticks(waited, world.rate)):
                world.step()
                if world.result:
                    break
            for tick, text, role in world.messages[heard:]:
                write("[%d:%02d] %s" % (tick // world.rate // 60, tick // world.rate % 60, text))
            heard = len(world.messages)
            if not world.result:
                for s in text_map(world, ui) + status_lines(world, ui):
                    write(s)
    if world.result in ("won", "lost"):
        write("VICTORY." if world.result == "won" else "DEFEAT.")
    world.over = world.result
    return world.result


def play_scene(game, scene):
    """Play the skirmish of a CLIo scene, then the scene's (or the skirmish's) effects for a win, a loss
    (none: the game is lost) or leaving it (none: the game ends)."""
    from . import conditions
    w, term, settings = game.world, game.term, game.settings
    sid = scene.get("skirmish")
    spec = game.data.skirmishes.get(sid) or {}
    world = make(game.data, sid)
    size_ok = True
    try:
        cols, rows = term.size()
        size_ok = cols >= 40 and rows >= 14
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
        play_frame(world, term, game.audio, game=game)
    else:
        def read(prompt):
            try:
                return term.read(prompt)
            except Exception as e:
                if e.__class__.__name__ == "QuitGame":
                    return None
                raise
        play_text(world, term.line, read)
    outcome = world.result
    w.vars.setdefault("skirmishes", {})[sid] = world.stats()
    if outcome == "won":
        w.flags["%s_won" % sid] = True
        effects = scene.get("on_skirmish_win") or spec.get("on_win")
        if effects:
            conditions.run(effects, game)
        else:
            game.say("Victory.", "success")
    elif outcome == "lost":
        effects = scene.get("on_skirmish_lose") or spec.get("on_lose")
        if effects:
            conditions.run(effects, game)
        else:
            game.end_game("lose", spec.get("death_text") or "outro_lose")
    else:
        effects = scene.get("on_skirmish_quit")
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
def _num(v, lo=None):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and (lo is None or v >= lo)


def kind_problems(kinds, where, upgrades=None):
    out = []
    upgrades = upgrades or {}
    for k, s in kinds.items():
        if s.get("role") not in ROLES:
            out.append("%s kind '%s': role should be one of %s" % (where, k, ", ".join(ROLES)))
        for f in ("hp", "cost", "time", "sight"):
            if not _num(s.get(f), 0):
                out.append("%s kind '%s': %s should be a number" % (where, k, f))
        for p in s.get("produces") or []:
            if p not in kinds:
                out.append("%s kind '%s' makes '%s', not a kind" % (where, k, p))
        if s.get("needs") and s["needs"] not in kinds and s["needs"] not in upgrades:
            out.append("%s kind '%s' needs '%s', not a kind or an upgrade" % (where, k, s["needs"]))
        if s.get("hits") not in (None, "ground", "air", "both"):
            out.append("%s kind '%s': hits should be ground, air or both" % (where, k))
        if s.get("building") and not (isinstance(s.get("size"), list) and len(s["size"]) == 2
                                      and all(isinstance(v, int) and 1 <= v <= 6 for v in s["size"])):
            out.append("%s kind '%s': size should be [w, h], 1-6 each" % (where, k))
        if not isinstance(s.get("char"), str) or len(s.get("char") or "") != 1:
            out.append("%s kind '%s': char should be one character" % (where, k))
    return out


def problems(data):
    out = []
    sk = getattr(data, "skirmishes", None) or {}
    ups = upgrades_of(data)
    out += kind_problems(kinds_of(data), "rts", ups)
    allk = kinds_of(data)
    for u, up in ups.items():
        if not isinstance(up, dict):
            continue
        if up.get("at") not in allk and up.get("at") not in ROLES:
            out.append("rts upgrade '%s': at should be a building kind or role, not '%s'" % (u, up.get("at")))
        for f in ("cost", "time"):
            if not _num(up.get(f), 0):
                out.append("rts upgrade '%s': %s should be a number" % (u, f))
        if not [f for f in STATS if f in up]:
            out.append("rts upgrade '%s' adds nothing (%s)" % (u, ", ".join(STATS)))
        for x in up.get("to") or []:
            if x not in allk and x not in ROLES:
                out.append("rts upgrade '%s': '%s' is not a kind or role" % (u, x))
        if up.get("needs") and up["needs"] not in allk and up["needs"] not in ups:
            out.append("rts upgrade '%s' needs '%s', not a kind or an upgrade" % (u, up["needs"]))
    for sid, spec in sk.items():
        where = "skirmish '%s'" % sid
        if not isinstance(spec, dict):
            out.append("%s should be an object" % where)
            continue
        rows = map_rows(spec)
        if not rows:
            out.append("%s: map should be a list of lines" % where)
            continue
        kinds = kinds_of(data, spec)
        if spec.get("kinds"):
            out += kind_problems({k: kinds[k] for k in spec["kinds"] if k in kinds}, where,
                                 upgrades_of(data, spec))
        sides = spec.get("sides") or []
        if not isinstance(sides, list) or not 1 <= len(sides) <= 4:
            out.append("%s: sides should be a list of 1 to 4" % where)
            continue
        legend = spec.get("legend") or {}
        known = set(TERRAIN) | set(legend) | set("1234")
        unknown = sorted({ch for r in rows for ch in r if ch not in known})
        if unknown:
            out.append("%s: the map has characters nothing says the meaning of: %s" % (where, " ".join(unknown)))
        players = 0
        for i, s in enumerate(sides):
            if not isinstance(s, dict):
                out.append("%s: side %d should be an object" % (where, i + 1))
                continue
            if s.get("control", "ai") not in ("player", "ai", "none"):
                out.append("%s: side %d control should be player, ai or none" % (where, i + 1))
            players += s.get("control") == "player"
            if not any(str(i + 1) in r for r in rows) and s.get("control") != "none":
                out.append("%s: side %d has no start (%d) on the map" % (where, i + 1, i + 1))
            fac = s.get("faction")
            mine = {k: v for k, v in kinds.items() if v.get("faction") == fac}
            for role in ("hq", "worker"):
                if not any(v.get("role") == role for v in mine.values()):
                    out.append("%s: side %d (faction %s) has no %s kind" % (where, i + 1, fac, role))
        if players > 1:
            out.append("%s: one side at most is the player's" % where)
        if spec.get("goal") not in (None, "destroy", "survive"):
            out.append("%s: goal should be destroy or survive" % where)
        if spec.get("goal") == "survive" and not _num(spec.get("time"), 1):
            out.append("%s: a survive goal needs a time" % where)
        try:
            w = World(spec, sid, data)
            for t in w.things.values():
                if t.building and not all(w.inside(x, y) and w.terrain[y * w.W + x] in OPEN
                                          for y in range(t.ty, t.ty + t.h) for x in range(t.tx, t.tx + t.w)):
                    out.append("%s: side %d's %s does not stand on open ground" % (where, t.side + 1, t.kind))
        except Exception as e:
            out.append("%s: %s" % (where, e))
    for sid, sc in (getattr(data, "scenes", None) or {}).items():
        if sc.get("skirmish") and sc["skirmish"] not in sk:
            out.append("scene '%s': unknown skirmish '%s'" % (sid, sc["skirmish"]))
    return out


def autoplay(world, minutes=30, player_ai=None):
    """The computer plays every side (the player's with ``player_ai``) until one wins or the time is up."""
    if world.player is not None:
        s = world.sides[world.player]
        s.control = "ai"
        s.ai = dict(AI, **(player_ai or world.spec.get("player_ai") or {}))
        s.wave = int(s.ai["wave"])
    end = int(minutes * 60 * world.rate)
    while not world.result and world.tick < end:
        world.step()
    if world.player is not None:
        world.sides[world.player].control = "player"
    return world.result, world.why


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
    for sid in argv or sorted(data.skirmishes):
        t0 = time.time()
        w = make(data, sid)
        result, why = autoplay(w)
        print("%s: %s (%s) at %d:%02d of play, %.1fs" % (sid, result or "no winner", why, w.tick // w.rate // 60,
                                                       w.tick // w.rate % 60, time.time() - t0))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
