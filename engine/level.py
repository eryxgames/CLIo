# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""First-person levels: a grid you walk through, seen through the player's eyes.

A scene can hold a level (``"level": "e1m1"`` in scenes.json).  Entering it
hands the screen to the level until the player leaves by its exit, dies or
quits; then the story goes on (``"on_level_exit"`` effects).  Levels live in
``levels.json``, their monsters in ``monsters.json``, pick-ups are ordinary
items with a ``"pickup"`` block, and the weapons and the player's start are in
game.json under ``"first_person"``.  docs/AUTHORING.md has the whole format.

Time moves in beats, as in a turn-based game: a step, a shot or a wait is one
beat, and then everything else moves.  Turning to look round is free.  On a
real terminal the level is drawn in frame mode (:mod:`engine.frame`,
:mod:`engine.firstperson`) and keys act at once; piped, or with ``--scroll``,
it is played in scrolling text with a small map, so it can be tested and
played anywhere.

Commands are typed as in a shell: ``a; b`` (a, then b), ``a && b`` (b only if
a hit or moved), ``a || b`` (b only if a missed or was blocked), ``!!``,
``!3``, ``!f``, ``alias``; a surprise - a hit, a monster appearing, fire coming
- stops a line as ^C would.
"""
from __future__ import annotations

import contextlib
import copy
import math
import random
import re
import time

from . import conditions
from . import firstperson as fp
from .firstperson import DIRS, FX, Bits, Picture, View, slide, vslide

FACING = {"n": 0, "north": 0, "e": 1, "east": 1, "s": 2, "south": 2, "w": 3, "west": 3}
FACE_NAMES = ("north", "east", "south", "west")

# what the characters of a map mean, unless a level's "legend" says otherwise
LEGEND = {
    "#": {"wall": "steel"}, "%": {"wall": "screens"}, "=": {"wall": "hazard"}, " ": {"wall": "steel"},
    ".": {}, "~": {"toxic": True}, "@": {"start": True},
    "+": {"door": True}, "R": {"door": True, "key": "r"}, "W": {"door": True, "key": "w"},
    "X": {"door": True, "key": "x"},
    "S": {"panel": "fist"}, "P": {"panel": "shoot"}, "E": {"exit": True},
    "&": {"crate": True}, "^": {"plate": "plate"},
    ":": {"oil": True}, ";": {"slick": True},
}

KEYMAP = {
    "up": "k", "down": "j", "left": "turn left", "right": "turn right",
    "ctrl-left": "h", "ctrl-right": "l", "alt-left": "h", "alt-right": "l",
    "shift-left": "h", "shift-right": "l", ",": "h", ".": "l", "<": "turn left", ">": "turn right",
    "home": "h", "pgup": "l", "end": "turn around", "pgdn": "use",
    "space": "f", "insert": "f", "enter": "use", "tab": "map", "center": "w", "delete": "w",
    "1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7",
    "?": "help", "f1": "help", "f2": "goggles",
}

WEAPONS = {
    "1": {"name": "fist", "ammo": None, "sprite": "w_fist", "sound": "punch", "kind": "melee", "damage": [6, 14]},
    "2": {"name": "pistol", "ammo": "bullets", "sprite": "w_pistol", "sound": "pistol", "damage": [8, 14]},
    "3": {"name": "shotgun", "ammo": "shells", "sprite": "w_shotgun", "sound": "shotgun", "damage": [5, 9],
          "pellets": 7, "spread": 0.35},
    "4": {"name": "chaingun", "ammo": "bullets", "sprite": "w_chaingun", "sound": "chaingun", "damage": [7, 12],
          "burst": 2},
}
ACCURACY = (1.0, 0.95, 0.9, 0.82, 0.72, 0.62, 0.52, 0.44, 0.38)   # by distance in cells
PELLET = (1.0, 1.0, 0.85, 0.6, 0.42, 0.3, 0.22, 0.16, 0.12)

HELP = [
    ("↑ ↓  step forward, back      ← →  turn", "text"),
    ("Ctrl+← →  or  , .  strafe     space  fire", "text"),
    ("Enter  open, press   Tab  map   1-7  weapons", "text"),
    ("F2  TTY goggles on/off (the battery lasts while off)", "text"),
    ("", "text"),
    ("Typed: k j h l, turn left/right/around, use,", "dim"),
    ("f [x], kill [-9] x, t x, w [n], map, ps, man x,", "dim"),
    ("goggles [on|off], out (of a vehicle), history,", "dim"),
    ("alias n='...', keys, whoami, sound, q", "dim"),
    ("a; b   a && b   a || b   !!  !3  !f   as in a shell", "dim"),
    ("A surprise stops a line, as ^C would.", "dim"),
]

DETAILS = ("auto", "high", "low")     # a level's picture: "low" draws the floor and ceiling at half width

STATE_MARK = {"aim": "!", "windup": "!", "charge": "»", "spin": "!!"}
STATE_ROLE = {"aim": "aim", "windup": "wind", "charge": "charge", "spin": "aim"}


class StopLine(Exception):
    """An unknown command ends the rest of the line, as an error would in a script."""


# --------------------------------------------------------------------------- #
# the map
# --------------------------------------------------------------------------- #
class Cell:
    __slots__ = ("x", "y", "ch", "kind", "tex", "key", "panel", "toxic", "open", "opens_on", "closes_on",
                 "on_enter", "sealed", "pressed", "label", "label_role", "secret", "found", "floor", "ceiling",
                 "crate", "plate", "down", "open_while", "teleport", "arrive_only", "pad_facing", "lift", "deck", "sunk",
                 "oil", "slick", "conveyor", "scorched", "exit_kind", "heavy")

    def __init__(self, x, y, ch, spec):
        self.x, self.y, self.ch = x, y, ch
        self.tex = spec.get("wall") or spec.get("texture") or "steel"
        self.floor = spec.get("floor")                  # tiles under and over this cell, else the level's
        self.ceiling = spec.get("ceiling")
        self.crate = bool(spec.get("crate"))            # a crate stands here: it can be pushed
        self.heavy = spec.get("crate") == "heavy" or (self.crate and bool(spec.get("heavy")))   # only a machine moves it
        self.plate = spec.get("plate")                  # a pressure plate, by name
        self.down = False
        self.open_while = spec.get("open_while")        # a door or wall open only while a plate of this name is down
        self.teleport = spec.get("teleport")            # a teleporter's pad: pads of one name lead to each other
        self.arrive_only = bool(spec.get("arrive"))
        self.pad_facing = spec.get("facing")
        self.lift = spec.get("lift")                    # a lift: the two of one name ride to each other
        self.deck = int(spec.get("deck", 0) or 0)
        self.sunk = False
        self.oil = bool(spec.get("oil"))                # oil: slippery, and it burns, fire running along it
        self.slick = bool(spec.get("slick")) or self.oil   # slippery: what moves onto it slides on
        c = str(spec.get("conveyor") or "").lower()[:1]
        self.conveyor = FACING.get(c) if c else None    # a belt: what is on it moves a cell a beat, this way
        self.scorched = False
        self.key = spec.get("key")
        self.panel = spec.get("panel")
        self.toxic = bool(spec.get("toxic"))
        self.opens_on = spec.get("opens_on")
        self.closes_on = spec.get("closes_on")
        self.on_enter = spec.get("on_enter")
        self.sealed = bool(spec.get("sealed")) or bool(spec.get("door") and spec.get("opens_on") and not spec.get("key"))
        self.pressed = False
        self.secret = bool(spec.get("secret")) or bool(self.panel)
        self.found = False
        self.open = 0.0
        self.exit_kind = "secret" if spec.get("exit") == "secret" else "exit"
        if spec.get("exit"):
            self.kind = "exit"
        elif spec.get("door"):
            self.kind = "door"
            self.open = 1.0 if spec.get("open") else 0.0
        elif self.panel:
            self.kind = "panel"
        elif spec.get("wall") or ((spec.get("opens_on") or spec.get("open_while")) and not spec.get("door")):
            self.kind = "wall"
        else:
            self.kind = "floor"
        self.label, self.label_role = None, None
        if self.kind == "door" and self.key:
            self.label = "".join(b if b == self.key else "-" for b in "rwx")
            self.label_role = "key_" + self.key
        elif self.kind == "exit":
            self.label, self.label_role = "EXIT", "good"

    @property
    def solid(self):
        if self.crate:
            return True
        if self.kind == "door":
            return self.open < 1.0
        return self.kind in ("wall", "panel", "exit")

    def drawn_as_wall(self, opened=None):
        if self.kind == "door":
            return (self.open if opened is None else opened) < 1.0
        return self.kind in ("wall", "panel", "exit")

    def texture(self):
        if self.kind == "door":
            if self.sealed:
                return "sealed"
            return "door_" + self.key if self.key else "door"
        if self.kind == "panel":
            return self.panel if self.panel in ("fist", "shoot") else "steel"
        if self.kind == "exit":
            return "exit_on" if self.pressed else "exit"
        return self.tex


VOID = Cell(-1, -1, " ", {"wall": "steel"})


class Monster:
    def __init__(self, mid, kind, spec, x, y, tag):
        self.id, self.kind, self.spec = mid, kind, spec
        self.x, self.y, self.tag = x, y, tag
        self.hp = self.max_hp = int(spec.get("hp", 20))
        self.spin = 0                                   # beats spent spinning up (a gun that must spin first)
        self.spun = False
        self.stride = 0                                 # steps taken: which foot its walk shows
        self.stun = 0                                   # beats it loses (a chainsaw bites)
        self.sprite = spec.get("sprite") or kind
        self.size = float(spec.get("size", 1.0))
        self.float = float(spec.get("float", 0.0))
        self.attack = spec.get("attack") or {}
        self.awake = bool(spec.get("awake"))
        self.wake_on = None
        self.intent = None
        self.cool = 0
        self.grudge = None
        self.dead = False
        self.gone = False            # left the level alive (an escape)
        self.seen = False
        self.targeted = False
        self.owner = None            # the monster that made this one
        self.clock = 0
        self.enraged = False
        self.barrel = spec.get("kind") == "barrel" or self.attack.get("kind") == "barrel"
        self.vehicle = spec.get("vehicle") if isinstance(spec.get("vehicle"), dict) else None   # one can ride it

    @property
    def name(self):
        return self.spec.get("name", self.kind)

    def label(self):
        mark = STATE_MARK.get(self.intent, "")
        role = STATE_ROLE.get(self.intent, "dim" if self.barrel else "boss" if self.spec.get("boss") else "tag")
        if self.grudge is not None:
            role = "alert"
        return self.tag + mark, role


class Item:
    def __init__(self, iid, spec, x, y):
        self.iid, self.spec, self.x, self.y = iid, spec, x, y
        self.pickup = spec.get("pickup") or {}
        self.sprite = self.pickup.get("sprite") or spec.get("sprite") or iid
        self.size = float(self.pickup.get("size", 0.55))
        self.taken = False
        self.on_pickup = None


class Grenade:
    """A grenade on the floor, its fuse burning: beats left until it goes off."""

    def __init__(self, x, y, fuse, blast):
        self.x, self.y, self.fuse, self.blast = x, y, fuse, blast


HOLES = 60                   # bullet holes kept in a level's walls (the oldest go first)


class Shot:
    def __init__(self, path, owner, damage, speed=1):
        self.path, self.owner, self.damage, self.speed = path, owner, damage, speed
        self.i = 0
        self.x, self.y = path[0] if path else (0, 0)


class Player:
    def __init__(self, state, cfg):
        start = dict(cfg.get("start") or {})
        start.update(state or {})
        self.x = self.y = 0
        self.facing = 0
        self.hp = int(start.get("health", 100))
        self.max_hp = int(start.get("max_health", 100))
        self.armor = int(start.get("armor", 0))
        self.weapons = [str(w) for w in start.get("weapons", ["1", "2"])]
        self.weapon = str(start.get("weapon", self.weapons[-1] if self.weapons else "1"))
        self.ammo = dict(start.get("ammo") or {"bullets": 50, "shells": 0})
        self.max_ammo = dict(start.get("max_ammo") or {"bullets": 200, "shells": 50})
        self.keys = set()
        self.sudo = 0
        self.boots = int(start.get("boots", 0))      # beats on toxic floor the boots have left
        self.vehicle = None                          # the machine he rides (a Monster), or None on foot
        self.goggles = 0                             # beats the TTY goggles' battery has left
        self.goggles_on = False                      # worn: the battery runs down only while they are on
        self.had_goggles = False

    @property
    def nightvision(self):
        """Seeing through the goggles: they are on and the battery is not flat."""
        return bool(self.goggles and self.goggles_on)

    def keep(self):
        """What goes on to the next level (keys and root do not; boots do)."""
        return {"health": self.hp, "max_health": self.max_hp, "armor": self.armor, "weapons": self.weapons,
                "weapon": self.weapon, "ammo": dict(self.ammo), "max_ammo": dict(self.max_ammo),
                "boots": self.boots}


def bresenham(x0, y0, x1, y1):
    cells = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        cells.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return cells
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def ease(k):
    return k * k * (3 - 2 * k)


# --------------------------------------------------------------------------- #
# the level
# --------------------------------------------------------------------------- #
class Level:
    def __init__(self, data, level_id, audio=None, seed=None, player=None):
        spec = (data.levels or {}).get(level_id)
        if not isinstance(spec, dict):
            raise ValueError("there is no level '%s'" % level_id)
        self.data, self.id, self.spec = data, level_id, spec
        self.cfg = data.config.get("first_person") or {}
        self.audio = audio
        self.rng = random.Random(seed if seed is not None else level_id)
        self.name = spec.get("name", level_id)
        self.par = int(spec.get("par", 0))
        own = {str(k): v for k, v in (getattr(data, "weapons", None) or {}).items() if isinstance(v, dict)}
        self.weapons = {str(k): v for k, v in (self.cfg.get("weapons") or ({} if own else WEAPONS)).items()}
        self.weapons.update(own)                         # weapons.json, over game.json's first_person "weapons"
        self.player = Player(player, self.cfg)
        self.monsters, self.items, self.shots, self.decals = [], [], [], []
        self.grenades = []
        self.holes = []                                  # (x, y, face, along, down): bullet holes in walls
        self.marks, self.marks_version = {}, 0
        self.log = []
        self.beat = 0
        self.over = None
        self.interrupt = None
        self.history, self.last_line = [], ""
        self.aliases = {"dodge": "h || l"}
        self.target = None
        self.seen_cells = set()
        self.events = set()
        self.noise_at = None
        self.stats = {"kills": 0, "items": 0, "secrets": 0, "taken": 0, "fired": 0, "hits": 0}
        self.boots_said = False
        self.exit_kind = None
        self.vrng = random.Random(repr(seed) + "/looks")   # for what is only seen: the game's own chances stay as they were
        self.boss = None
        self.console = None
        self.sprites = {}
        self._tags = {}
        self._ids = 0
        self.parse_map()
        self.load_sprites()
        self.load_tiles()
        self.plates(quiet=True)
        self.update_seen()

    # ---- building ------------------------------------------------------- #
    def parse_map(self):
        legend = dict(LEGEND)
        legend.update(self.spec.get("legend") or {})
        rows = [str(r) for r in self.spec.get("map") or []]
        self.h = len(rows)
        self.w = max((len(r) for r in rows), default=0)
        self.grid = []
        start = None
        for y in range(self.h):
            line = []
            for x in range(self.w):
                ch = rows[y][x] if x < len(rows[y]) else " "
                spec = legend.get(ch)
                if spec is None:
                    spec = {}
                if isinstance(spec, str):
                    spec = {"monster": spec} if spec in (self.data.monsters or {}) else {"item": spec}
                cell = Cell(x, y, ch, {k: v for k, v in spec.items() if k not in ("monster", "item")})
                line.append(cell)
                if spec.get("start"):
                    start = (x, y)
                if spec.get("monster"):
                    m = self.add_monster(spec["monster"], x, y)
                    if m is not None:
                        m.wake_on = spec.get("wake_on")
                        if spec.get("awake"):
                            m.awake = True
                if spec.get("item"):
                    it = self.add_item(spec["item"], x, y)
                    if it is not None:
                        it.on_pickup = spec.get("on_pickup")
            self.grid.append(line)
        if start is None:
            start = next(((c.x, c.y) for row in self.grid for c in row if not c.solid), (1, 1))
        self.player.x, self.player.y = start
        self.player.facing = FACING.get(str(self.spec.get("facing", "n")).lower(), 0)
        # number the tags in the order a player meets them: z1 is the nearest zombie
        far = self.distances(*start, limit=400)
        counts = {}
        for m in sorted(self.monsters, key=lambda m: (far.get((m.x, m.y), 999), m.y, m.x)):
            letter = m.tag.rstrip("0123456789")
            counts[letter] = counts.get(letter, 0) + 1
            m.tag = "%s%d" % (letter, counts[letter])
        cells = [c for row in self.grid for c in row]
        self.plate_cells = [c for c in cells if c.plate]
        self.held_cells = [c for c in cells if c.open_while]
        self.pads = [c for c in cells if c.teleport]
        self.lifts = [c for c in cells if c.lift]
        self.belts = [c for c in cells if c.conveyor is not None]
        self.fires = {}                                  # (x, y) -> beats it burns on
        self.total_kills = sum(1 for m in self.monsters if not m.barrel and not m.spec.get("boss"))
        self.total_items = len(self.items)
        self.total_secrets = sum(1 for row in self.grid for c in row if c.secret)

    def add_monster(self, kind, x, y):
        spec = (self.data.monsters or {}).get(kind)
        if not isinstance(spec, dict):
            return None
        letter = spec.get("tag") or kind[0]
        self._tags[letter] = self._tags.get(letter, 0) + 1
        self._ids += 1
        m = Monster(self._ids, kind, spec, x, y, "%s%d" % (letter, self._tags[letter]))
        if m.spec.get("boss") and self.boss is None:
            self.boss = m
        self.monsters.append(m)
        return m

    def add_item(self, iid, x, y):
        spec = (self.data.items or {}).get(iid)
        if not isinstance(spec, dict):
            return None
        it = Item(iid, spec, x, y)
        self.items.append(it)
        return it

    def load_sprites(self):
        from .sprite import _rgb, far_versions, walk_frames
        names = {m.sprite for m in self.monsters} | {it.sprite for it in self.items}
        names |= {w.get("sprite") for w in self.weapons.values()} | {"fireball", "muzzle", "gore", "crate", "container",
                                                                     "grenade", "rocket"}
        names |= {m.vehicle.get("cockpit") for m in self.monsters if m.vehicle}
        names |= {(m.spec.get("attack") or {}).get("spawn") for m in self.monsters}
        for kind in list(names):
            spec = (self.data.monsters or {}).get(kind)
            if isinstance(spec, dict):
                names.add(spec.get("sprite") or kind)
        movers = set()                                  # the pictures of monsters that walk
        for kind in {m.kind for m in self.monsters} | {(m.spec.get("attack") or {}).get("spawn") for m in self.monsters}:
            spec = (self.data.monsters or {}).get(kind)
            if isinstance(spec, dict) and not spec.get("float") \
                    and (spec.get("attack") or {}).get("kind") not in ("barrel", "spawner", "cron"):
                movers.add(spec.get("sprite") or kind)
        for name in names:
            if not name:
                continue
            data = (self.data.sprites or {}).get(name)
            if not isinstance(data, dict) or not data.get("pixels"):
                continue
            pal = {k: _rgb(v) for k, v in (data.get("palette") or {}).items()}
            keep = data.get("keep", "")
            far = None if data.get("lod") else far_versions(data["pixels"], keep)
            pic = self.sprites[name] = Picture.from_data(data, pal, far)
            if name in movers:                          # its steps: drawn, or made from its standing picture
                walk = data["walk"] if isinstance(data.get("walk"), list) else walk_frames(data["pixels"])
                pic.walk = [Picture.from_data({"pixels": f}, pal, far_versions(f, keep)) for f in walk if f]
                if data.get("attack"):
                    pic.attack = Picture.from_data({"pixels": data["attack"]}, pal, far_versions(data["attack"], keep))
            mz = data.get("muzzle")
            if isinstance(mz, (list, tuple)) and len(mz) == 2 and pic.w and pic.h:
                pic.muzzle = ((mz[0] + 0.5) / pic.w, (mz[1] + 0.5) / pic.h)

    def load_tiles(self):
        """The game's own tiles (tiles.json) over the engine's, and the level's floor and ceiling."""
        from .firstperson import tile_frames
        self.tiles, self.see_through = {}, set()
        for name, data in (getattr(self.data, "tiles", None) or {}).items():
            frames = tile_frames(data) if isinstance(data, dict) else []
            if frames:
                self.tiles[name] = frames
                if any(c is None for f in frames for r in f for c in r):
                    self.see_through.add(name)
        self.floor_tile, self.ceiling_tile = self.spec.get("floor"), self.spec.get("ceiling")

    # ---- the grid ------------------------------------------------------- #
    def cell(self, x, y):
        if 0 <= y < self.h and 0 <= x < self.w:
            return self.grid[y][x]
        return VOID

    def crate_cells(self):
        return [(c.x, c.y) for row in self.grid for c in row if c.crate]

    def monster_at(self, x, y, skip=None):
        for m in self.monsters:
            if not m.dead and not m.gone and m.x == x and m.y == y and m is not skip:
                return m
        return None

    def passable(self, x, y):
        c = self.cell(x, y)
        return not c.solid

    def free(self, x, y, skip=None):
        p = self.player
        return self.passable(x, y) and not self.monster_at(x, y, skip) and (x, y) != (p.x, p.y)

    def line_of_sight(self, x0, y0, x1, y1):
        for (x, y) in bresenham(x0, y0, x1, y1)[1:-1]:
            if self.cell(x, y).solid:
                return False
        return True

    def rel(self, x, y):
        """(sideways, ahead) of a cell from where the player stands and looks."""
        p = self.player
        fx, fy = DIRS[p.facing]
        rx, ry = DIRS[(p.facing + 1) % 4]
        dx, dy = x - p.x, y - p.y
        return dx * rx + dy * ry, dx * fx + dy * fy

    def dist(self, m):
        return max(abs(m.x - self.player.x), abs(m.y - self.player.y))

    def in_view(self, x, y):
        a, z = self.rel(x, y)
        return 1 <= z <= fp.SIGHT and abs(a) <= z + 0.5

    def update_seen(self):
        p = self.player
        for m in self.monsters:
            m.seen = (not m.dead and not m.gone and self.in_view(m.x, m.y)
                      and self.line_of_sight(p.x, p.y, m.x, m.y))
            m.targeted = m is self.target
        R = fp.SIGHT
        for y in range(p.y - R, p.y + R + 1):
            for x in range(p.x - R, p.x + R + 1):
                a, z = self.rel(x, y)
                if (z >= 0 and abs(a) <= z + 1) or max(abs(x - p.x), abs(y - p.y)) <= 1:
                    if self.line_of_sight(p.x, p.y, x, y):
                        self.seen_cells.add((x, y))

    def visible(self):
        return sorted([m for m in self.monsters if m.seen and not m.dead and not m.gone],
                      key=lambda m: (self.dist(m), abs(self.rel(m.x, m.y)[0])))

    def distances(self, x0, y0, limit=40):
        """Steps to (x0, y0) from every cell that can walk there (monsters do not block)."""
        dist = {(x0, y0): 0}
        frontier = [(x0, y0)]
        while frontier:
            nxt = []
            for (x, y) in frontier:
                d = dist[(x, y)]
                if d >= limit:
                    continue
                for dx, dy in DIRS:
                    n = (x + dx, y + dy)
                    if n not in dist and self.passable(*n):
                        dist[n] = d + 1
                        nxt.append(n)
                for n in self.pad_links().get((x, y), ()):     # a pad that leads here is a step away
                    if n not in dist:
                        dist[n] = d + 1
                        nxt.append(n)
            frontier = nxt
        return dist

    def pad_links(self):
        """For each pad, the pads whose way leads to it: ``{(x, y): [(x, y), ...]}`` (worked out once)."""
        if not hasattr(self, "pads"):                       # not yet read from the map
            return {}
        if getattr(self, "_pad_links", None) is None:
            links = {}
            for c in self.pads:
                if c.arrive_only:
                    continue
                group = [o for o in self.pads if o.teleport == c.teleport]
                others = group[group.index(c) + 1:] + group[:group.index(c)]
                if others:
                    links.setdefault((others[0].x, others[0].y), []).append((c.x, c.y))
            self._pad_links = links
        return self._pad_links

    # ---- talking ---------------------------------------------------------- #
    def say(self, text, role="text"):
        self.log = (self.log + [(text, role)])[-40:]
        if self.console is not None:
            self.console.said(text, role)

    def sfx(self, name, fallback=None):
        if self.audio is not None and name:
            try:
                self.audio.sfx(name, fallback) if fallback else self.audio.sfx(name)
            except Exception:
                pass

    def music(self, track):
        if self.audio is not None and track:
            try:
                self.audio.music(track)
            except Exception:
                pass

    def anim(self, frames, dt=0.05):
        if self.console is not None:
            self.console.play(self, frames, dt)

    def weapon_sprite(self):
        if self.player.vehicle is not None:
            return self.player.vehicle.vehicle.get("cockpit")
        return (self.weapons.get(self.player.weapon) or {}).get("sprite")

    # ---- playing ---------------------------------------------------------- #
    def run(self, console):
        """Play until the exit, death or quitting: "exit", "dead" or "quit"."""
        self.console = console
        console.start()
        try:
            self.music(self.spec.get("music"))
            console.page(self, self.intro_lines())
            while not self.over:
                line = console.read(self)
                if line is None:
                    self.over = "quit"
                    break
                with console.busy():
                    self.run_line(line)
            if self.over in ("exit", "dead"):
                console.ending(self)
                console.page(self, self.end_lines())
        except KeyboardInterrupt:
            self.over = self.over or "quit"
        finally:
            console.stop()
        return self.over

    def intro_lines(self):
        lines = [(self.spec.get("title") or self.name.upper(), "title")]
        for t in self.spec.get("intro") or []:
            lines.append((t, "dim"))
        lines.append(("", "text"))
        lines += HELP[:3]
        if self.par:
            lines += [("", "text"), ("par %d beats" % self.par, "dim")]
        return lines

    def end_lines(self):
        s = self.stats
        def pct(a, b):
            return "%d%%" % (100 * a // b) if b else "-"
        if self.over == "dead":
            head = [("Process terminated.", "hurt"), ("exit status 137 (SIGKILL)", "dim")]
        else:
            head = [(self.name.upper() + "  FINISHED", "good")]
        lines = head + [("", "text"),
                        ("kills      %s   (%d of %d)" % (pct(s["kills"], self.total_kills), s["kills"], self.total_kills), "text"),
                        ("items      %s" % pct(s["items"], self.total_items), "text"),
                        ("secrets    %s   (%d of %d)" % (pct(s["secrets"], self.total_secrets), s["secrets"],
                                                         self.total_secrets), "secret" if s["secrets"] else "text"),
                        ("beats      %d%s" % (self.beat, ("   par %d" % self.par) if self.par else ""),
                         "hit" if self.par and self.beat <= self.par and self.over == "exit" else "text")]
        if self.boss is not None and self.boss.gone:
            lines += [("", "text"), (self.spec.get("boss_escaped_line", "%s got away." % self.boss.name), "boss")]
        return lines

    # ---- a typed line: commands joined like a shell's -------------------- #
    def run_line(self, line):
        line = (line or "").strip()
        if not line:
            return
        m = re.fullmatch(r"!(\d+|[a-z][\w ]*)", line)
        if m:
            key = m.group(1)
            found = (self.history[int(key) - 1] if key.isdigit() and 0 < int(key) <= len(self.history)
                     else next((h for h in reversed(self.history) if h.startswith(key)), None))
            if found is None:
                self.say("rootless: !%s: event not found" % key, "dim")
                return
            line = found
        if "!!" in line:
            if not self.last_line:
                self.say("!!: event not found", "dim")
                return
            line = line.replace("!!", self.last_line)
        self.last_line = line
        self.history = (self.history + [line])[-50:]
        if re.match(r"(un)?alias\b", line):
            self.alias(line)
            return
        parts = re.split(r"\s*(;|&&|\|\|)\s*", self.expand(line))
        ok, op, first = True, ";", True
        self.interrupt = None
        for i, tok in enumerate(parts):
            if i % 2:
                op = tok
                continue
            if not tok or (op == "&&" and not ok) or (op == "||" and ok):
                continue
            if self.over:
                return
            if not first and self.interrupt:
                self.say("^C  %s" % self.interrupt, "alert")
                return
            try:
                ok = self.command(tok)
            except StopLine:
                return
            first = False

    def expand(self, line, depth=0):
        out = []
        for part in re.split(r"(\s*(?:;|&&|\|\|)\s*)", line):
            words = part.split()
            if words and words[0] in self.aliases and depth < 5:
                out.append(self.expand(" ".join([self.aliases[words[0]]] + words[1:]), depth + 1))
            else:
                out.append(part)
        return "".join(out)

    def alias(self, line):
        m = re.fullmatch(r"alias\s+([a-z][\w-]*)=(['\"]?)(.+)\2", line)
        if m:
            self.aliases[m.group(1)] = m.group(3).strip()
            self.say("alias %s='%s'" % (m.group(1), m.group(3).strip()), "info")
        elif re.fullmatch(r"unalias\s+\S+", line):
            self.aliases.pop(line.split()[1], None)
        elif line.strip() == "alias":
            self.console.page(self, [("alias %s='%s'" % kv, "text") for kv in sorted(self.aliases.items())]
                              or [("no aliases", "dim")])
        else:
            self.say("usage: alias name='line'", "dim")

    def command(self, tok):
        t = " ".join(tok.strip().lower().split())
        moves = {"k": (0, 1), "forward": (0, 1), "fwd": (0, 1), "j": (0, -1), "back": (0, -1),
                 "h": (-1, 0), "strafe left": (-1, 0), "l": (1, 0), "strafe right": (1, 0)}
        if t in moves:
            return self.step(*moves[t])
        turns = {"turn left": -1, "tl": -1, "<": -1, "left": -1, "turn right": 1, "tr": 1, ">": 1, "right": 1,
                 "turn around": 2, "ta": 2, "about": 2}
        if t in turns:
            return self.turn(turns[t])
        if t in ("u", "use", "open", "press"):
            return self.use()
        if t in ("out", "leave", "dismount", "get out"):
            return self.leave()
        if self.player.vehicle is not None and (t in self.weapons or (len(t) == 1 and t.isdigit())):
            self.say("Your hands are on the %s's levers: its claws are your weapon. (out: climb down)"
                     % self.player.vehicle.name, "dim")
            return True
        if t in ("w", "wait", "."):
            self.end_beat()
            return True
        m = re.fullmatch(r"(?:w|wait|sleep)\s+(\d+)", t)
        if m:
            return self.sleep(int(m.group(1)))
        if len(t) == 1 and t.isdigit() and any(self.slot_of(k) == t for k in self.weapons):
            return self.choose_slot(t)
        if t in self.weapons:
            return self.switch(t)
        m = re.fullmatch(r"(?:f|fire|shoot)\s*([a-z]\d*)?", t)
        if m:
            return self.fire(m.group(1))
        m = re.fullmatch(r"kill(\s+-9)?(?:\s+([a-z]\d*))?", t)
        if m:
            if m.group(1) and self.player.weapon != "1" and "1" in self.weapons:
                self.switch("1")
            return self.fire(m.group(2))
        m = re.fullmatch(r"(?:t|target)(?:\s+([a-z]\d*))?", t)
        if m:
            return self.set_target(m.group(1))
        if t in ("map", "m"):
            self.console.page(self, None, automap=True)
            return True
        if t == "ps":
            self.console.page(self, self.ps_lines())
            return True
        m = re.fullmatch(r"man(?:\s+(\S+))?", t)
        if m:
            self.console.page(self, self.man_lines(m.group(1)))
            return True
        if t == "history":
            self.console.page(self, [("%3d  %s" % (i + 1, h), "text") for i, h in enumerate(self.history)][-14:])
            return True
        if t == "keys":
            km = self.console.keymap if getattr(self.console, "keys", None) else None
            self.console.page(self, [("%-12s %s" % kv, "text") for kv in sorted(km.items())] if km
                              else [("No single keys here: type the commands.", "dim")])
            return True
        m = re.fullmatch(r"sound(?:\s+(set)(?:\s+(\S+))?)?", t)
        if m:
            if self.audio is None:
                self.say("No sound here.", "dim")
            elif m.group(1):
                self.say(self.audio.choose_set(m.group(2)), "dim")
            else:
                self.console.page(self, [(l, "text") for l in self.audio.status()] +
                                  ([("sound set NAME plays another set of sounds", "dim")] if self.audio.sets else []))
            return True
        m = re.fullmatch(r"(?:goggles|nv)(?:\s+(on|off))?", t)
        if m:
            return self.goggles(m.group(1))
        if t == "whoami":
            self.say("rootless   (uid 1000; root was revoked)" if not self.player.sudo else "root   (for now)", "dim")
            if self.player.boots:
                self.say("Hazmat boots on: %d more beats in acid." % self.player.boots, "toxic")
            return True
        if t.startswith("sudo"):
            if self.player.sudo:
                self.say("You are root for %d more beats." % self.player.sudo, "root")
            else:
                self.say("rootless is not in the sudoers file. This incident will be reported.", "hurt")
            return True
        if t in ("?", "help"):
            self.console.page(self, HELP)
            return True
        if t in ("q", "quit", "exit"):
            self.over = "quit"
            return True
        self.say("rootless: %s: command not found" % tok.strip(), "hurt")
        raise StopLine()

    # ---- a machine to ride ------------------------------------------------- #
    def board(self, m):
        """Climb into a vehicle (walk into it): you go where it goes, it takes the hits, its claws are your hands."""
        p = self.player
        spec = m.vehicle
        ox, oy = p.x, p.y
        self.monsters.remove(m)
        p.vehicle, p.x, p.y = m, m.x, m.y
        if self.target is m:
            self.target = None
        self.sfx((spec.get("sounds") or {}).get("board") or "use", "use")
        self.anim([FX(cam=(ox + (m.x - ox) * ease(i / 5.0), oy + (m.y - oy) * ease(i / 5.0)), recoil=6 - i)
                   for i in range(1, 6)], 0.04)
        self.say(spec.get("board") or "You climb into the %s." % m.name, "good")
        self.update_seen()
        self.arrive()
        self.end_beat()
        return True

    def leave(self):
        """Climb down from the vehicle: behind you, or to a side - it stays where it stands."""
        p = self.player
        v = p.vehicle
        if v is None:
            self.say("You are on your own two feet already.", "dim")
            return False
        fx, fy = DIRS[p.facing]
        rx, ry = DIRS[(p.facing + 1) % 4]
        sides = [(-fx, -fy), (-rx, -ry), (rx, ry), (fx, fy)]
        ok = [(p.x + dx, p.y + dy) for dx, dy in sides if self.free(p.x + dx, p.y + dy)]
        dry = [c for c in ok if not self.cell(*c).toxic and c not in self.fires] or ok
        if not dry:
            self.say("No room to climb down here.", "dim")
            return False
        x, y = dry[0]
        p.vehicle = None
        v.x, v.y = p.x, p.y
        self.monsters.append(v)
        ox, oy = p.x, p.y
        p.x, p.y = x, y
        self.sfx((v.vehicle.get("sounds") or {}).get("board") or "use", "use")
        self.anim([FX(cam=(ox + (x - ox) * ease(i / 4.0), oy + (y - oy) * ease(i / 4.0))) for i in range(1, 5)], 0.04)
        self.say(v.vehicle.get("leave") or "You climb down from the %s." % v.name, "dim")
        self.update_seen()
        self.arrive()
        self.end_beat()
        return True

    def stomp(self, m, x, y):
        """Riding into a monster: it is trodden on - crushed, if that kills it, or else thrown back."""
        p, v = self.player, self.player.vehicle
        dmg = int(v.vehicle.get("stomp", 40))
        fx, fy = x - p.x, y - p.y
        self.sfx((v.vehicle.get("sounds") or {}).get("step") or "punch", "punch")
        self.anim([FX(cam=(p.x + fx * k, p.y + fy * k), shake=s) for k, s in ((0.25, 1), (0.4, -1), (0.2, 0))], 0.04)
        self.damage([(m, dmg)], lead="The %s treads on it:" % v.name)
        if self.over:
            return True
        if m.dead:
            ox, oy = p.x, p.y
            p.x, p.y = x, y
            self.anim([FX(cam=(ox + fx * ease(i / 4.0), oy + fy * ease(i / 4.0))) for i in range(1, 5)], 0.03)
            self.update_seen()
            self.arrive()
        elif self.free(x + fx, y + fy, skip=m):
            m.x, m.y = x + fx, y + fy
            self.anim([FX(pos={m.id: (x + fx * k, y + fy * k)}) for k in (0.5, 0.85, 1.0)], 0.04)
            self.say("%s is thrown back." % m.tag, "hit")
        self.end_beat()
        return True

    def claw(self):
        """The vehicle's claws: a heavy blow to what is right ahead - a monster thrown back, a hollow wall
        broken through, a barrel set off."""
        p, v = self.player, self.player.vehicle
        spec = v.vehicle
        x, y = self.ahead()
        cell = self.cell(x, y)
        m = self.monster_at(x, y)
        self.sfx((spec.get("sounds") or {}).get("claw") or "punch", "punch")
        self.anim([FX(recoil=-3), FX(recoil=-5, shake=1), FX(recoil=-2)], 0.04)
        if m is not None:
            lo, hi = spec.get("claw", [30, 50])
            self.stats["fired"] += 1
            self.stats["hits"] += 1
            self.damage([(m, self.rng.randint(lo, hi))], lead="CRUNCH.")
            fx, fy = DIRS[p.facing]
            if not m.dead and not m.barrel and not m.spec.get("boss") and self.free(m.x + fx, m.y + fy, skip=m):
                ox, oy = m.x, m.y
                m.x, m.y = ox + fx, oy + fy
                m.stun, m.intent = max(m.stun, 1), None
                self.anim([FX(pos={m.id: (ox + fx * k, oy + fy * k)}) for k in (0.5, 0.85, 1.0)], 0.04)
                self.say("%s is flung back." % m.tag, "hit")
        elif cell.kind == "panel" and cell.panel == "fist":
            self.open_panel(cell)
        elif cell.crate:
            self.say("The claws clang on the %s. (Walk into it to shove it.)" % ("container" if cell.heavy else "crate"), "dim")
        elif cell.solid:
            self.say("The claws scrape the wall. Sparks.", "dim")
        else:
            self.say("The claws snap shut on air.", "dim")
        self.end_beat()
        return True

    def wreck(self):
        """The vehicle gives out under you: you are thrown clear, and it blows apart."""
        p, v = self.player, self.player.vehicle
        fx, fy = DIRS[p.facing]
        rx, ry = DIRS[(p.facing + 1) % 4]
        spots = [(p.x + dx, p.y + dy) for dx, dy in ((-fx, -fy), (-rx, -ry), (rx, ry), (fx, fy))
                 if self.free(p.x + dx, p.y + dy)]
        p.vehicle = None
        v.x, v.y = p.x, p.y
        self.monsters.append(v)
        self.say(v.vehicle.get("wreck") or "The %s gives out. You are thrown clear." % v.name, "alert")
        if spots:
            ox, oy = p.x, p.y
            p.x, p.y = spots[0]
            self.anim([FX(cam=(ox + (p.x - ox) * ease(i / 3.0), oy + (p.y - oy) * ease(i / 3.0)), shake=1 - i % 2 * 2)
                       for i in range(1, 4)], 0.04)
        v.hp = 0
        self.kill(v)
        self.update_seen()

    # ---- the player's actions --------------------------------------------- #
    def goggles(self, how=None):
        """Put the TTY goggles on or take them off (a free action, as turning is): their battery lasts longer."""
        p = self.player
        if not p.goggles:
            self.say("The goggles' battery is flat." if p.had_goggles else "You have no goggles.", "dim")
            return True
        want = (not p.goggles_on) if how is None else how == "on"
        if want == p.goggles_on:
            self.say("The goggles are already %s." % ("on" if want else "off"), "dim")
            return True
        p.goggles_on = want
        if want:
            self.sfx("goggles_on")
            self.say("Goggles on: the world in dots, and what is hollow shows. (%d beats of battery)" % p.goggles,
                     "secret")
        else:
            self.sfx("goggles_off", "click")
            self.say("Goggles off. The battery keeps %d beats." % p.goggles, "dim")
        self.update_seen()
        return True

    def turn(self, d):
        p = self.player
        old_cells = self.console.snapshot(self) if self.console else None
        p.facing = (p.facing + d) % 4
        self.update_seen()
        if old_cells is not None:
            self.console.turn(self, old_cells, -1 if d < 0 else 1)
        return True

    def step(self, side, ahead):
        p = self.player
        fx, fy = DIRS[p.facing]
        rx, ry = DIRS[(p.facing + 1) % 4]
        nx, ny = p.x + fx * ahead + rx * side, p.y + fy * ahead + ry * side
        cell = self.cell(nx, ny)
        v = p.vehicle
        if v is not None:                                # riding: no doors, no pads; what is in the way is trodden
            if cell.kind == "door":
                self.say("The %s will not fit through the door. (Enter or `out`: climb down)" % v.name, "dim")
                return False
            if cell.teleport or cell.lift:
                self.say("The %s is too heavy for the %s." % (v.name, "pad" if cell.teleport else "lift"), "dim")
                return False
            m = self.monster_at(nx, ny)
            if m is not None and not m.barrel and not m.spec.get("boss") and not m.float:
                return self.stomp(m, nx, ny)
        if cell.crate and cell.heavy and v is None:
            self.say("A container: it will not budge for you. Something with hydraulics might move it.", "dim")
            self.sfx("locked")
            return False
        if cell.crate:
            return self.push(cell, nx - p.x, ny - p.y)
        if cell.solid:
            if ahead > 0 and side == 0:
                return self.use()
            self.say("A wall." if cell.kind == "wall" else "Something is in the way.", "dim")
            return False
        m = self.monster_at(nx, ny)
        if m is not None and m.vehicle and v is None:
            return self.board(m)
        if m is not None and m.barrel and not m.vehicle:
            return self.push_barrel(m, nx - p.x, ny - p.y)
        if m is not None:
            self.say("%s is in the way." % m.tag, "dim")
            return False
        ox, oy = p.x, p.y
        p.x, p.y = nx, ny
        slid = self.slide_path(nx, ny, nx - ox, ny - oy)
        if slid:                                       # slick floor: on, until something stops it
            for (x, y) in slid:
                p.x, p.y = x, y
                for it in self.items:
                    if not it.taken and (it.x, it.y) == (x, y) and (x, y) != slid[-1]:
                        self.take(it)
            self.sfx("slide", "footstep")
            path = [(ox, oy), (nx, ny)] + slid
            n = len(path) - 1
            self.anim([FX(cam=self.along(path, ease(i / (3.0 * n)))) for i in range(1, 3 * n + 1)], 0.025)
            self.say("You slide on the %s." % ("oil" if self.cell(nx, ny).oil else "slick floor"), "dim")
            self.update_seen()
            self.arrive()
            self.end_beat()
            return True
        # silent unless the game or its sound set has them; a step into acid is "wade", or else a footstep
        wet = self.cell(nx, ny).toxic
        if v is not None:
            self.sfx((v.vehicle.get("sounds") or {}).get("step") or "footstep", "footstep")
        else:
            self.sfx("wade", "footstep") if wet else self.sfx("footstep")
        drops = (Bits(self.vrng).burst(nx + (nx - ox) * 0.45, ny + (ny - oy) * 0.45, 0.0,
                                      [(90, 230, 70), (150, 255, 110), (40, 150, 40)], n=10, speed=0.6, up=1.4,
                                      size=0.8).frames(4, 0.05) if wet else [()] * 4)
        self.anim([FX(cam=(ox + (nx - ox) * ease(i / 4.0), oy + (ny - oy) * ease(i / 4.0)), parts=drops[i - 1])
                   for i in range(1, 5)], 0.03)
        self.update_seen()
        self.arrive()
        self.end_beat()
        return True

    @staticmethod
    def along(path, k):
        """The point ``k`` (0..1) of the way along a path of cells."""
        n = len(path) - 1
        f = max(0.0, min(1.0, k)) * n
        i = min(n - 1, int(f))
        (x0, y0), (x1, y1) = path[i], path[i + 1]
        return x0 + (x1 - x0) * (f - i), y0 + (y1 - y0) * (f - i)

    def room(self, x, y, crate=False):
        """Can something slide or be pushed onto this cell? (No walls, crates, monsters, the player.)"""
        c = self.cell(x, y)
        p = self.player
        if c.solid or self.monster_at(x, y) is not None or (x, y) == (p.x, p.y):
            return False
        if crate and (c.teleport or c.lift or any(not it.taken and (it.x, it.y) == (x, y) for it in self.items)):
            return False
        return True

    def slide_path(self, x, y, dx, dy, crate=False):
        """The cells something goes on to after moving onto (x, y) going (dx, dy): none unless it is slick."""
        out = []
        while self.cell(x, y).slick and len(out) < 40 and self.room(x + dx, y + dy, crate):
            x, y = x + dx, y + dy
            out.append((x, y))
            if crate and self.cell(x, y).toxic:
                break
        return out

    def push_barrel(self, b, dx, dy):
        """Walk into a barrel: it rolls a cell on (further on slick floor) - into a crowd, or into the acid."""
        p = self.player
        bx, by = b.x + dx, b.y + dy
        if not self.room(bx, by, crate=True):
            self.say("The barrel will not move: something is behind it.", "dim")
            return False
        ox, oy, sx, sy = p.x, p.y, b.x, b.y
        path = [(sx, sy), (bx, by)] + self.slide_path(bx, by, dx, dy, crate=True)
        b.x, b.y = path[-1]
        p.x, p.y = sx, sy
        self.sfx("push", "drop")
        n = len(path) - 1
        frames = 4 * n
        self.anim([FX(cam=(ox + dx * ease(min(1.0, i / 4.0)), oy + dy * ease(min(1.0, i / 4.0))),
                      pos={b.id: self.along(path, i / float(frames))}) for i in range(1, frames + 1)], 0.03)
        self.say("You roll the barrel%s." % (" and it slides" if n > 1 else ""), "dim")
        self.update_seen()
        self.arrive()
        self.end_beat()
        return True

    def push(self, cell, dx, dy):
        """Walk into a crate: it slides one cell on, if there is room - into acid, it sinks and makes a step."""
        p = self.player
        bx, by = cell.x + dx, cell.y + dy
        beyond = self.cell(bx, by)
        if (beyond.solid or self.monster_at(bx, by) or beyond.teleport or beyond.lift
                or any(not it.taken and (it.x, it.y) == (bx, by) for it in self.items)):
            self.say("The crate will not move: something is behind it.", "dim")
            self.sfx("locked")
            return False
        heavy = cell.heavy
        cell.crate = cell.heavy = False
        ox, oy = p.x, p.y
        p.x, p.y = cell.x, cell.y
        path = [(cell.x, cell.y), (bx, by)] + ([] if beyond.toxic or heavy else self.slide_path(bx, by, dx, dy, crate=True))
        bx, by = path[-1]
        beyond = self.cell(bx, by)
        beyond.crate, beyond.heavy = True, heavy
        self.sfx("push", "drop")
        n = len(path) - 1
        frames = 4 * n
        self.anim([FX(cam=(ox + dx * ease(min(1.0, i / 4.0)), oy + dy * ease(min(1.0, i / 4.0))),
                      crates={(bx, by): self.along(path, i / float(frames))}) for i in range(1, frames + 1)], 0.035)
        if beyond.toxic:
            beyond.crate, beyond.heavy, beyond.toxic, beyond.sunk = False, False, False, True
            self.marks_version += 1
            self.say("The %s sinks into the acid and settles: a step you can stand on." % ("container" if heavy else "crate"), "good")
            self.sfx("wade", "drop")
        else:
            self.say("The loader shoves the container on." if heavy else "You push the crate.", "dim")
        self.update_seen()
        self.arrive()
        self.end_beat()
        return True

    def plates(self, quiet=False):
        """Plates are down while something heavy stands on them; what they hold opens, and shuts again."""
        if not self.plate_cells:
            return
        p = self.player
        weight = {(m.x, m.y) for m in self.monsters if not m.dead and not m.gone and not m.float} | {(p.x, p.y)}
        down = set()
        for c in self.plate_cells:
            now = c.crate or (c.x, c.y) in weight
            if now != c.down:
                c.down = now
                self.marks_version += 1
                if not quiet:
                    self.sfx("plate", "use")
            if now:
                down.add(c.plate)
        for c in self.held_cells:
            want = c.open_while in down
            here = (c.x, c.y) == (p.x, p.y) or self.monster_at(c.x, c.y) is not None or c.crate
            if c.kind == "door":
                if want and c.open < 1.0:
                    if quiet:
                        c.open = 1.0
                    else:
                        if c.open_while not in self.events:
                            self.events.add(c.open_while)
                            text = (self.spec.get("events") or {}).get(c.open_while)
                            if text:
                                self.say(text, "alert")
                        self.open_door(c)
                elif not want and c.open >= 1.0 and not here:
                    if not quiet:
                        self.sfx("door")
                        self.say("Somewhere a door slams shut.", "alert")
                        self.anim([FX(doors={(c.x, c.y): k}) for k in (0.7, 0.4, 0.1)], 0.04)
                    c.open = 0.0
            elif want and c.kind == "wall":
                c.kind = "floor"
            elif not want and c.kind == "floor" and not here:
                c.kind = "wall"
        self.update_seen()

    def arrive(self, teleported=False):
        p = self.player
        for it in self.items:
            if not it.taken and (it.x, it.y) == (p.x, p.y):
                self.take(it)
        cell = self.cell(p.x, p.y)
        if cell.secret and not cell.found and not cell.panel:      # a secret place, found by standing in it
            cell.found = True
            self.stats["secrets"] += 1
            self.sfx("secret")
            self.say("A secret area!", "secret")
        if cell.on_enter and cell.on_enter not in self.events:
            self.event(cell.on_enter)
        if cell.teleport and not cell.arrive_only and not teleported and not self.over:
            self.teleport(cell)

    def teleport(self, pad):
        """Pads of one name lead to each other: on to the next in the map's order (one marked "arrive" only receives)."""
        group = [c for c in self.pads if c.teleport == pad.teleport]
        others = group[group.index(pad) + 1:] + group[:group.index(pad)]
        dest = next((c for c in others if not c.crate), None)
        if dest is None:
            self.say("The pad hums, and nothing happens.", "dim")
            return
        p = self.player
        ox, oy, of = p.x, p.y, p.facing
        self.sfx("teleport")
        victim = self.monster_at(dest.x, dest.y)
        p.x, p.y = dest.x, dest.y
        if dest.pad_facing:
            p.facing = FACING.get(str(dest.pad_facing).lower(), p.facing)
        away = [FX(style="dots-fill", cam=(ox, oy), face=of, whiten=0.2), FX(style="dots", cam=(ox, oy), face=of, whiten=0.45),
                FX(style="dots", cam=(ox, oy), face=of, whiten=0.8)]
        here = [FX(style="dots", whiten=0.8), FX(style="dots", whiten=0.5), FX(style="dots", whiten=0.25),
                FX(style="dots-fill", whiten=0.1), FX(style="dots-fill")]
        self.anim(away + here, 0.13)
        self.say("A flash of dots, and you are somewhere else.", "secret")
        if victim is not None and not victim.barrel and not victim.spec.get("boss"):
            victim.hp = 0
            self.say("%s was standing on the pad. Was." % victim.tag, "good")
            self.kill(victim)
        self.update_seen()
        self.arrive(teleported=True)

    def ride(self, lift):
        """A lift takes the player to the other lift of its name: down, or up, by their decks."""
        dest = next((c for c in self.lifts if c.lift == lift.lift and c is not lift), None)
        if dest is None:
            self.say("The lift has nowhere to go.", "dim")
            return False
        if dest.crate or self.monster_at(dest.x, dest.y):
            self.say("Something blocks the lift at the other end.", "dim")
            return False
        p = self.player
        down = dest.deck < lift.deck
        console = self.console
        old = console.snapshot(self, style="dots-fill") if console else None
        p.x, p.y = dest.x, dest.y
        self.update_seen()
        new = console.snapshot(self, style="dots-fill") if console else None
        self.sfx("lift", "power")
        self.say("The lift hums %s." % ("down" if down else "up"), "info")
        if console is not None and old is not None:
            console.ride(self, old, new, down)
        self.arrive()
        self.end_beat()
        return True

    def take(self, it):
        p, pk = self.player, it.pickup
        name = it.spec.get("name", it.iid)
        if "health" in pk:
            limit = int(pk.get("max", p.max_hp))
            if p.hp >= limit:
                self.say("You do not need the %s." % name, "dim")
                return
            p.hp = min(limit, p.hp + int(pk["health"]))
        if "armor" in pk:
            if p.armor >= int(pk["armor"]) and len(pk) <= 2:
                self.say("Your armour is better than this %s." % name, "dim")
                return
            p.armor = max(p.armor, int(pk["armor"]))
        if "ammo" in pk:
            full = all(p.ammo.get(k, 0) >= p.max_ammo.get(k, 999) for k in pk["ammo"])
            if full and len(pk) <= 2:
                self.say("You cannot carry more.", "dim")
                return
            for k, n in pk["ammo"].items():
                p.ammo[k] = min(p.max_ammo.get(k, 999), p.ammo.get(k, 0) + int(n))
        if pk.get("key"):
            p.keys.add(pk["key"])
        if pk.get("weapon"):
            wid = str(pk["weapon"])
            if wid not in p.weapons:
                p.weapons.append(wid)
                p.weapons.sort()
                p.weapon = wid
        if pk.get("power") == "sudo":
            p.sudo = int(pk.get("beats", 20))
        if pk.get("power") == "boots":
            p.boots = max(p.boots, int(pk.get("beats", 20)))
        if pk.get("power") == "goggles":
            p.goggles = max(p.goggles, int(pk.get("beats", 30)))
            p.goggles_on = p.had_goggles = True
        it.taken = True
        self.stats["items"] += 1
        self.say(pk.get("text") or "You pick up the %s." % name, "root" if pk.get("power") else "good")
        self.sfx(pk.get("sound") or ("special" if pk.get("weapon") or pk.get("power") else "pickup"))
        if it.on_pickup:
            self.event(it.on_pickup)

    def ahead(self):
        p = self.player
        fx, fy = DIRS[p.facing]
        return p.x + fx, p.y + fy

    def use(self):
        x, y = self.ahead()
        cell = self.cell(x, y)
        p = self.player
        if p.vehicle is not None and cell.kind != "exit":           # in the cage, Enter climbs down
            if cell.kind == "door":
                self.say("The %s will not fit through the door: you climb down." % p.vehicle.name, "dim")
            return self.leave()
        here = self.cell(p.x, p.y)
        if here.lift and not (cell.kind in ("door", "exit") and not cell.pressed and cell.open < 1.0):
            return self.ride(here)
        if cell.kind == "door" and cell.open < 1.0 and cell.open_while:
            self.say("It will not open: something holds it shut. A plate somewhere keeps it.", "dim")
            self.sfx("locked")
            return False
        if cell.crate:
            self.say("A crate. Walk into it to push it.", "dim")
            return False
        if cell.kind == "door" and cell.open < 1.0:
            if cell.sealed:
                self.say("Sealed. Something keeps it shut.", "dim")
                self.sfx("locked")
                return False
            if cell.key and cell.key not in p.keys:
                self.say("Permission denied: this door needs the %s key." % cell.label, "hurt")
                self.sfx("locked")
                return False
            self.open_door(cell)
            self.end_beat()
            return True
        if cell.kind == "exit":
            if cell.pressed:
                return False
            cell.pressed = True
            self.exit_kind = cell.exit_kind
            self.sfx("power")
            self.say("You throw the switch." if cell.exit_kind != "secret" else "You throw the switch. A lift you had not seen opens.", "good")
            self.anim([FX() for _ in range(6)], 0.08)
            ride = self.spec.get("exit_ride")
            if ride in ("down", "up") and self.console is not None:     # the level ends in a lift
                old = self.console.snapshot(self, style="dots-fill")
                if old is not None:
                    self.sfx("lift", "power")
                    self.console.ride(self, old, None, ride == "down")
            self.over = "exit"
            return True
        if cell.kind == "panel":
            self.say("The wall sounds hollow here." if cell.panel == "fist" else "A vent, dented, as if shot at.", "dim")
            return False
        if cell.kind == "wall":
            self.say("A wall.", "dim")
            return False
        self.say("Nothing to use here.", "dim")
        return False

    def open_door(self, cell):
        self.sfx("door")
        self.anim([FX(doors={(cell.x, cell.y): k}) for k in (0.2, 0.4, 0.6, 0.8, 0.95)], 0.04)
        cell.open = 1.0
        self.update_seen()

    def open_panel(self, cell):
        cell.kind = "floor"
        cell.found = True
        self.stats["secrets"] += 1
        self.sfx("secret")
        self.say("A secret is revealed!", "secret")
        self.anim([FX(whiten=k) for k in (0.25, 0.12, 0.0)], 0.05)
        self.update_seen()

    def slot_of(self, wid):
        """The key a weapon is on: its "key", or its id when that is a digit."""
        w = self.weapons.get(wid) or {}
        return str(w.get("key") or wid)

    def choose_slot(self, key):
        """A weapon key: the best weapon on it, or the next one when one of them is in hand already."""
        p = self.player
        order = list(self.weapons)
        mine = [k for k in order if self.slot_of(k) == key and k in p.weapons]
        if len(mine) <= 1:
            return self.switch(mine[0] if mine else key)
        mine.reverse()                                  # the last in weapons.json first: the best
        if p.weapon in mine:
            mine = mine[mine.index(p.weapon) + 1:] + mine[:mine.index(p.weapon)]
        for k in mine:
            w = self.weapons[k]
            if not w.get("ammo") or p.ammo.get(w["ammo"], 0) > 0:
                return self.switch(k)
        return self.switch(mine[0])

    def switch(self, wid):
        p = self.player
        w = self.weapons.get(wid)
        if w is None or wid not in p.weapons:
            self.say("You have no %s." % (w or {}).get("name", "weapon " + wid), "dim")
            return False
        if w.get("ammo") and p.ammo.get(w["ammo"], 0) <= 0:
            self.say("No %s for the %s." % (w["ammo"], w["name"]), "dim")
            return False
        if p.weapon != wid:
            p.weapon = wid
            self.say("You ready the %s." % w["name"], "info")
            if w.get("ready_sound"):
                self.sfx(w["ready_sound"])
            self.anim([FX(recoil=4), FX(recoil=2), FX(recoil=1)], 0.04)
        return True

    def sleep(self, n):
        for i in range(min(n, 9)):
            if self.over:
                break
            if i and self.interrupt:
                self.say("^C  %s" % self.interrupt, "alert")
                break
            self.end_beat()
        return True

    def cone(self):
        """What a shot with no target goes for: everything in sight, the nearest and most central first.
        (With only quarter turns, much is never straight ahead; the gun finds it anyway.)"""
        return sorted([m for m in self.visible() if m.awake or not m.spec.get("boss")],
                      key=lambda m: (self.dist(m) + abs(self.rel(m.x, m.y)[0]) * 0.5, m.id))

    def set_target(self, tag=None):
        vis = self.visible()
        if not vis:
            self.say("Nothing in sight.", "dim")
            return False
        if tag:
            found = [m for m in vis if m.tag.lower() == tag] or [m for m in vis if len(tag) == 1 and m.tag[0].lower() == tag]
            if not found:
                self.say("rootless: %s: no such target in sight" % tag, "dim")
                return False
            self.target = found[0]
        else:
            i = vis.index(self.target) + 1 if self.target in vis else 0
            self.target = vis[i % len(vis)]
        self.update_seen()
        m = self.target
        self.say("Target: %s, %s, %d away." % (m.tag, m.name, self.dist(m)), "info")
        return True

    def fire(self, tag=None):
        p, rng = self.player, self.rng
        if p.vehicle is not None:
            return self.claw()
        w = self.weapons.get(p.weapon) or WEAPONS["1"]
        if w.get("ammo") and p.ammo.get(w["ammo"], 0) <= 0:
            self.say("Click. No %s." % w["ammo"], "hurt")
            return False
        melee = w.get("kind") == "melee"
        target = None
        if tag:
            vis = self.visible()
            found = [m for m in vis if m.tag.lower() == tag] or [m for m in vis if len(tag) == 1 and m.tag[0].lower() == tag]
            if not found:
                self.say("rootless: %s: no such target in sight" % tag, "dim")
                return False
            target = min(found, key=self.dist)
        elif self.target is not None and self.target.seen and not melee:
            target = self.target
        else:
            cone = self.cone()
            foes = [m for m in cone if not m.barrel]
            far_barrels = [m for m in cone if m.barrel and self.dist(m) > 1     # never one at arm's length,
                           and abs(self.rel(m.x, m.y)[0]) < 0.5 and not m.vehicle]   # only one straight ahead
            target = (foes or far_barrels or [None])[0]
        if w.get("kind") in ("rocket", "grenade"):
            if w.get("ammo"):
                p.ammo[w["ammo"]] = max(0, p.ammo[w["ammo"]] - 1)
            self.stats["fired"] += 1
            self.noise(p.x, p.y)
            if w["kind"] == "rocket":
                self.launch(w, target)
            else:
                self.lob(w, target)
            if self.over:
                return True
            self.after_shot(w)
            self.end_beat()
            return True
        if melee:
            ax, ay = self.ahead()
            if target is None or (target.x, target.y) != (ax, ay):
                target = self.monster_at(ax, ay)
            if target is None:
                cell = self.cell(ax, ay)
                self.anim([FX(recoil=-2), FX(recoil=-3), FX(recoil=-1)], 0.04)
                if cell.kind == "panel" and cell.panel == "fist":
                    self.sfx(w.get("sound"))
                    self.open_panel(cell)
                    self.end_beat()
                    return True
                if w.get("name", "fist") == "fist":
                    self.say("You punch the air." if not cell.solid else "Ow. That is a wall.", "dim")
                else:
                    self.say(("The %s cuts the air." if not cell.solid else "The %s bites the wall. Sparks.") % w["name"], "dim")
                self.end_beat()
                return False
        if w.get("ammo"):
            p.ammo[w["ammo"]] = max(0, p.ammo[w["ammo"]] - int(w.get("burst", 1)))
        self.stats["fired"] += 1
        self.sfx(w.get("sound"))
        self.anim([FX(recoil=-2), FX(recoil=-3), FX(recoil=-1)] if melee else
                  [FX(muzzle=True, recoil=1, casing=0.25), FX(muzzle=True, recoil=2, casing=0.5), FX(recoil=1, casing=0.75),
                   FX(casing=1.0)], 0.04)
        if not melee:
            self.noise(p.x, p.y)
        if target is None:
            self.shoot_straight(w)
            self.after_shot(w)
            self.end_beat()
            return False
        d = max(1, self.dist(target))
        hits = {}
        lo, hi = w.get("damage", [5, 10])
        if melee:
            if rng.random() < float(w.get("accuracy", 0.85)):
                hits[target] = rng.randint(lo, hi) * (3 if w.get("berserk") else 1)
        else:
            for _ in range(int(w.get("burst", 1))):
                for _ in range(int(w.get("pellets", 1))):
                    acc = (PELLET if w.get("pellets", 1) > 1 else ACCURACY)[min(d, 8)]
                    if rng.random() < acc:
                        hits[target] = hits.get(target, 0) + rng.randint(lo, hi)
                    elif d <= 2 and w.get("spread") and rng.random() < w["spread"]:
                        near = [m for m in self.monsters if not m.dead and m is not target
                                and abs(m.x - target.x) + abs(m.y - target.y) == 1]
                        if near:
                            m = rng.choice(near)
                            hits[m] = hits.get(m, 0) + rng.randint(lo, hi)
        dodge = float(target.spec.get("dodge", 0) or 0)
        if target in hits and dodge and target.awake and d >= 2 and not melee and rng.random() < dodge:
            rx_, ry_ = DIRS[(p.facing + 1) % 4]
            sides = [(target.x + rx_, target.y + ry_), (target.x - rx_, target.y - ry_)]
            rng.shuffle(sides)
            side = next(((x, y) for x, y in sides if self.free(x, y, skip=target)), None)
            if side is not None:                       # it saw the shot coming
                ox, oy = target.x, target.y
                target.x, target.y = side
                self.anim([FX(pos={target.id: (ox + (side[0] - ox) * k, oy + (side[1] - oy) * k)}) for k in (0.5, 0.85, 1.0)], 0.03)
                del hits[target]
                self.say("%s sidesteps your shot." % target.tag, "dim")
                self.update_seen()
        if target in hits:
            self.stats["hits"] += 1
            self.sfx((target.spec.get("sounds") or {}).get("hit") or (None if target.barrel else "hit_body"))
        elif not melee:
            self.sfx("hit_wall")                    # it flies past, into what is behind
        if not melee:                               # what missed goes on into the wall behind: a hole
            fired = int(w.get("burst", 1)) * int(w.get("pellets", 1))
            for _ in range(min(3, fired if target not in hits else fired // 3)):
                self.stray(target.x, target.y, 0.6 if w.get("pellets", 1) > 1 else 0.3)
        if hits:
            sound = w.get("text", {"melee": "THUD."}.get(w.get("kind"), "BLAM." if w.get("pellets", 1) > 1 else "BANG."))
            self.damage(sorted(hits.items(), key=lambda kv: kv[0] is not target), lead=sound)
            if (melee and w.get("stagger") and target in hits and not target.dead and not target.barrel
                    and not target.spec.get("boss")):                    # it reels: no aim, no step
                target.stun = max(target.stun, int(w["stagger"]))
                target.intent = None
            if ((int(w.get("pellets", 1)) > 1 or (melee and w.get("shove"))) and d == 1 and target in hits
                    and not target.dead and not target.barrel
                    and not target.spec.get("boss")):                    # point blank: the shotgun (or a shovel) shoves
                fx_, fy_ = DIRS[p.facing]
                if self.free(target.x + fx_, target.y + fy_, skip=target):
                    ox, oy = target.x, target.y
                    target.x, target.y = ox + fx_, oy + fy_
                    self.anim([FX(pos={target.id: (ox + fx_ * k, oy + fy_ * k)}) for k in (0.5, 0.85, 1.0)], 0.04)
                    self.say("%s is thrown back%s." % (target.tag, " into the acid" if self.cell(target.x, target.y).toxic else ""), "hit")
        else:
            self.say("You miss %s." % target.tag, "dim")
        self.after_shot(w)
        self.end_beat()
        return target in hits

    def after_shot(self, w):
        p = self.player
        if w.get("ammo") and p.ammo.get(w["ammo"], 0) <= 0:
            self.say("Out of %s." % w["ammo"], "alert")
            order = list(self.weapons)
            ready = [k for k in p.weapons if k in self.weapons and (not self.weapons[k].get("ammo")
                                                                     or p.ammo.get(self.weapons[k]["ammo"], 0) > 0)
                     and self.weapons[k].get("kind") not in ("rocket", "grenade")]   # never explosives by itself
            best = max(ready or ["1"], key=lambda k: (bool((self.weapons.get(k) or {}).get("ammo")),
                                                      order.index(k) if k in order else -1))
            self.switch(best)

    def shoot_straight(self, w):
        """A shot with nothing to aim at flies on until it meets a wall - maybe a hollow one."""
        p = self.player
        fx, fy = DIRS[p.facing]
        x, y = p.x, p.y
        for _ in range(fp.SIGHT + 2):
            x, y = x + fx, y + fy
            cell = self.cell(x, y)
            if cell.solid:
                if cell.kind == "panel" and cell.panel == "shoot":
                    self.open_panel(cell)
                else:
                    n = DIRS.index((-fx, -fy))
                    for _ in range(min(4, int(w.get("pellets", 1)) * int(w.get("burst", 1)))):
                        spread = 0.36 if w.get("pellets", 1) > 1 else 0.22
                        self.hole(x, y, n, self.vrng.uniform(-spread, spread), self.vrng.uniform(0.32, 0.62))
                    self.sfx("hit_wall")
                    self.say("Your shot hits the %s." % ("crate" if cell.crate else "door" if cell.kind == "door" else "wall"), "dim")
                    sparks = Bits(self.vrng).burst(x - fx * 0.52, y - fy * 0.52, 0.55, [(255, 230, 140), (255, 180, 60), (255, 255, 230)],
                                                   n=12, speed=0.9, up=1.2, size=0.6, toward=(-fx * 0.8, -fy * 0.8)).frames(4, 0.04)
                    self.anim([FX(parts=f) for f in sparks], 0.03)
                return
        self.say("You fire into the dark.", "dim")

    # ---- damage ------------------------------------------------------------ #
    def damage(self, hits, lead="", source=None):
        hits = [(m, d) for m, d in hits if not m.dead and not m.gone]
        if not hits:
            return
        turned = []
        asleep = [m for m, _ in hits if m.spec.get("boss") and not m.awake]
        if asleep:                                   # a boss's fight starts when the level says so
            for m in asleep:
                self.say((m.spec.get("asleep") or "%s does not notice. It is not time yet.") % m.name, "boss")
            hits = [(m, d) for m, d in hits if m not in asleep]
            if not hits:
                return
        for m, d in hits:
            m.hp -= d
            if not m.awake:
                self.wake(m, quiet=True)
            if (source is not None and not source.dead and m is not source and not m.barrel
                    and m.hp > 0 and m.grudge is not source and not m.spec.get("boss")):
                m.grudge = source
                turned.append(m)
        killed = [m for m, _ in hits if m.hp <= 0 and not (m.spec.get("boss") and m.spec.get("attack", {}).get("escape"))]
        burst = [m for m in killed if not m.barrel and (m.hp <= -15 or lead.startswith("The blast"))]
        text = ", ".join("%s takes %d" % (m.tag, d) for m, d in hits)
        self.say(("%s %s" % (lead, text)).strip(), "hit")
        ids = tuple(m.id for m, _ in hits)
        frames = [FX(flash=ids if i < 2 else (), texts=[(m, "-%d" % d, "hit", i) for m, d in hits]) for i in range(3)]
        dying = [m for m in killed if not m.barrel]
        gibs = Bits(self.vrng)
        for m in burst:                                      # overkill, or a blast: it comes apart
            pic = self.sprites.get(m.sprite)
            cols = [c for row in (pic.rows if pic else []) for c in row if c is not None][::3] or [(150, 20, 20)]
            gibs.burst(m.x, m.y, 0.6 * m.size, cols + [(150, 10, 10), (110, 0, 0)], n=22, speed=1.8, up=2.0, size=1.2)
        flying = gibs.frames(4, 0.05) if burst else [()] * 4
        for i, k in enumerate((0.25, 0.5, 0.75, 1.0) if dying else ()):
            frames.append(FX(dissolve={m.id: (1.0 if m in burst else k) for m in dying}, tint={m.id: (150, 8, 8) for m in dying},
                             texts=[(m, "-%d" % d, "hit", 3 + i) for m, d in hits], parts=flying[i]))
        self.anim(frames, 0.05)
        for m in turned:
            self.say("%s turns on %s!" % (m.tag, source.tag), "alert")
        for m in killed:
            self.kill(m)
        b = self.boss
        if b is not None and not b.dead and not b.gone and any(m is b for m, _ in hits):
            self.boss_hurt()

    def kill(self, m):
        if m.dead:
            return
        m.dead, m.intent = True, None
        if self.target is m:
            self.target = None
        for o in self.monsters:
            if o.grudge is m:
                o.grudge = None
        if m.barrel:
            self.explode(m)
            return
        if not m.spec.get("boss"):
            self.stats["kills"] += 1
        gore = self.sprites.get(m.spec.get("remains", "gore"))
        if gore is not None:
            self.decals.append((m.x, m.y, gore))
        if m.spec.get("burst_fire"):                   # its tanks burst: fire all round
            beats = int(m.spec["burst_fire"])
            for dx, dy in ((0, 0),) + DIRS:
                self.ignite(m.x + dx, m.y + dy, beats)
            self.say("Its tanks burst into flame.", "alert")
        self.say((m.spec.get("death") or "%s dies.") % m.tag, "good")
        self.sfx((m.spec.get("sounds") or {}).get("death") or "enemy_down")
        drop = m.spec.get("drops")
        if drop and drop in (self.data.items or {}) and not any(i.x == m.x and i.y == m.y and not i.taken
                                                                  for i in self.items):
            it = self.add_item(drop, m.x, m.y)
            if it is not None:
                self.total_items += 1
                self.anim([FX(lift_items={it: h}) for h in (0.45, 0.6, 0.45, 0.15, 0.05, 0.0)], 0.035)
        self.update_seen()

    def explode(self, b):
        self.say("%s explodes!" % b.tag, "alert")
        dmg = int((b.attack or {}).get("damage", 40)) if isinstance((b.attack or {}).get("damage"), int) else 40
        self.blast(b.x, b.y, dmg, by=b, colours=[(70, 74, 82), (40, 120, 40), (255, 160, 40), (255, 220, 120)])

    def blast(self, x, y, dmg, by=None, lead="The blast:", colours=None):
        """An explosion - a barrel's, a rocket's, a grenade's: everything within a cell takes ``dmg`` (the player
        three quarters of it), crates and monsters are thrown a cell away, oil next to it catches fire, other
        grenades next to it go off, and the floor is left scorched."""
        self.sfx("explosion")
        bits = Bits(self.vrng).burst(x, y, 0.3, colours or [(90, 88, 84), (60, 58, 56), (255, 160, 40), (255, 220, 120)],
                                     n=26, speed=2.4, up=2.2, size=1.1).frames(7, 0.045)
        self.anim([FX(booms=[(x, y, k)], shake=(1 if i % 2 else -1) if k < 0.5 else 0, parts=bits[i])
                   for i, k in enumerate((0.0, 0.12, 0.25, 0.4, 0.55, 0.7, 0.85))], 0.045)
        self.noise(x, y)
        p = self.player
        victims = [(m, dmg) for m in self.monsters if not m.dead and not m.gone and m is not by
                   and max(abs(m.x - x), abs(m.y - y)) <= 1]
        if victims:
            self.damage(victims, lead=lead)
        self.blast_push(x, y)
        here = self.cell(x, y)
        if here.kind == "floor" and not here.toxic and not here.solid and not here.scorched:
            here.scorched = True                         # a black mark that stays
            self.marks_version += 1
        self.ignite(x, y, 2)
        for dx, dy in DIRS:
            if self.cell(x + dx, y + dy).oil:
                self.ignite(x + dx, y + dy, 2)
        if max(abs(p.x - x), abs(p.y - y)) <= 1 and not self.over:
            self.hurt(int(dmg * 0.75), "The blast catches you.", by=by)
        near = [g for g in self.grenades if max(abs(g.x - x), abs(g.y - y)) <= 1]
        for g in near:                                   # it sets the grenades next to it off
            if g in self.grenades and not self.over:
                self.grenades.remove(g)
                self.blast(g.x, g.y, g.blast, lead="Another grenade:")

    # ---- rockets, grenades, holes ------------------------------------------ #
    def line_ahead(self, target, n):
        """The cells a missile flies through: towards the target and on past it, or straight ahead."""
        p = self.player
        if target is None:
            fx, fy = DIRS[p.facing]
            return [(p.x + fx * i, p.y + fy * i) for i in range(1, n + 1)]
        path = bresenham(p.x, p.y, target.x, target.y)[1:]
        dx, dy = target.x - p.x, target.y - p.y
        k = max(abs(dx), abs(dy)) or 1
        for i in range(1, n):
            path.append((target.x + int(round(dx / float(k) * i)), target.y + int(round(dy / float(k) * i))))
        return path[:n]

    def launch(self, w, target):
        """A rocket flies along the line until it meets a monster, a barrel or a wall, and bursts there:
        the one it hits takes ``damage``, everything within a cell ``blast`` - you too, if you are that close."""
        p = self.player
        self.sfx(w.get("sound") or "rocket")
        path = self.line_ahead(target, fp.SIGHT + 4)
        at, hit, prev = None, None, (p.x, p.y)
        for (x, y) in path:
            if self.cell(x, y).solid:
                at = prev                                # it bursts against the wall's face
                break
            m = self.monster_at(x, y)
            if m is not None:
                at, hit = (x, y), m
                break
            prev = (x, y)
        way = [(p.x, p.y)] + (path[:path.index(at) + 1] if at in path else (path if at is None else []))
        if len(way) > 1:
            n = max(2, int(round(len(way) * 1.5)))
            smoke, frames = [], []
            for i in range(1, n + 1):
                x, y = self.along(way, i / float(n))
                smoke = [(sx, sy, h + 0.03, (min(255, c[0] + 6),) * 3, size) for sx, sy, h, c, size in smoke][-14:]
                smoke.append((x - 0.2 * DIRS[p.facing][0], y - 0.2 * DIRS[p.facing][1], 0.5,
                               (130, 128, 124), 0.8))
                frames.append(FX(missiles=[(x, y, 0.5, "rocket", (255, 150, 50))], parts=list(smoke),
                                 muzzle=i <= 1, recoil=2 if i <= 2 else 0))
            self.anim(frames, 0.03)
        if at is None:
            self.say("%s The rocket streaks off into the dark." % w.get("text", "FWOOSH."), "dim")
            return
        if at == (p.x, p.y):
            self.say("You fire a rocket into the wall at arm's length.", "alert")
        if hit is not None:
            lo, hi = w.get("damage", [30, 50])
            self.stats["hits"] += 1
            self.damage([(hit, self.rng.randint(lo, hi))], lead="%s The rocket hits:" % w.get("text", "FWOOSH."))
            if hit.barrel and hit.dead:
                return                                   # it set the barrel off: that was the blast
        elif at != (p.x, p.y):
            self.say("%s The rocket bursts on the wall." % w.get("text", "FWOOSH."), "hit")
        if not self.over:
            self.blast(at[0], at[1], int(w.get("blast", 40)))

    def lob(self, w, target):
        """A grenade, thrown in an arc ``range`` cells ahead (or as far as the one aimed at): off a wall it
        bounces back, before a monster it drops; on slick floor it slides on, on a belt it rides, and when
        its ``fuse`` (beats) is out it goes off."""
        p = self.player
        fx, fy = DIRS[p.facing]
        reach = int(w.get("range", 3))
        if target is not None:
            a, z = self.rel(target.x, target.y)
            if 1 <= z <= reach + 1:
                reach = z
        x, y, dx, dy, left, notes = p.x, p.y, fx, fy, reach, []
        way = [(x, y)]
        while left > 0:
            nx, ny = x + dx, y + dy
            if self.cell(nx, ny).solid:
                dx, dy, left = -dx, -dy, left - 1        # off the wall, back the way it came
                notes.append("bounces off the %s" % ("crate" if self.cell(nx, ny).crate else "wall"))
                self.sfx("bounce", "hit_wall")
                continue
            m = self.monster_at(nx, ny)
            if m is not None and not m.float:
                notes.append("drops at %s's feet" % m.tag)
                break
            x, y, left = nx, ny, left - 1
            way.append((x, y))
        slid = self.slide_path(x, y, dx, dy) if (x, y) != (p.x, p.y) else []
        if slid:
            notes.append("skids on along the %s" % ("oil" if self.cell(x, y).oil else "slick floor"))
        n = max(3, 3 * (len(way) - 1))
        frames = []
        for i in range(1, n + 1):
            k = i / float(n)
            gx, gy = self.along(way, k) if len(way) > 1 else way[0]
            frames.append(FX(missiles=[(gx, gy, 0.45 * (1 - k) + 1.1 * k * (1 - k), "grenade", None)],
                             recoil=-2 if i <= 2 else 0))
        for i, k in enumerate((0.34, 0.67, 1.0) * (1 if slid else 0)):
            gx, gy = self.along([(x, y)] + slid, k)
            frames.append(FX(missiles=[(gx, gy, 0.0, "grenade", None)]))
        self.anim(frames, 0.035)
        if slid:
            x, y = slid[-1]
        g = Grenade(x, y, int(w.get("fuse", 2)), int(w.get("blast", 50)))
        self.grenades.append(g)
        where = "at your feet!" if (x, y) == (p.x, p.y) else "%d cell%s away." % (
            max(abs(x - p.x), abs(y - p.y)), "" if max(abs(x - p.x), abs(y - p.y)) == 1 else "s")
        self.say("%s The grenade %slands %s" % (w.get("text", "Tink."), "".join(t + ", " for t in notes), where),
                 "alert" if (x, y) == (p.x, p.y) else "dim")

    def fuses(self):
        """Grenades' fuses burn down a beat; the ones out go off."""
        for g in list(self.grenades):
            g.fuse -= 1
        for g in [g for g in self.grenades if g.fuse <= 0]:
            if g in self.grenades and not self.over:
                self.grenades.remove(g)
                self.blast(g.x, g.y, g.blast, lead="The grenade:")

    def hole(self, x, y, n, along, down):
        """A bullet hole in the face of wall (x, y) turned towards ``DIRS[n]``: ``along`` it (-0.5..0.5,
        sideways in the direction ``DIRS[n + 1]``) and ``down`` it (0 at the top, 1 at the floor)."""
        c = self.cell(x, y)
        if c.kind not in ("wall", "panel", "exit") or c.crate or c is VOID:
            return
        self.holes.append((x, y, n, max(-0.45, min(0.45, along)), max(0.05, min(0.95, down))))
        del self.holes[:-HOLES]

    def stray(self, tx, ty, spread=0.3):
        """A shot that missed (tx, ty) goes on behind it: a hole where it meets a wall (within 14 cells)."""
        p, r = self.player, self.vrng
        dx, dy = tx - p.x + r.uniform(-spread, spread), ty - p.y + r.uniform(-spread, spread)
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        px_, py_ = float(p.x), float(p.y)
        cx, cy = p.x, p.y
        for i in range(1, 14 * 16):
            x, y = p.x + ux * i / 16.0, p.y + uy * i / 16.0
            ix, iy = int(math.floor(x + 0.5)), int(math.floor(y + 0.5))
            if (ix, iy) != (cx, cy):
                if self.cell(ix, iy).solid:
                    if ix != cx and iy != cy:                # through a corner: the face that is open
                        ix, iy = (ix, cy) if self.cell(ix, cy).solid else (cx, iy)
                    if ix != cx:
                        n = DIRS.index((1 if cx > ix else -1, 0))
                        face = ix + 0.5 * DIRS[n][0]
                        y = py_ + uy * (face - px_) / ux if ux else y
                        along = (y - iy) * DIRS[(n + 1) % 4][1]
                    else:
                        n = DIRS.index((0, 1 if cy > iy else -1))
                        face = iy + 0.5 * DIRS[n][1]
                        x = px_ + ux * (face - py_) / uy if uy else x
                        along = (x - ix) * DIRS[(n + 1) % 4][0]
                    self.hole(ix, iy, n, along, r.uniform(0.34, 0.6))
                    return
                cx, cy = ix, iy

    def blast_push(self, x0, y0):
        """A blast throws crates and monsters next to it a cell further away, if there is room."""
        sign = lambda v: (v > 0) - (v < 0)                    # noqa: E731
        moved, slid = [], {}
        for c in [self.cell(x, y) for y in range(y0 - 1, y0 + 2) for x in range(x0 - 1, x0 + 2)]:
            if not c.crate or c.heavy:
                continue
            dx, dy = sign(c.x - x0), sign(c.y - y0)
            t = self.cell(c.x + dx, c.y + dy)
            if (dx or dy) and not t.solid and not self.monster_at(t.x, t.y) and (t.x, t.y) != (self.player.x, self.player.y):
                c.crate = False
                if t.toxic:
                    t.toxic, t.sunk = False, True
                    self.marks_version += 1
                else:
                    t.crate = True
                    slid[(t.x, t.y)] = (c.x, c.y)
        for m in self.monsters:
            if m.dead or m.gone or m.barrel or m.spec.get("boss") or max(abs(m.x - x0), abs(m.y - y0)) > 1:
                continue
            dx, dy = sign(m.x - x0), sign(m.y - y0)
            if (dx or dy) and self.free(m.x + dx, m.y + dy, skip=m):
                moved.append((m, m.x, m.y))
                m.x, m.y = m.x + dx, m.y + dy
        if moved or slid:
            self.anim([FX(pos={m.id: (ox + (m.x - ox) * k, oy + (m.y - oy) * k) for m, ox, oy in moved},
                          crates={xy: (o[0] + (xy[0] - o[0]) * k, o[1] + (xy[1] - o[1]) * k) for xy, o in slid.items()})
                       for k in (0.4, 0.75, 1.0)], 0.04)
            for m, _x, _y in moved:
                self.say("%s is thrown back%s." % (m.tag, " into the acid" if self.cell(m.x, m.y).toxic else ""), "hit")
            self.plates()

    def acid(self):
        """A beat on toxic floor: it wears the boots down, or burns."""
        p = self.player
        if p.vehicle is not None and p.vehicle.vehicle.get("wades", True):
            return                                       # steel feet
        if p.boots:
            p.boots -= 1
            if not p.boots:
                self.say("The acid has eaten through your boots.", "alert")
            elif p.boots == 5:
                self.say("Your boots are wearing thin: 5 more beats in acid.", "alert")
            elif not self.boots_said:
                self.say("The rubber hisses. Your boots hold.", "toxic")
            self.boots_said = True
            return
        self.sfx("acid_burn")
        self.hurt(int(self.cfg.get("toxic_damage", 5)), "The floor burns through your boots.")

    def hurt(self, dmg, text, by=None):
        p = self.player
        if p.sudo:
            self.say(text + "  (root shrugs it off)", "root")
            return
        v = p.vehicle
        if v is not None:                                # the machine takes it
            v.hp -= dmg
            self.say("%s  The %s takes %d (%d left)" % (text, v.name, dmg, max(0, v.hp)), "hurt")
            self.sfx("hit_wall")
            self.anim([FX(shake=s, hurt=h) for s, h in ((1, 0.25), (-1, 0.12), (0, 0.0))], 0.05)
            self.interrupt = self.interrupt or "the loader was hit"
            if v.hp <= 0:
                self.wreck()
            elif v.hp <= 40 and v.hp + dmg > 40:
                self.say("The %s's hydraulics are failing. Get out before it goes." % v.name, "alert")
            return
        if p.armor:
            saved = min(p.armor, dmg // 3)
            p.armor -= saved
            dmg -= saved
        p.hp = max(0, p.hp - dmg)
        self.stats["taken"] += dmg
        self.say("%s  -%d" % (text, dmg), "hurt")
        self.sfx("hurt")
        where = None
        if by is not None:
            a, z = self.rel(by.x, by.y)
            if not (z >= 1 and abs(a) <= z + 0.5):
                where = "back" if z <= 0 and abs(a) <= abs(z) else ("left" if a < 0 else "right")
        k = min(1.0, 0.25 + dmg / 36.0)
        lunge = by is not None and self.dist(by) <= 1 and not by.barrel
        self.anim([FX(hurt=h * k, hurt_dir=where, shake=s, lunge={by.id: 1.2} if lunge and h > 0.5 else {})
                   for h, s in ((1.0, 1), (0.7, -1), (0.4, 1), (0.15, 0))], 0.05)
        self.interrupt = self.interrupt or "you were hit"
        if p.hp <= 0:
            self.over = "dead"

    # ---- waking ------------------------------------------------------------ #
    def noise(self, x, y):
        self.noise_at = (x, y)

    def wake(self, m, quiet=False):
        if m.awake or m.barrel:
            return
        m.awake = True
        if not quiet and m.seen:
            self.say("%s notices you." % m.tag, "alert")
            self.interrupt = self.interrupt or "%s is awake" % m.tag
        self.sfx((m.spec.get("sounds") or {}).get("sight"))
        if m is self.boss:
            self.boss_wakes()

    def event(self, name):
        if name in self.events:
            return
        self.events.add(name)
        opened = closed = 0
        for row in self.grid:
            for c in row:
                if c.closes_on == name and c.kind == "door" and c.open >= 1.0:
                    c.open, c.sealed = 0.0, True
                    closed += 1
                if c.opens_on == name:
                    if c.kind == "door":
                        c.sealed = False
                        c.open = 1.0
                    else:
                        c.kind = "floor"
                    opened += 1
        text = (self.spec.get("events") or {}).get(name)
        if text:
            self.say(text, "alert")
        elif closed:
            self.say("A door slams shut behind you.", "alert")
        elif opened:
            self.say("Somewhere, walls grind open.", "alert")
        for m in self.monsters:
            if m.wake_on == name and not m.dead:
                self.wake(m, quiet=True)
        if closed or opened:
            self.sfx("door")
            self.update_seen()
            self.anim([FX(shake=s) for s in (1, -1, 0)], 0.05)
        self.interrupt = self.interrupt or "something moved"

    # ---- the world's beat -------------------------------------------------- #
    def end_beat(self):
        if self.over:
            return
        self.beat += 1
        p = self.player
        self.fly()
        if self.over:
            return
        self.wake_up()
        self.moved, self.queue = [], []
        for m in list(self.monsters):
            if not m.dead and not m.gone and m.awake and not m.barrel:
                self.act(m)
        if self.moved:
            self.anim([FX(pos={m.id: (x0 + (m.x - x0) * ease(i / 3.0), y0 + (m.y - y0) * ease(i / 3.0))
                               for m, x0, y0 in self.moved}) for i in range(1, 4)], 0.04)
            for m, _x, _y in self.moved:                # monsters use teleporters too
                c = self.cell(m.x, m.y)
                if c.teleport and not c.arrive_only and not m.dead:
                    self.monster_teleport(m, c)
        for job in self.queue:
            if self.over:
                return
            job()
        if self.boss is not None and self.boss.awake and not self.boss.dead and not self.boss.gone:
            self.boss_beat()
        self.convey()
        if self.over:
            return
        self.fuses()
        if self.over:
            return
        self.plates()
        self.burn()
        if self.over:
            return
        burning = [(m, int(self.cfg.get("toxic_damage", 5))) for m in self.monsters if not m.dead and not m.gone
                   and not m.float and not m.spec.get("boss") and self.cell(m.x, m.y).toxic
                   and not (m.vehicle and m.vehicle.get("wades", True))]
        if burning and not self.over:
            self.damage(burning, lead="The acid:")
        cell = self.cell(p.x, p.y)
        if cell.toxic and not self.over:
            self.acid()
        if p.nightvision:
            p.goggles -= 1
            if not p.goggles:
                p.goggles_on = False
                self.say("The goggles flicker out. Colours come back.", "dim")
            elif p.goggles == 5:
                self.say("The goggles' battery is low: 5 more beats. (goggles off saves it)", "alert")
        if p.sudo:
            p.sudo -= 1
            if not p.sudo:
                self.say("Root has expired. You are rootless again.", "dim")
        self.noise_at = None
        self.update_seen()
        if p.hp <= 0:
            self.over = "dead"

    def monster_teleport(self, m, pad):
        group = [c for c in self.pads if c.teleport == pad.teleport]
        others = group[group.index(pad) + 1:] + group[:group.index(pad)]
        p = self.player
        dest = next((c for c in others if not c.crate and self.monster_at(c.x, c.y) is None and (c.x, c.y) != (p.x, p.y)), None)
        if dest is None:
            return
        seen = m.seen
        m.x, m.y = dest.x, dest.y
        self.update_seen()
        if seen or m.seen:
            self.say("%s %s in a flash of dots." % (m.tag, "vanishes" if seen and not m.seen else "appears"), "secret")
            self.sfx("teleport")
            self.interrupt = self.interrupt or "%s teleported" % m.tag

    # ---- fire, belts --------------------------------------------------------- #
    def ignite(self, x, y, beats=3):
        """Set a cell burning (not walls; not acid): oil burns longer, and spreads it."""
        c = self.cell(x, y)
        if c.solid and not c.crate or c.toxic or c.kind not in ("floor", "door") or (c.kind == "door" and c.open < 1):
            return False
        beats += 2 if c.oil else 0
        if self.fires.get((x, y), 0) < beats:
            self.fires[(x, y)] = beats
            self.marks_version += 1
        return True

    def burn(self):
        """What stands in fire burns; barrels in it go off; fire runs along oil, and dies down."""
        if not self.fires:
            return
        p = self.player
        dmg = int(self.cfg.get("fire_damage", 6))
        if (p.x, p.y) in self.fires:
            self.sfx("fire_burn", "hurt")
            self.hurt(dmg, "You are standing in fire!", by=None)
            if self.over:
                return
        caught = [(m, 99 if m.barrel and not m.vehicle else dmg) for m in self.monsters if not m.dead and not m.gone and not m.float
                  and not m.spec.get("boss") and (m.x, m.y) in self.fires]
        if caught:
            self.damage(caught, lead="The fire:")
        spread = {}
        for (x, y), left in list(self.fires.items()):
            c = self.cell(x, y)
            if c.oil:
                for dx, dy in DIRS:
                    n = self.cell(x + dx, y + dy)
                    if n.oil and (n.x, n.y) not in self.fires:
                        spread[(n.x, n.y)] = 4
            if left <= 1:
                del self.fires[(x, y)]
                if c.oil:
                    c.oil = c.slick = False
                    c.scorched = True
            else:
                self.fires[(x, y)] = left - 1
        for xy, beats in spread.items():
            self.fires[xy] = beats
        if spread and any(self.cell(*xy).x is not None for xy in spread):
            near = [xy for xy in spread if max(abs(xy[0] - p.x), abs(xy[1] - p.y)) <= 8]
            if near:
                self.say("Fire runs along the oil.", "alert")
        self.marks_version += 1

    def convey(self):
        """Belts move what is on them - the player, crates, barrels, monsters, items - a cell a beat, if there is room."""
        if not self.belts:
            return
        p = self.player
        moves, crates, items = [], {}, []
        cam = None
        order = sorted(self.belts, key=lambda c: -(c.x * DIRS[c.conveyor][0] + c.y * DIRS[c.conveyor][1]))
        for c in order:
            dx, dy = DIRS[c.conveyor]
            tx, ty = c.x + dx, c.y + dy
            m = self.monster_at(c.x, c.y)
            if (p.x, p.y) == (c.x, c.y):
                if self.room(tx, ty):
                    cam = ((p.x, p.y), (tx, ty))
                    p.x, p.y = tx, ty
            elif c.crate:
                if self.room(tx, ty, crate=True):
                    heavy = c.heavy
                    c.crate = c.heavy = False
                    t = self.cell(tx, ty)
                    if t.toxic:
                        t.toxic, t.sunk = False, True
                        self.marks_version += 1
                    else:
                        t.crate, t.heavy = True, heavy
                        crates[(tx, ty)] = (c.x, c.y)
            elif m is not None and not m.float and not m.spec.get("boss"):
                if self.room(tx, ty):
                    moves.append((m, m.x, m.y))
                    m.x, m.y = tx, ty
            for it in self.items:
                if not it.taken and (it.x, it.y) == (c.x, c.y) and not self.cell(tx, ty).solid:
                    items.append((it, it.x, it.y))
                    it.x, it.y = tx, ty
            for g in self.grenades:                      # a grenade rides a belt, its fuse burning
                if (g.x, g.y) == (c.x, c.y) and not self.cell(tx, ty).solid and g not in items:
                    items.append(g)
                    g.x, g.y = tx, ty
        if moves or crates or cam or items:
            self.anim([FX(cam=(cam[0][0] + (cam[1][0] - cam[0][0]) * k, cam[0][1] + (cam[1][1] - cam[0][1]) * k) if cam else None,
                          pos={m.id: (x0 + (m.x - x0) * k, y0 + (m.y - y0) * k) for m, x0, y0 in moves},
                          crates={xy: (o[0] + (xy[0] - o[0]) * k, o[1] + (xy[1] - o[1]) * k) for xy, o in crates.items()})
                       for k in (0.33, 0.66, 1.0)], 0.04)
            if cam:
                self.say("The belt carries you on.", "dim")
                self.update_seen()
                self.arrive()

    def wake_up(self):
        p = self.player
        heard = self.distances(*self.noise_at, limit=12) if self.noise_at else {}
        for m in self.monsters:
            if m.awake or m.dead or m.gone or m.barrel or m.wake_on:
                continue
            near = max(abs(m.x - p.x), abs(m.y - p.y)) <= int(m.spec.get("sight", 8))
            if (near and self.line_of_sight(m.x, m.y, p.x, p.y)) or (m.x, m.y) in heard:
                self.wake(m)

    def fly(self):
        if not self.shots:
            return
        p = self.player
        moves = []
        for s in self.shots:
            steps = s.path[s.i + 1: s.i + 1 + s.speed]
            end = steps[-1] if steps else (s.x, s.y)
            moves.append((s, (s.x, s.y), end))
        self.anim([FX(shots=[(a[0] + (b[0] - a[0]) * i / 4.0, a[1] + (b[1] - a[1]) * i / 4.0)
                             for _s, a, b in moves]) for i in range(1, 5)], 0.035)
        for s, _a, _b in moves:
            if s not in self.shots:
                continue
            for _ in range(s.speed):
                s.i += 1
                if s.i >= len(s.path):
                    self.shots.remove(s)
                    self.say("Fire splashes on the floor.", "dim")
                    break
                s.x, s.y = s.path[s.i]
                if self.cell(s.x, s.y).solid:
                    self.shots.remove(s)
                    break
                if (s.x, s.y) == (p.x, p.y):
                    self.shots.remove(s)
                    self.hurt(self.rng.randint(*s.damage), "Fire from %s hits you." % s.owner.tag, by=s.owner)
                    break
                victim = self.monster_at(s.x, s.y, skip=s.owner)
                if victim is not None:
                    self.shots.remove(s)
                    src = s.owner if not s.owner.dead else None
                    self.damage([(victim, self.rng.randint(*s.damage))], lead="Fire from %s:" % s.owner.tag, source=src)
                    break
            if self.over:
                return

    def move_mob(self, m, x, y):
        if not self.free(x, y, skip=m):
            return False
        self.moved.append((m, m.x, m.y))
        m.x, m.y = x, y
        m.stride += 1
        return True

    def step_towards(self, m, field, away=False):
        best, here = None, field.get((m.x, m.y), 999)
        options = [(m.x + dx, m.y + dy) for dx, dy in DIRS]
        self.rng.shuffle(options)
        for (x, y) in options:
            if not self.free(x, y, skip=m):
                continue
            d = field.get((x, y), 999)
            if (d > here) if away else (d < here):
                if best is None or ((d > best[0]) if away else (d < best[0])):
                    best = (d, x, y)
        if best is not None:
            return self.move_mob(m, best[1], best[2])
        return False

    def act(self, m):
        p, rng = self.player, self.rng
        a = m.attack
        kind = a.get("kind", "melee")
        if kind == "cron":
            return
        m.cool = max(0, m.cool - 1)
        if m.stun:                                      # still reeling: no aim, no step
            m.stun -= 1
            m.intent = None
            m.spin, m.spun = 0, False
            return
        if m.grudge is not None and (m.grudge.dead or m.grudge.gone):
            m.grudge = None
        foe = m.grudge
        tx, ty = (foe.x, foe.y) if foe else (p.x, p.y)
        d = max(abs(m.x - tx), abs(m.y - ty))
        adjacent = abs(m.x - tx) + abs(m.y - ty) == 1
        los = self.line_of_sight(m.x, m.y, tx, ty)
        reach = int(a.get("range", 8))
        if not hasattr(self, "_field") or self._field[0] != (tx, ty, self.beat):
            self._field = ((tx, ty, self.beat), self.distances(tx, ty))
        field = self._field[1]
        every = int(a.get("move_every", 1) or 1)
        still = every > 1 and (self.beat + m.id) % every != 0          # a heavy one moves every other beat
        if kind == "hitscan" and a.get("spinup"):
            if los and d <= reach:
                if m.spun:
                    m.intent = "spin"
                    self.queue.append(lambda: self.ranged(m, foe, d))
                    return
                m.spin += 1
                m.intent = "spin"
                if m.spin == 1 and m.seen:
                    self.say("%s's barrels start to spin." % m.tag, "aim")
                    self.sfx((m.spec.get("sounds") or {}).get("spinup") or "spinup")
                    self.interrupt = self.interrupt or "%s spins up" % m.tag
                if m.spin >= int(a["spinup"]):
                    m.spun = True
                return
            if m.spin or m.spun:
                if m.seen:
                    self.say("%s's barrels wind down." % m.tag, "dim")
                m.spin, m.spun, m.intent = 0, False, None
            if not still:
                self.step_towards(m, field)
            return
        if kind == "flame":
            lined = (m.x == tx or m.y == ty) and d <= reach and los
            if m.intent == "windup":
                m.intent, m.cool = None, int(a.get("cool", 1))
                if lined:
                    self.queue.append(lambda: self.flame(m, foe))
                return
            if lined and not m.cool and rng.random() < float(a.get("eager", 0.7)):
                m.intent = "windup"
                if m.seen:
                    self.say("%s levels its nozzle." % m.tag, "wind")
                    self.sfx((m.spec.get("sounds") or {}).get("windup"))
                return
            if not still:                               # get in line with the target, close enough to reach it
                options = [(m.x + dx, m.y + dy) for dx, dy in DIRS]
                rng.shuffle(options)
                best = None
                for (x, y) in options + [(m.x, m.y)]:
                    if (x, y) != (m.x, m.y) and not self.free(x, y, skip=m):
                        continue
                    dd = max(abs(x - tx), abs(y - ty))
                    line = (x == tx or y == ty) and 1 <= dd <= reach
                    score = (0 if line else 1, field.get((x, y), 999) if not line else -dd)
                    if best is None or score < best[0]:
                        best = (score, x, y)
                if best and (best[1], best[2]) != (m.x, m.y):
                    self.move_mob(m, best[1], best[2])
            return
        if kind in ("hitscan", "projectile"):
            if m.intent in ("aim", "windup"):
                m.intent, m.cool = None, int(a.get("cool", 1))
                if los:
                    self.queue.append(lambda: (self.ranged(m, foe, d) if kind == "hitscan" else self.throw(m, foe)))
                return
            if adjacent and a.get("claw"):
                self.queue.append(lambda: self.bite(m, foe, a.get("claw")))
                return
            if los and d <= reach and not m.cool and rng.random() < float(a.get("eager", 0.55)):
                m.intent = "aim" if kind == "hitscan" else "windup"
                if m.seen:
                    self.say(("%s takes aim." if kind == "hitscan" else "%s raises a burning hand.") % m.tag,
                             "aim" if kind == "hitscan" else "wind")
                if kind == "projectile":
                    self.sfx((m.spec.get("sounds") or {}).get("windup"))
                return
            keep = a.get("keep", [2, reach])
            if still:
                pass
            elif not los or d > keep[1]:
                self.step_towards(m, field)
            elif d < keep[0]:
                self.step_towards(m, field, away=True)
            elif rng.random() < 0.3:
                self.step_towards(m, {(x, y): 0 for x, y in [(m.x + dx, m.y + dy) for dx, dy in DIRS]}, away=False)
        elif kind == "melee":
            if adjacent:
                self.queue.append(lambda: self.bite(m, foe, a.get("damage", [10, 18])))
                return
            for _ in range(int(a.get("speed", 1))):
                if not self.step_towards(m, field):
                    break
                if abs(m.x - tx) + abs(m.y - ty) == 1:
                    break
            if d <= 3 and m.intent != "charge" and not foe:
                m.intent = "charge"
                if m.seen:
                    self.say("%s charges!" % m.tag, "charge")
        elif kind == "spawner":
            m.clock += 1
            spawn = a.get("spawn")
            alive = [c for c in self.monsters if c.owner is m and not c.dead]
            if los and m.clock % int(a.get("every", 4)) == 0 and len(alive) < int(a.get("max", 3)) and spawn:
                self.queue.append(lambda: self.spawn(m, spawn, 1))
                return
            keep = a.get("keep", [3, 6])
            if m.clock % 2 == 0:
                if not los or d > keep[1]:
                    self.step_towards(m, field)
                elif d < keep[0]:
                    self.step_towards(m, field, away=True)

    def ranged(self, m, foe, d):
        if m.dead or m.gone:
            return
        a = m.attack
        self.anim([FX(emuzzle=(m.id,)), FX(emuzzle=(m.id,)), FX()], 0.04)
        self.sfx((m.spec.get("sounds") or {}).get("attack") or "pistol")
        lo, hi = a.get("damage", [5, 10])
        pellets = int(a.get("pellets", 1))
        if foe is not None and not foe.dead:
            total = sum(self.rng.randint(lo, hi) for _ in range(pellets))
            self.damage([(foe, total)], lead="%s shoots %s:" % (m.tag, foe.tag), source=m)
            return
        acc = a.get("accuracy") or [0.9, 0.85, 0.75, 0.62, 0.5, 0.42, 0.36, 0.3, 0.26]
        total = 0
        for _ in range(pellets):
            if self.rng.random() < acc[min(d, len(acc) - 1)]:
                total += self.rng.randint(lo, hi)
        if total:
            self.hurt(total, "%s shoots you." % m.tag, by=m)
        else:
            self.sfx("fly_by")
            self.say("%s's shot goes wide." % m.tag, "dim")

    def flame(self, m, foe):
        """A flamethrower's spray: every cell in its line, to its reach, catches fire; what stands there burns now."""
        if m.dead or m.gone:
            return
        p = self.player
        a = m.attack
        tx, ty = (foe.x, foe.y) if foe else (p.x, p.y)
        dx, dy = (tx > m.x) - (tx < m.x), (ty > m.y) - (ty < m.y)
        if dx and dy:
            return
        cells = []
        x, y = m.x, m.y
        for _ in range(int(a.get("range", 3))):
            x, y = x + dx, y + dy
            if self.cell(x, y).solid and not self.cell(x, y).crate:
                break
            cells.append((x, y))
            if self.cell(x, y).crate:
                break
        self.sfx((m.spec.get("sounds") or {}).get("attack") or "flame")
        bits = Bits(self.vrng)
        for i, (x, y) in enumerate(cells):
            bits.burst(m.x + dx * 0.6, m.y + dy * 0.6, 0.45, [(255, 200, 70), (255, 120, 30), (255, 240, 170)],
                       n=8, speed=0.6, up=0.4, size=1.4, toward=(dx * (3.0 + i), dy * (3.0 + i)))
        self.anim([FX(emuzzle=(m.id,), parts=f) for f in bits.frames(5, 0.05)], 0.04)
        if m.seen:
            self.say("%s sprays fire%s!" % (m.tag, " at " + foe.tag if foe else ""), "wind")
        lo, hi = a.get("damage", [8, 14])
        victims = []
        for (x, y) in cells:
            self.ignite(x, y, int(a.get("burn", 3)))
            o = self.monster_at(x, y, skip=m)
            if o is not None:
                victims.append((o, self.rng.randint(lo, hi)))
            if (x, y) == (p.x, p.y) and not self.over:
                self.hurt(self.rng.randint(lo, hi), "%s's fire washes over you." % m.tag, by=m)
        if victims and not self.over:
            self.damage(victims, lead="%s's fire:" % m.tag, source=m)
        self.interrupt = self.interrupt or "fire"

    def throw(self, m, foe):
        if m.dead or m.gone:
            return
        p = self.player
        tx, ty = (foe.x, foe.y) if foe else (p.x, p.y)
        path = bresenham(m.x, m.y, tx, ty)
        # carry the line on past the target, so it can fly by
        dx, dy = tx - m.x, ty - m.y
        for k in range(1, 6):
            path.append((tx + int(round(dx / max(1, max(abs(dx), abs(dy))) * k)),
                         ty + int(round(dy / max(1, max(abs(dx), abs(dy))) * k))))
        a = m.attack
        self.shots.append(Shot(path, m, tuple(a.get("damage", [14, 20])), int(a.get("speed", 1))))
        self.sfx((m.spec.get("sounds") or {}).get("attack") or "zap")
        if m.seen:
            self.say("%s hurls fire%s!" % (m.tag, " at " + foe.tag if foe else ""), "wind")
        self.interrupt = self.interrupt or "fire coming"

    def bite(self, m, foe, dmg):
        if m.dead or m.gone:
            return
        lo, hi = dmg
        if foe is not None and not foe.dead:
            if abs(foe.x - m.x) + abs(foe.y - m.y) == 1:
                self.damage([(foe, self.rng.randint(lo, hi))], lead="%s tears into %s:" % (m.tag, foe.tag), source=m)
            return
        p = self.player
        if abs(p.x - m.x) + abs(p.y - m.y) == 1:
            self.sfx((m.spec.get("sounds") or {}).get("attack") or "hit")
            self.hurt(self.rng.randint(lo, hi), (m.spec.get("bite") or "%s bites you.") % m.tag, by=m)

    def spawn(self, m, kind, count):
        made = []
        cells = [(m.x + dx, m.y + dy) for dx, dy in DIRS + ((1, 1), (-1, 1), (1, -1), (-1, -1))]
        self.rng.shuffle(cells)
        for (x, y) in cells:
            if len(made) >= count:
                break
            if self.free(x, y):
                c = self.add_monster(kind, x, y)
                if c is not None:
                    c.owner, c.awake = m, True
                    made.append(c)
        if made:
            self.total_kills += len(made)
            self.update_seen()
            self.say("%s spawns %s." % (m.tag, ", ".join(c.tag for c in made)), "alert")
            self.sfx((m.spec.get("sounds") or {}).get("spawn") or "teleport")
            self.anim([FX(dissolve={c.id: k for c in made}) for k in (0.9, 0.7, 0.45, 0.2)], 0.06)
            self.interrupt = self.interrupt or "something new"

    # ---- Cron ---------------------------------------------------------------- #
    def boss_wakes(self):
        b = self.boss
        b.clock = 0
        a = b.attack
        self.arena = set(self.distances(b.x, b.y, limit=int(a.get("arena", 6))))
        self.say(a.get("wake_text", "%s wakes." % b.name), "boss")
        self.music(b.spec.get("music"))

    def crontab(self):
        b = self.boss
        a = b.attack
        enraged = a.get("enraged") or {}
        return (enraged.get("crontab") if b.enraged else None) or a.get("crontab") or []

    def boss_beat(self):
        b, p = self.boss, self.player
        a = b.attack
        b.clock += 1
        lo, hi = a.get("rain_damage", [14, 20])
        burning = [xy for xy, k in self.marks.items() if k == "burn"]
        warned = [xy for xy, k in self.marks.items() if k == "warn"]
        if burning:
            self.marks = {}
            self.marks_version += 1
        if warned:
            self.marks = {xy: "burn" for xy in warned}
            self.marks_version += 1
            self.sfx("explosion")
            self.anim([FX(shake=s) for s in (1, -1, 1, 0)], 0.06)
            if (p.x, p.y) in self.marks:
                self.hurt(self.rng.randint(lo, hi), "The scheduled fire falls on you.", by=b)
            for m in self.monsters:
                if not m.dead and m is not b and (m.x, m.y) in self.marks and not m.spec.get("boss"):
                    self.damage([(m, self.rng.randint(lo, hi))], lead="Scheduled fire:")
        for job in self.crontab():
            every = int(job.get("every", 3))
            if b.clock % every:
                continue
            what = job.get("do")
            if what == "rain" and not warned:
                self.rain(job)
            elif what == "fork":
                alive = [c for c in self.monsters if c.owner is b and not c.dead]
                n = max(0, min(int(job.get("count", 2)), int(job.get("max", 4)) - len(alive)))
                if n:
                    self.say("crond: forking.", "boss")
                    self.spawn(b, job.get("spawn", "soul"), n)

    def rain(self, job):
        b, p = self.boss, self.player
        patterns = job.get("patterns") or ["rows", "cols", "diagonals", "ring", "checker"]
        kind = patterns[(b.clock // max(1, int(job.get("every", 3)))) % len(patterns)]
        cells = []
        for (x, y) in self.arena:
            if kind == "rows":
                hit = (y - p.y) % 2 == 0
            elif kind == "cols":
                hit = (x - p.x) % 2 == 0
            elif kind == "diagonals":                 # one straight step always leaves it
                hit = abs(x - p.x) == abs(y - p.y)
            elif kind == "ring":
                hit = max(abs(x - p.x), abs(y - p.y)) in (0, 2)
            else:
                hit = (x + y + p.x + p.y) % 2 == 0
            if hit:
                cells.append((x, y))
        self.marks = {xy: "warn" for xy in cells}
        self.marks_version += 1
        self.say("crontab: */%d  rain (%s) - next beat. Get off the marked floor." % (int(job.get("every", 3)), kind),
                 "boss")
        self.sfx("alarm")
        self.interrupt = self.interrupt or "fire scheduled"

    def boss_hurt(self):
        b = self.boss
        a = b.attack
        if not b.awake:
            self.wake(b)
        enr = a.get("enraged") or {}
        if not b.enraged and enr and b.hp <= b.max_hp * float(enr.get("below", 0.5)):
            b.enraged = True
            self.say(enr.get("text", "%s rewrites its crontab." % b.name), "boss")
            self.anim([FX(whiten=k) for k in (0.5, 0.3, 0.15, 0.0)], 0.05)
        esc = a.get("escape")
        if esc and b.hp <= b.max_hp * float(esc.get("below", 0.15)):
            self.boss_escapes(esc)

    def boss_escapes(self, esc):
        b = self.boss
        for t in esc.get("text") or ["%s escapes." % b.name]:
            self.say(t, "boss")
        self.sfx(esc.get("sound") or "teleport")
        self.anim([FX(rise={b.id: k}, whiten=0.5 - k * 0.5, flash=(b.id,) if i % 2 else ())
                   for i, k in enumerate((0.0, 0.04, 0.1, 0.18, 0.28, 0.4, 0.55, 0.75))], 0.07)
        b.gone, b.intent = True, None
        self.marks, self.marks_version = {}, self.marks_version + 1
        if self.target is b:
            self.target = None
        self.music(self.spec.get("music"))
        if esc.get("event"):
            self.event(esc["event"])
        self.interrupt = self.interrupt or "%s is gone" % b.name

    def boss_line(self):
        b = self.boss
        if b is None or not b.awake or b.dead or b.gone:
            return None
        parts = []
        for job in self.crontab():
            every = int(job.get("every", 3))
            parts.append("*/%d %s (%d)" % (every, job.get("do"), every - b.clock % every))
        return b.name.upper(), b.hp, b.max_hp, "crontab: " + "  ".join(parts)

    # ---- pages ------------------------------------------------------------- #
    def ps_lines(self):
        out = [("  PID  STAT   HP  DIST  CMD", "dim")]
        for m in self.visible():
            stat = {"aim": "A", "windup": "W", "charge": "C"}.get(m.intent, "R" if m.awake else "S")
            out.append(("%5d  %-4s %4d  %4d  %s (%s)" % (100 + m.id, stat, max(0, m.hp), self.dist(m), m.name, m.tag),
                        STATE_ROLE.get(m.intent, "text")))
        if len(out) == 1:
            out.append(("(nothing in sight)", "dim"))
        out += [("", "text"), ("STAT  A aiming  W winding up  C charging  R running  S sleeping", "dim")]
        return out

    def man_lines(self, what):
        mons = self.data.monsters or {}
        if not what:
            return [("What manual page do you want?", "dim"), ("man " + " | ".join(sorted(mons)), "dim")]
        kind = what if what in mons else next((m.kind for m in self.monsters if m.tag.lower() == what.lower()), None)
        if kind is None:
            kind = next((k for k, v in mons.items() if what in (v.get("name", ""), v.get("role", ""))), None)
        if kind is None:
            return [("No manual entry for %s" % what, "dim")]
        spec = mons[kind]
        lines = [("%s(6)" % spec.get("name", kind).upper().replace(" ", "_"), "title")]
        if spec.get("role"):
            lines.append((spec["role"], "dim"))
        lines.append(("", "text"))
        return lines + [(t, "text") for t in spec.get("man") or ["No description."]]

    def snapshot_state(self):
        return {"x": self.player.x, "y": self.player.y}


# --------------------------------------------------------------------------- #
# consoles: how a level is shown and asked
# --------------------------------------------------------------------------- #
class FrameConsole:
    """Frame mode: the first-person picture, redrawn in place; keys act at once."""

    def __init__(self, term, style="pixel", keys=True, keymap=None, animate=True, speed=1.0, detail="auto"):
        from .frame import Screen
        from .keys import KeyReader
        self.screen = Screen(term, KeyReader() if keys else None, keymap or KEYMAP, animate, speed)
        self.keymap = self.screen.keymap
        self.keys = self.screen.keys
        self.style = style
        self.detail = detail if detail in DETAILS else "auto"   # how fine the floor is: see View
        self.view = None
        self.views = {}
        self.size = None
        self.phase = 0
        self.status = ""

    def start(self):
        self.screen.start()

    def stop(self):
        self.screen.stop()

    def said(self, text, role):
        pass

    def layout(self):
        W, H = self.screen.size()
        VR = max(6, min(H - 7, 34))
        if (W, VR) != self.size:
            self.size = (W, VR)
            self.view = View(W, VR, self.style, self.detail)
            self.views = {}
        return W, H, VR

    def view_for(self, lv, style=None):
        """The view to draw with: the game's style, or another for a moment (a teleport), or the goggles' dots."""
        style = style or ("dots" if lv.player.nightvision else None)
        if not style or style == self.style:
            return self.view
        if style not in self.views:
            self.views[style] = View(self.size[0], self.size[1], style, self.detail)
        return self.views[style]

    def rows(self, lv, fx=None, cells=None, page=None, automap=False):
        W, H, VR = self.layout()
        sc = self.screen
        g = sc.glyphs
        fx = fx or FX()
        p = lv.player
        w = lv.weapons.get(p.weapon) or {}
        ammo = ("%s %d" % (g["ammo"], p.ammo.get(w["ammo"], 0))) if w.get("ammo") else g["ammo"] + " -"
        bar = (" %s " % g["bar"], "dim")
        keys = [(k if k in p.keys else g["dot"], ("key_" + k) if k in p.keys else "dim") for k in "rwx"]
        face = self.face(lv, fx)
        segs = [(" %s %d" % (g["heart"], p.hp), "hurt" if fx.hurt or p.hp < 30 else "text"),
                ("  %s %d" % (g["armor"], p.armor), "dim" if not p.armor else "key_x" if p.armor > 100 else "good"), bar,
                ] + ([("%s %d" % (p.vehicle.name, max(0, p.vehicle.hp)), "alert" if p.vehicle.hp <= 40 else "key_w"), bar]
                     if p.vehicle is not None else
                     [("%s %s " % (lv.slot_of(p.weapon), w.get("name", "?")), "text"), (ammo, "ammo"), bar]) + keys + [
                bar, (g["facing"][p.facing] + " " + FACE_NAMES[p.facing][0].upper(), "text"), bar,
                ("%d/%d" % (lv.stats["kills"], lv.total_kills), "dim"), bar, (face, "root" if p.sudo else "title")]
        out = [sc.paint.text(segs, W, g["ell"])]
        if page is not None or automap:
            out += self.page_rows(lv, page, W, VR, automap)
        else:
            if cells is None:
                cells = self.view_for(lv, fx.style).render(lv, fx, self.phase)
            out += [list(r) for r in cells]                # painted by the screen: only what changed
        out.append(self.legend(lv, W))
        log = lv.log[-3:]
        log = [("", "text")] * (3 - len(log)) + log
        out += [sc.paint.text([(" " + t, r)], W, g["ell"]) for t, r in log]
        return out

    def face(self, lv, fx):
        p = lv.player
        ascii_ = self.screen.glyphs is not None and self.screen.glyphs.get("heart") == "HP"
        if p.sudo:
            return "[B-)]" if ascii_ else "(⌐■_■)"
        if fx.hurt:
            return "[>_<]" if ascii_ else "(>_<)"
        if p.hp < 30:
            return "[x_x]" if ascii_ else "(×_×)"
        return "[o_o]" if ascii_ else "(•_•)"

    def legend(self, lv, W):
        sc = self.screen
        g = sc.glyphs
        boss = lv.boss_line()
        if boss:
            name, hp, mx, tab = boss
            n = 10
            full = int(round(n * max(0, hp) / float(mx)))
            return sc.paint.text([(" " + name + " ", "boss"), (g["block"] * full, "hurt"), (g["dot"] * (n - full), "dim"),
                                  ("  " + tab, "alert")], W, g["ell"])
        segs = [(" ", "text")]
        for m in lv.visible():
            text, role = m.label()
            if m is lv.target:
                text = "[%s]" % text
            if m.barrel:
                segs += [(text, "dim"), ("  ", "text")]
            else:
                segs += [(text, role), (" %d  " % max(0, m.hp), "dim")]
        if lv.shots:
            segs.append((g["fire"] + " fire", "wind"))
        if lv.player.sudo:
            segs.append(("  # root: %d" % lv.player.sudo, "root"))
        if lv.player.boots:
            segs.append(("  boots: %d" % lv.player.boots, "toxic"))
        if lv.player.goggles:
            segs.append(("  goggles: %d" % lv.player.goggles, "secret") if lv.player.goggles_on else
                        ("  goggles off: %d" % lv.player.goggles, "dim"))
        return sc.paint.text(segs, W, g["ell"])

    def page_rows(self, lv, lines, W, VR, automap):
        sc = self.screen
        if automap:
            return self.automap(lv, W, VR)
        top = max(0, (VR - len(lines)) // 2)
        rows = [""] * VR
        left = max(1, (W - max([len(t) for t, _r in lines] or [0])) // 2)
        for i, (text, role) in enumerate(lines[:VR - top]):
            rows[top + i] = " " * left + sc.paint.text([(text, role)], W - left, sc.glyphs["ell"])
        return rows

    def automap(self, lv, W, VR):
        """The cells seen so far, north up, each cell two characters wide (so it is square)."""
        sc = self.screen
        p = lv.player
        cw, chh = W // 2, VR - 1
        x0 = max(0, min(p.x - cw // 2, lv.w - cw)) if lv.w > cw else -(cw - lv.w) // 2
        y0 = max(0, min(p.y - chh // 2, lv.h - chh)) if lv.h > chh else -(chh - lv.h) // 2
        dark = (14, 14, 18)

        def colour(x, y):
            if (x, y) not in lv.seen_cells:
                return dark
            if (x, y) == (p.x, p.y):
                return (120, 255, 160)
            m = lv.monster_at(x, y)
            if m is not None and m.seen:
                return (240, 70, 60) if not m.barrel else (90, 170, 90)
            c = lv.cell(x, y)
            if any(not it.taken and (it.x, it.y) == (x, y) for it in lv.items):
                return (240, 210, 90)
            if c.kind == "door":
                return fp.KEY_COLOURS.get(c.key, (170, 140, 90)) if c.open < 1 else (90, 80, 60)
            if c.kind == "exit":
                return (90, 230, 120)
            if c.crate:
                return (140, 104, 64)
            if c.kind in ("wall", "panel"):
                return (120, 124, 136)
            if c.toxic:
                return (40, 140, 60)
            if c.teleport:
                return (110, 60, 200)
            if c.lift:
                return (200, 170, 50)
            if c.plate:
                return (150, 128, 70) if not c.down else (96, 82, 46)
            return (44, 42, 40)
        rows = []
        for r in range(chh):
            cells = []
            for x in range(cw):
                c = colour(x0 + x, y0 + r)
                cells += [(" ", None, c), (" ", None, c)]
            rows.append(cells + [(" ", None, None)] * (W - 2 * cw))
        ax, ay = p.x - x0, p.y - y0                      # the player's arrow over his cell
        if 0 <= ay < chh and 0 <= ax < cw:
            arrow = sc.glyphs["facing"][p.facing]
            rows[ay][2 * ax] = (arrow, (10, 40, 20), (120, 255, 160))
            rows[ay][2 * ax + 1] = (" ", None, (120, 255, 160))
        title = " MAP  %s   E exit  coloured doors need keys   (any key)" % lv.name
        return [sc.paint.text([(title, "title")], W, sc.glyphs["ell"])] + [sc.paint.cells(r, sc.unicode) for r in rows]

    # ---- the screen's work ---------------------------------------------- #
    HINT = "↑↓ step  ←→ turn  Ctrl+←→ or , . strafe  space fire  Enter use  Tab map  ? help"
    HINT_ASCII = "arrows: step/turn  , . strafe  space fire  Enter use  Tab map  ? help"

    def hint(self):
        sc = self.screen
        text = self.HINT if sc.glyphs.get("ud") == "↑↓" else self.HINT_ASCII
        if self.keys is None:
            text = "k j step  turn left/right  h l strafe  f fire  use  map  help"
        return sc.paint.text([(text, "dim")], self.size[0] if self.size else 80, sc.glyphs["ell"])

    def draw(self, lv, fx=None, prompt="> ", cells=None):
        self.screen.frame(self.rows(lv, fx, cells), prompt=prompt, status=self.status, footer=self.hint())

    def read(self, lv):
        self.phase += 1
        self.status = ""
        return self.screen.read(lambda: self.draw(lv))

    def page(self, lv, lines, automap=False):
        self.screen.wait(lambda: self.screen.frame(self.rows(lv, page=lines, automap=automap),
                                                   prompt="(Enter) ", footer=self.hint()))

    def play(self, lv, frames, dt):
        self.status = "%s %s" % (self.screen.glyphs["run"], lv.last_line)
        self.screen.play(frames, lambda fx: self.draw(lv, fx, prompt=None), dt)

    def snapshot(self, lv, style=None):
        self.layout()
        return self.view_for(lv, style).render(lv, FX(), self.phase)

    def turn(self, lv, old, direction):
        new = self.view_for(lv).render(lv, FX(), self.phase)
        frames = [slide(old, new, k, direction) for k in (0.3, 0.6, 0.85)]
        self.screen.play(frames, lambda cells: self.draw(lv, prompt=None, cells=cells), 0.03)

    def ride(self, lv, old, new, down):
        """A lift's ride, in dots: the view slides away, the shaft goes by, the other end comes in."""
        frames = [vslide(old, new, k, down) for k in (0.08, 0.18, 0.3, 0.42, 0.52, 0.62, 0.72, 0.82, 0.92, 1.0)]
        self.screen.play(frames, lambda cells: self.draw(lv, prompt=None, cells=cells), 0.11)

    def ending(self, lv):
        if lv.over == "dead":
            self.screen.play([FX(hurt=0.6, fade=k) for k in (0.15, 0.3, 0.45, 0.6, 0.72)],
                             lambda fx: self.draw(lv, fx, prompt=None), 0.08)
        else:
            self.draw(lv, prompt=None)
        time.sleep(0.6 if self.screen.animate else 0)

    def busy(self):
        return self.screen.busy()


class TextConsole:
    """Scrolling text: a small map that turns with the player, the news, a prompt."""
    keys = None
    keymap = None

    def __init__(self, write, read):
        self.write, self.ask = write, read

    def start(self):
        pass

    def stop(self):
        pass

    def said(self, text, role):
        self.write(text)

    def play(self, lv, frames, dt):
        pass

    def snapshot(self, lv, style=None):
        return None

    def turn(self, lv, old, direction):
        pass

    def ride(self, lv, old, new, down):
        pass

    def ending(self, lv):
        pass

    def busy(self):
        return contextlib.nullcontext()

    def page(self, lv, lines, automap=False):
        if automap:
            lines = [(row, "text") for row in self.whole_map(lv)]
        for text, _role in lines or []:
            self.write(text)

    def whole_map(self, lv):
        p = lv.player
        out = []
        for y in range(lv.h):
            row = []
            for x in range(lv.w):
                if (x, y) == (p.x, p.y):
                    row.append("^>v<"[p.facing])
                elif (x, y) not in lv.seen_cells:
                    row.append(" ")
                else:
                    row.append(self.char(lv, x, y))
            out.append("".join(row).rstrip())
        return out

    def char(self, lv, x, y):
        m = lv.monster_at(x, y)
        if m is not None and m.seen:
            return m.tag[0]
        c = lv.cell(x, y)
        if any(not it.taken and (it.x, it.y) == (x, y) for it in lv.items):
            return "*"
        if c.kind == "door":
            return "/" if c.open >= 1 else (c.key or "+").upper() if c.key else "+"
        if c.kind == "exit":
            return "E"
        if c.crate:
            return "&"
        if c.kind in ("wall", "panel"):
            return "#"
        if (x, y) in lv.marks:
            return "!"
        if c.teleport:
            return "o"
        if c.lift:
            return "="
        if c.plate:
            return "_" if c.down else "^"
        return "~" if c.toxic else "."

    def view(self, lv):
        """Seven cells ahead, four to each side, turned so ahead is up."""
        p = lv.player
        fx, fy = DIRS[p.facing]
        rx, ry = DIRS[(p.facing + 1) % 4]
        lines = []
        for z in range(6, -2, -1):
            row = []
            for a in range(-4, 5):
                x, y = p.x + fx * z + rx * a, p.y + fy * z + ry * a
                if (z, a) == (0, 0):
                    row.append("@")
                elif lv.line_of_sight(p.x, p.y, x, y) or abs(z) + abs(a) <= 1:
                    row.append(self.char(lv, x, y))
                else:
                    row.append(" ")
            lines.append(" ".join(row))
        return lines

    def read(self, lv):
        p = lv.player
        w = lv.weapons.get(p.weapon) or {}
        ammo = (" %s %d" % (w["ammo"], p.ammo.get(w["ammo"], 0))) if w.get("ammo") else ""
        if p.vehicle is not None:
            ammo += " | riding the %s %d" % (p.vehicle.name, max(0, p.vehicle.hp))
        power = "".join(" | %s %d" % (n, v) for n, v in (("root", p.sudo), ("boots", p.boots),
                                                          ("goggles" if p.goggles_on else "goggles off", p.goggles)) if v)
        self.write("-- hp %d  armour %d | %s%s | keys %s%s | facing %s | beat %d --" % (
            p.hp, p.armor, w.get("name", "?"), ammo, "".join(sorted(p.keys)) or "-", power, FACE_NAMES[p.facing],
            lv.beat))
        for line in self.view(lv):
            self.write("   " + line)
        vis = lv.visible()
        if vis:
            self.write("   " + "  ".join("%s %s %d" % (m.label()[0], m.name, max(0, m.hp)) for m in vis))
        boss = lv.boss_line()
        if boss:
            self.write("   %s %d/%d  %s" % boss)
        return self.ask("> ")


# --------------------------------------------------------------------------- #
# from a scene
# --------------------------------------------------------------------------- #
def play_scene(game, scene):
    """Run the level of a scene for a CLIo game, then go on with the story."""
    lid = scene.get("level")
    w = game.world
    state = w.vars.get("_fp_player")
    lv = Level(game.data, lid, audio=game.audio, seed=game.seed, player=state)
    term = game.term
    cfg = game.data.config.get("first_person") or {}
    settings = game.settings
    size_ok = True
    try:
        cols, rows = term.size()
        size_ok = cols >= 40 and rows >= 18
    except Exception:
        pass
    frame = (term.is_tty and term.ansi and size_ok and not settings.get("scroll_levels")
             and term.inp is None)
    if frame:
        keymap = dict(KEYMAP)
        keymap.update(cfg.get("keymap") or {})
        keymap.update(settings.get("keymap") or {})
        console = FrameConsole(term, settings.get("view") or cfg.get("view", "pixel"),
                               detail=settings.get("detail") or cfg.get("detail", "auto"),
                               keys=not settings.get("lines"), keymap=keymap, animate=term.animate,
                               speed=max(0.0, float(term.speed or 1.0)))
    else:
        def write(text):
            term.line(text)

        def read(prompt):
            try:
                return term.read(prompt)
            except Exception as e:
                if e.__class__.__name__ == "QuitGame":
                    return None
                raise
        console = TextConsole(write, read)
    outcome = lv.run(console)
    w.vars["_fp_player"] = lv.player.keep()
    stats = dict(lv.stats, beats=lv.beat, par=lv.par, secrets_total=lv.total_secrets, kills_total=lv.total_kills,
                 items_total=lv.total_items)
    w.vars.setdefault("levels", {})[lid] = stats
    if outcome == "exit":
        if lv.boss is not None and lv.boss.gone:
            w.flags["%s_escaped" % lv.boss.kind] = True
        effects = scene.get("on_level_exit") or lv.spec.get("on_exit")
        if lv.exit_kind == "secret":                   # the secret exit: a way of its own, if the scene has one
            effects = scene.get("on_secret_exit") or effects
        if effects:
            conditions.run(effects, game)
    elif outcome == "dead":
        w.vars.pop("_fp_player", None)
        game.end_game("lose", lv.spec.get("death_text") or "outro_lose")
    else:
        game.over = "quit"
    return outcome


def validate(data):
    """Problems with levels.json and monsters.json, as sentences."""
    problems = []
    mons = data.monsters or {}
    items = data.items or {}
    sprites = data.sprites or {}
    for kind, spec in mons.items():
        if not isinstance(spec, dict):
            problems.append("monster '%s' should be an object" % kind)
            continue
        a = spec.get("attack") or {}
        if a.get("kind") not in (None, "melee", "hitscan", "projectile", "spawner", "cron", "barrel", "flame"):
            problems.append("monster '%s': unknown attack kind '%s'" % (kind, a.get("kind")))
        spawn = a.get("spawn")
        if spawn and spawn not in mons:
            problems.append("monster '%s': spawns unknown monster '%s'" % (kind, spawn))
        for job in a.get("crontab") or []:
            if job.get("do") == "fork" and job.get("spawn") and job["spawn"] not in mons:
                problems.append("monster '%s': its crontab forks unknown monster '%s'" % (kind, job["spawn"]))
        if spec.get("drops") and spec["drops"] not in items:
            problems.append("monster '%s': drops unknown item '%s'" % (kind, spec["drops"]))
        sp = spec.get("sprite") or kind
        if sp not in sprites:
            problems.append("monster '%s': no sprite '%s' in sprites.json" % (kind, sp))
    from .firstperson import TEXTURES
    tiles = getattr(data, "tiles", None) or {}
    for name, t in tiles.items():
        if not isinstance(t, dict) or not isinstance(t.get("pixels"), list) or not t["pixels"] \
                or not all(isinstance(r, str) for r in t["pixels"]):
            problems.append("tile '%s' should have pixels: rows of letters" % name)
            continue
        pal = t.get("palette") or {}
        for d in [t["pixels"]] + [f for f in t.get("frames") or [] if isinstance(f, list)]:
            odd = sorted(set("".join(r for r in d if isinstance(r, str))) - set(pal) - {"."})
            if odd:
                problems.append("tile '%s' uses letters its palette does not have: %s" % (name, " ".join(odd)))
                break
    known_tiles = set(TEXTURES) | set(tiles)
    for wid, w in (getattr(data, "weapons", None) or {}).items():
        if not isinstance(w, dict):
            problems.append("weapon '%s' should be an object" % wid)
            continue
        if w.get("kind") not in (None, "", "gun", "melee", "rocket", "grenade"):
            problems.append("weapon '%s': kind should be gun, melee, rocket or grenade, not '%s'" % (wid, w.get("kind")))
        d = w.get("damage")
        if d is not None and not (isinstance(d, list) and len(d) == 2 and all(isinstance(v, (int, float)) for v in d)):
            problems.append("weapon '%s': damage should be [least, most]" % wid)
        if w.get("sprite") and w["sprite"] not in sprites:
            problems.append("weapon '%s': no sprite '%s' in sprites.json" % (wid, w["sprite"]))
        key = str(w.get("key") or wid)
        if not (len(key) == 1 and key in "123456789"):
            problems.append("weapon '%s': key should be one of 1-9 (the key that picks it)" % wid)
    for name, sp in sprites.items():                 # a monster's steps and its attack: drawn as big as it is
        if not isinstance(sp, dict) or not isinstance(sp.get("pixels"), list):
            continue
        size = (len(sp["pixels"]), max((len(r) for r in sp["pixels"]), default=0))
        frames = list(sp.get("walk") or []) + ([sp["attack"]] if sp.get("attack") else [])
        if any(not isinstance(f, list) or (len(f), max((len(r) for r in f), default=0)) != size for f in frames):
            problems.append("sprite '%s': its walk and attack frames should be %d x %d, as it is" % (name, size[1], size[0]))
    for lid, lv in (data.levels or {}).items():
        if not isinstance(lv, dict):
            problems.append("level '%s' should be an object" % lid)
            continue
        for key in ("floor", "ceiling"):
            if lv.get(key) and lv[key] not in known_tiles:
                problems.append("level '%s': its %s is an unknown tile '%s'" % (lid, key, lv[key]))
        rows = lv.get("map")
        if not isinstance(rows, list) or not rows or not all(isinstance(r, str) for r in rows):
            problems.append("level '%s': map should be a list of rows of text" % lid)
            continue
        legend = dict(LEGEND)
        legend.update(lv.get("legend") or {})
        starts = sum(r.count(ch) for r in rows for ch, spec in legend.items()
                     if isinstance(spec, dict) and spec.get("start"))
        if starts != 1:
            problems.append("level '%s': the map should have one start (@), it has %d" % (lid, starts))
        if not any("E" in r for r in rows) and not any(isinstance(s, dict) and s.get("exit") for s in legend.values()
                                                         if any(k for k in s)):
            problems.append("level '%s': there is no exit (E)" % lid)
        used = set("".join(rows))
        counts = {}
        for ch in used:
            sp = legend.get(ch)
            if isinstance(sp, dict):
                for key in ("teleport", "lift", "plate", "open_while"):
                    if sp.get(key):
                        counts.setdefault((key, sp[key]), 0)
                        counts[(key, sp[key])] += sum(r.count(ch) for r in rows)
        for (key, name), n in sorted(counts.items()):
            if key == "teleport" and n < 2:
                problems.append("level '%s': the teleporter '%s' has one pad; it needs another to lead to" % (lid, name))
            if key == "lift" and n != 2:
                problems.append("level '%s': the lift '%s' should have two ends, it has %d" % (lid, name, n))
            if key == "open_while" and ("plate", name) not in counts:
                problems.append("level '%s': no plate called '%s' holds what opens while it is down" % (lid, name))
        for ch in sorted(used):
            spec = legend.get(ch)
            if spec is None:
                problems.append("level '%s': the map uses '%s', which the legend does not explain" % (lid, ch))
                continue
            if isinstance(spec, str):
                if spec not in mons and spec not in items:
                    problems.append("level '%s': '%s' is neither a monster nor an item" % (lid, spec))
                continue
            if spec.get("monster") and spec["monster"] not in mons:
                problems.append("level '%s': '%s' is an unknown monster '%s'" % (lid, ch, spec["monster"]))
            if spec.get("item") and spec["item"] not in items:
                problems.append("level '%s': '%s' is an unknown item '%s'" % (lid, ch, spec["item"]))
            for key in ("wall", "texture", "floor", "ceiling"):
                if spec.get(key) and spec[key] not in known_tiles:
                    problems.append("level '%s': '%s' has an unknown tile '%s'" % (lid, ch, spec[key]))
            if spec.get("conveyor") and str(spec["conveyor"]).lower()[:1] not in FACING:
                problems.append("level '%s': '%s' is a belt going '%s'; it should be n, e, s or w" % (lid, ch, spec["conveyor"]))
            if spec.get("exit") not in (None, False, True, "secret"):
                problems.append("level '%s': '%s' is an exit '%s'; it should be true or \"secret\"" % (lid, ch, spec["exit"]))
    return problems
