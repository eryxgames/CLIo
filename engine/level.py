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
import json
import math
import operator
import os
import random
import zlib
import re
import time

from . import ai
from . import conditions
from . import firstperson as fp
from . import snapshot
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
    "?": "help", "f1": "help", "f2": "goggles", "f5": "save", "f9": "load", "]": "next",
    "f3": "mag", "f4": "jet", "f6": "dive",
    "shift-up": "look up", "shift-down": "look down", "ctrl-up": "look up", "ctrl-down": "look down",
    "alt-up": "look up", "alt-down": "look down",
}
LOOK_STEPS = 2               # how far up or down the player looks, in steps (the mesh view draws it)

WEAPONS = {
    "1": {"name": "fist", "ammo": None, "sprite": "w_fist", "sound": "punch", "kind": "melee", "damage": [6, 14]},
    "2": {"name": "pistol", "ammo": "bullets", "sprite": "w_pistol", "sound": "pistol", "damage": [8, 14]},
    "3": {"name": "shotgun", "ammo": "shells", "sprite": "w_shotgun", "sound": "shotgun", "damage": [5, 9],
          "pellets": 7, "spread": 0.35},
    "4": {"name": "chaingun", "ammo": "bullets", "sprite": "w_chaingun", "sound": "chaingun", "damage": [7, 12],
          "burst": 2},
}
IDLE = "."                   # the command of a beat that passes in real time with no key pressed
ACCURACY = (1.0, 0.95, 0.9, 0.82, 0.72, 0.62, 0.52, 0.44, 0.38)   # by distance in cells
COVER = 0.5                  # a shot that would hit one standing in cover hits the cover instead, this often
CROSSFIRE = 0.1              # a squad's gun is this much surer for each other gun of it on him from another side
PELLET = (1.0, 1.0, 0.85, 0.6, 0.42, 0.3, 0.22, 0.16, 0.12)

HELP = [
    ("↑ ↓  step forward, back      ← →  turn", "text"),
    ("Ctrl+← →  or  , .  strafe     space  fire", "text"),
    ("Enter  open, press   Tab  map   1-7 ]  weapons", "text"),
    ("F2  TTY goggles on/off (the battery lasts while off)", "text"),
    ("F3 magboots (on the ceiling: let go)  F4 jetpack  F6 dive / surface", "text"),
    ("F5  save   F9  load the last save", "text"),
    ("", "text"),
    ("Typed: k j h l, turn left/right/around, use,", "dim"),
    ("f [x], kill [-9] x, t x, w [n], next, map, ps, man x,", "dim"),
    ("mag [on|off], jet [on|off], dive, surface,", "dim"),
    ("goggles [on|off], out (of a vehicle), history,", "dim"),
    ("alias n='...', keys, whoami, sound, q", "dim"),
    ("save [name], load [name], saves, realtime [off|s]", "dim"),
    ("a; b   a && b   a || b   !!  !3  !f   as in a shell", "dim"),
    ("A surprise stops a line, as ^C would.", "dim"),
]

# taps on the picture (a phone in Termux, or a mouse): what each part of it does - see FrameConsole.touch_key
TOUCH_HELP = [
    ("", "text"),
    ("Touch: the picture in thirds -", "text"),
    ("  left, right: turn    bottom corners: strafe", "text"),
    ("  top middle: forward  centre: fire  bottom: use", "text"),
    ("  swipe up, down: forward, back", "text"),
    ("  the status line: next weapon   under it: map", "text"),
]
SWIPE_GAP = 0.3              # seconds: a swipe sends a run of wheel steps; one step of the player per this

# lines about the game rather than in it: not kept in a level's journal (a save plays the journal back)
DUELLED = re.compile(r" =((?:won|lost|fled)(?::\d+)?)$")   # a duel's outcome on the line that started it
META = re.compile(r"(?:save|load|saves)(?:\s+[\w-]+)?|\*[\w-]*|realtime(?:\s+(?:off|on|\d+(?:\.\d+)?))?")

DETAILS = ("auto", "high", "low")     # a level's picture: "low" draws the floor and ceiling at half width

STATE_MARK = {"aim": "!", "windup": "!", "charge": "»", "spin": "!!"}
STATE_ROLE = {"aim": "aim", "windup": "wind", "charge": "charge", "spin": "aim"}


class StopLine(Exception):
    """An unknown command ends the rest of the line, as an error would in a script."""


# --------------------------------------------------------------------------- #
# the map
# --------------------------------------------------------------------------- #
WALLS = ("wall", "panel", "exit", "switch", "locker", "field")   # the kinds of cell nothing goes through


class Cell:
    __slots__ = ("x", "y", "ch", "kind", "tex", "key", "panel", "toxic", "open", "opens_on", "closes_on",
                 "on_enter", "sealed", "pressed", "label", "label_role", "secret", "found", "floor", "ceiling",
                 "savepoint",
                 "crate", "plate", "down", "open_while", "teleport", "arrive_only", "pad_facing", "lift", "deck", "sunk",
                 "oil", "slick", "conveyor", "scorched", "exit_kind", "heavy", "switch", "sky", "deep", "steep",
                 "duel", "stairs", "mag", "pit", "bulkhead", "supply", "locker", "opened", "gate", "field", "zap",
                 "open_for", "closes_at", "from_side", "on_open", "height", "ceiling_height", "step",
                 "ceiling_mag", "mag_off_on", "mag_delay", "high", "hatch", "mag_ceiling", "lamp", "world_up",
                 "sheds")

    def __init__(self, x, y, ch, spec):
        self.x, self.y, self.ch = x, y, ch
        self.stairs = spec.get("stairs")                # stairs: walked into, they lead to the other of their name
        self.mag = spec.get("mag")                      # magnetic plating: magboots walk up it to the other of its name
        self.mag_ceiling = bool(spec.get("mag_ceiling"))  # magnetic plating up to the ceiling: magboots walk up it
        self.ceiling_mag = bool(spec.get("ceiling_mag"))  # the ceiling here is plated: magboots walk on it
        self.mag_off_on = spec.get("mag_off_on")        # ... until this event cuts its power
        self.mag_delay = int(spec.get("mag_delay") or 0)  # ... so many beats after the event
        self.high = bool(spec.get("high"))              # a switch, exit or locker up by the ceiling: reached from it
        self.hatch = spec.get("hatch")                  # a hatch in the ceiling to the other of its name (the deck above)
        self.lamp = spec.get("lamp") or None            # a lamp here: its colour, reach, power... (engine/atmosphere.py)
        up = FACING.get(str(spec.get("world_up") or "").lower())
        self.world_up = up                              # a wall walked as a floor: which way in the map the world's up is
        self.sheds = spec.get("sheds") if isinstance(spec.get("sheds"), dict) else None   # drops a falling thing
        self.bulkhead = bool(spec.get("bulkhead"))      # a wall down into the water: a diver passes under it
        self.tex = spec.get("wall") or spec.get("texture") or (
            "stairs" if self.stairs else "magwall" if self.mag or self.mag_ceiling else "bulkhead" if self.bulkhead else
            "field" if spec.get("field") else "steel")
        self.floor = spec.get("floor")                  # tiles under and over this cell, else the level's
        self.ceiling = spec.get("ceiling")
        self.crate = bool(spec.get("crate"))            # a crate stands here: it can be pushed
        self.heavy = spec.get("crate") == "heavy" or (self.crate and bool(spec.get("heavy")))   # only a machine moves it
        self.supply = contents(spec["supply"]) if spec.get("supply") is not None else None   # a crate that opens
        if self.supply is not None:
            self.crate = True
        self.locker = contents(spec["locker"]) if spec.get("locker") is not None else None   # a locker in the wall
        self.opened = False                             # the locker or the supply crate has been opened (and emptied)
        self.on_open = spec.get("on_open")              # opening it sets off this event
        self.gate = bool(spec.get("gate"))              # bars: a door seen and shot through
        self.field = spec.get("field")                  # a force field: seen and shot through, never walked through
        self.zap = int(spec.get("zap", 10) or 0) if self.field else 0     # what touching it costs
        self.open_for = int(spec.get("open_for") or 0)  # a timed door: it shuts again this many beats after it opens
        self.closes_at = None                           # the beat after which it shuts
        side = str(spec.get("from") or "").lower()[:1]
        self.from_side = FACING.get(side) if side else None   # a one-way door: it opens only from this side
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
        self.sealed = bool(spec.get("sealed")) or bool((spec.get("door") or spec.get("gate")) and spec.get("opens_on")
                                                       and not spec.get("key"))
        self.pressed = False
        self.secret = bool(spec.get("secret")) or bool(self.panel)
        self.savepoint = bool(spec.get("savepoint"))    # a checkpoint: the game is saved when it is first reached
        self.switch = spec.get("switch")                # a switch in the wall: using it sets off this event
        self.duel = {k: spec[k] for k in ("duel", "feedback", "feedback_text", "duel_won", "flee") if k in spec} \
            if spec.get("duel") else None               # a terminal: a card duel before the switch is thrown
        self.sky = bool(spec.get("sky"))                # open to the sky: no ceiling over it
        self.deep = bool(spec.get("deep"))              # water too deep to wade: floaters and fliers only
        self.steep = bool(spec.get("steep"))            # too steep to climb (open land): floaters and fliers only
        self.pit = bool(spec.get("pit"))                # a drop: fliers and floaters only
        self.height = float(spec.get("height") or 0.0)  # in rooms: the floor this high (walls' heights; the mesh view)
        top = spec.get("ceiling_height")                # ... and the ceiling (else a wall's height over the floor)
        self.ceiling_height = float(top) if top is not None else None
        self.step = spec.get("step")                    # the tile of the risers up to this cell (else the engine's)
        self.found = False
        self.open = 0.0
        self.exit_kind = "secret" if spec.get("exit") == "secret" else "exit"
        if spec.get("exit"):
            self.kind = "exit"
        elif self.locker is not None:
            self.kind = "locker"
        elif self.field:
            self.kind = "field"
        elif spec.get("door") or self.gate:
            self.kind = "door"
            self.open = 1.0 if spec.get("open") else 0.0
        elif self.panel:
            self.kind = "panel"
        elif self.switch:
            self.kind = "switch"
        elif spec.get("wall") or self.stairs or self.mag or self.mag_ceiling or self.bulkhead \
                or ((spec.get("opens_on") or spec.get("open_while")) and not spec.get("door")):
            self.kind = "wall"
        else:
            self.kind = "floor"
        self.label, self.label_role = None, None
        if self.kind in ("door", "locker") and self.key:
            self.label = "".join(b if b == self.key else "-" for b in "rwx")
            self.label_role = "key_" + self.key
        elif self.kind == "exit":
            self.label, self.label_role = "EXIT", "good"
        elif self.kind == "switch" and spec.get("label"):
            self.label, self.label_role = str(spec["label"])[:8], "info"
        elif (self.stairs or self.mag or self.kind == "locker") and spec.get("label"):
            self.label, self.label_role = str(spec["label"])[:8], "info"

    @property
    def solid(self):
        if self.crate:
            return True
        if self.kind == "door":
            return self.open < 1.0
        return self.kind in WALLS

    def drawn_as_wall(self, opened=None):
        if self.kind == "door":
            return (self.open if opened is None else opened) < 1.0
        return self.kind in WALLS

    @property
    def clear(self):
        """Bars or a force field: what is beyond is seen, and shot at, through it."""
        return self.gate or self.kind == "field"

    def texture(self):
        if self.kind == "door":
            if self.gate:
                return "bars_" + self.key if self.key else "bars"
            if self.open_for:
                return "door_timed"
            if self.from_side is not None:
                return "door_oneway"
            if self.sealed:
                return "sealed"
            return "door_" + self.key if self.key else "door"
        if self.kind == "locker":
            if self.opened:
                return "locker_open"
            return "locker_" + self.key if self.key else "locker"
        if self.kind == "panel":
            return self.panel if self.panel in ("fist", "shoot") else "steel"
        if self.kind == "exit":
            return "exit_on" if self.pressed else "exit"
        if self.kind == "switch":
            return "switch_on" if self.pressed else "switch"
        return self.tex


def contents(v):
    """What a locker or a supply crate holds, as item ids: a list, one id, or true (nothing)."""
    if isinstance(v, str):
        return (v,)
    if isinstance(v, (list, tuple)):
        return tuple(str(i) for i in v)
    return ()


VOID = Cell(-1, -1, " ", {"wall": "steel"})


class Field:
    """Steps to a cell from the cells round it, a ring at a time - only as many rings as have been asked for
    (``get``), or all of them (``finish``). Monsters do not block; deep water, slopes and pits only floaters."""
    __slots__ = ("dist", "frontier", "d", "limit", "floats", "links", "cell", "up")

    def __init__(self, lv, x0, y0, limit, floats):
        self.dist = {(x0, y0): 0}
        self.frontier = [(x0, y0)]
        self.d, self.limit, self.floats = 0, limit, floats
        self.links = lv.pad_links()
        self.cell = lv.cell
        self.up = (lv.step_up + 1e-9) if (getattr(lv, "heights", False) or getattr(lv, "terraced", False)) \
            and not floats else None

    def get(self, at, default=None):
        dist = self.dist
        while at not in dist and self.frontier and self.d < self.limit:
            self.ring()
        return dist.get(at, default)

    def finish(self):
        while self.frontier and self.d < self.limit:
            self.ring()

    def ring(self):
        dist, cell, links, floats = self.dist, self.cell, self.links, self.floats
        up = self.up
        self.d = d = self.d + 1
        nxt = []
        for (x, y) in self.frontier:
            for n in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):      # DIRS: north, east, south, west
                if n in dist:
                    continue
                c = cell(n[0], n[1])
                if c.solid or (not floats and (c.deep or c.steep or c.pit)):        # as passable() has it
                    continue
                if up is not None and cell(x, y).height - c.height > up:            # walked from n: a step too high
                    continue
                dist[n] = d
                nxt.append(n)
            if links:
                for n in links.get((x, y), ()):         # a pad that leads here is a step away
                    if n not in dist:
                        dist[n] = d
                        nxt.append(n)
        self.frontier = nxt
# what can change in a cell while a level is played (the rest is as the map made it): saved, and kept for a
# forgotten chunk. A test plays every level through and checks that nothing else changes.
CELL_STATE = ("kind", "open", "pressed", "found", "crate", "heavy", "down", "sunk", "scorched", "sealed",
              "toxic", "oil", "slick", "secret", "panel", "key", "supply", "locker", "opened", "closes_at",
              "ceiling_mag")
cell_state = operator.attrgetter(*CELL_STATE)
JOURNAL_KEEP = 20000         # lines of play a save keeps (a snapshot carries the rest)


class Monster:
    # what a monster's mind holds (engine/ai): an older save's monsters get these
    DEFAULTS = {"tactic": None, "role": None, "squad": None, "seen_at": None, "post": None, "side": 0, "goal": None,
                "said": None, "spot": None, "grenades_left": 0, "mines_left": 0, "lobbed": None, "dived": False,
                "on_death": None}

    def __init__(self, mid, kind, spec, x, y, tag):
        self.id, self.kind, self.spec = mid, kind, spec
        self.x, self.y, self.tag = x, y, tag
        self.dived = False                               # a submarine under the water
        self.hp = self.max_hp = int(spec.get("hp", 20))
        self.spin = 0                                   # beats spent spinning up (a gun that must spin first)
        self.spun = False
        self.stride = 0                                 # steps taken: which foot its walk shows
        self.stun = 0                                   # beats it loses (a chainsaw bites)
        self.sprite = spec.get("sprite") or kind
        self.model = spec.get("model")                  # a 3D model in models.json, drawn instead of the sprite
        self.heading = None                             # where it faces (radians; None: at the player)
        self.size = float(spec.get("size", 1.0))
        self.float = float(spec.get("float", 0.0))
        self.attack = spec.get("attack") or {}
        self.awake = bool(spec.get("awake"))
        self.wake_on = None
        self.on_death = None                            # its death sets off this event (its map cell's "on_death")
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
        self.ball = spec.get("kind") == "ball"         # a heavy ball: it rolls when shoved, and crushes what it meets
        self.barrel = spec.get("kind") == "barrel" or self.attack.get("kind") == "barrel" or self.ball
        self.rolling = None                              # (dx, dy) while a ball rolls
        self.left = 0                                    # cells it rolls on before it comes to rest
        self.roll_wait = 0                               # beats before a released ball starts
        self.roll_dir = None                             # the way an event sets it rolling (its map cell's "roll")
        self.rolled = 0                                  # cells rolled: how far it has turned
        if self.ball:
            self.heading = 0.0
        self.vehicle = spec.get("vehicle") if isinstance(spec.get("vehicle"), dict) else None   # one can ride it
        v = self.vehicle or {}
        self.fuel = int(v.get("fuel", 0) or 0)           # beats of fuel in its tanks (a vehicle with "fuel")
        self.started = False                             # its engines run: the fuel burns a beat at a time
        self.tactic = None                               # what its brain chose this beat (engine/ai)
        self.role = None                                 # its part in its squad's plan
        self.squad = None                                # the Squad it belongs to
        self.seen_at = None                              # (x, y, beat): where it last knew the player to be
        self.post = (x, y)                               # where it was put: a guard goes back there
        self.side = 0                                    # a flanker's side: -1 his left, 1 his right
        self.goal = None                                 # (x, y): where its tactic takes it (cover, a flank)
        self.said = None                                 # the tactic it last told the player about
        self.spot = None                                 # (x, y): the cell its squad gave it (a swarm round him)
        g, mn = spec.get("grenades"), spec.get("mines")
        self.grenades_left = int(g.get("count", 1)) if isinstance(g, dict) else 0   # grenades it carries
        self.mines_left = int(mn.get("count", 1)) if isinstance(mn, dict) else 0    # mines it can lay
        self.lobbed = None                               # the beat it last threw a grenade

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
        self.model = self.pickup.get("model")
        self.size = float(self.pickup.get("size", 0.55))
        self.taken = False
        self.on_pickup = None

    @property
    def mine(self):
        """A mine (``"pickup": {"mine": {...}}``): it goes off under the one who steps on it; not an item found."""
        return isinstance(self.pickup.get("mine"), dict)


class Grenade:
    """A grenade on the floor, its fuse burning: beats left until it goes off."""

    def __init__(self, x, y, fuse, blast):
        self.x, self.y, self.fuse, self.blast = x, y, fuse, blast


TIP = (10, 28, 52, 76, 90)    # degrees the world turns through as magboots walk up a wall
TIP_BACK = (90, 72, 46, 22, 6)  # ... and back at the other end
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
        self.fuel = 0                                # beats of fuel carried in cans, for a machine that needs it
        self.magboots = bool(start.get("magboots"))  # worn: they grip steel (no sliding, belts do not carry him)
        self.mag_on = self.magboots
        self.jet = int(start.get("jet", 0))          # beats of fuel in the jetpack
        self.jet_on = False                          # in the air on it
        self.diving = False                          # under the water (swimming, or in a submarine that dived)
        self.air = int(cfg.get("breath", 20))        # beats of breath left under water
        self.look = 0                                # looking up (+) or down (-), in steps (the mesh view)
        self.ceiling = False                         # on the ceiling, upside down, held by the magboots

    DEFAULTS = {"magboots": False, "mag_on": False, "jet": 0, "jet_on": False, "diving": False, "air": 20, "look": 0,
                "ceiling": False}

    @property
    def nightvision(self):
        """Seeing through the goggles: they are on and the battery is not flat."""
        return bool(self.goggles and self.goggles_on)

    def keep(self):
        """What goes on to the next level (keys and root do not; boots do)."""
        return {"health": self.hp, "max_health": self.max_hp, "armor": self.armor, "weapons": self.weapons,
                "weapon": self.weapon, "ammo": dict(self.ammo), "max_ammo": dict(self.max_ammo),
                "boots": self.boots, "magboots": self.magboots, "jet": self.jet}


for _kind in (Monster, Item, Player, Grenade, Shot):
    snapshot.register(_kind)                             # a save holds these, each once
snapshot.LEVEL_DEFAULTS.setdefault("rides", list)
snapshot.LEVEL_DEFAULTS.setdefault("cuts", list)


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
    heights = False                                      # rooms with floors at heights (made from a map only)
    terraced = False                                     # open land with the map's floors raised (terraces)
    atmosphere = None                                    # light and weather, when the level has them

    def __init__(self, data, level_id, audio=None, seed=None, player=None, depth=0):
        spec = (data.levels or {}).get(level_id)
        if not isinstance(spec, dict):
            raise ValueError("there is no level '%s'" % level_id)
        self.data, self.id, self.spec = data, level_id, spec
        self.cfg = data.config.get("first_person") or {}
        self.render = spec.get("render")                 # "mesh" or "classic": how this level would be drawn
        self.step_up = float(spec.get("climb", self.cfg.get("climb", 0.55)))   # the highest step walked up
        self.audio = audio
        made = spec.get("generate") if isinstance(spec.get("generate"), dict) else spec.get("world")
        if seed is None and isinstance(made, dict) and made.get("seed") == "run":
            seed = random.SystemRandom().randrange(1, 1 << 30)   # a new place every game (the save keeps the seed)
        self.depth = int(depth or 0)                     # how deep: a generated level's floor, from a game variable
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
        self.cuts = []                                   # (beat, x, y): plated ceilings whose power goes then
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
        self.seed = seed
        self.start_player = copy.deepcopy(player) if isinstance(player, dict) else None
        self.journal = []                                # every line typed: a save is these, played back
        self.replaying = False
        self.host = None                                 # the game round the level: it saves, loads, jumps
        self.dev = False                                 # --dev: *LEVEL jumps, saves are not counted
        saves = self.cfg.get("saves")
        self.saves_left = int(saves) if isinstance(saves, int) and not isinstance(saves, bool) else None
        self.loaded = self.warp = None                   # a save to go on with, a level to jump to
        self.pending_save = []                           # (slot, how): saves to make when this line is done
        self.duel_answer = None                          # a card duel's outcome, read back from the journal
        self.reached = set()                             # checkpoints passed
        self.opening = None                              # lines said in place of the title page (a loaded game)
        self.sprites = {}
        self._tags = {}
        self._ids = 0
        self.world = None
        self.squads = {}                                 # name -> Squad (engine/ai/squad.py)
        if isinstance(spec.get("world"), dict):
            self.start_world(spec["world"])
        else:
            self.parse_map()
        self.load_models()
        self.load_sprites()
        self.load_tiles()
        if self.world is not None:
            self.world.begin()
            self.land_walls = self.world.walls
        self.plates(quiet=True)
        self.update_seen()
        if self.world is None:                           # the cells as built: a save keeps only what changed
            self._pristine = [cell_state(c) for row in self.grid for c in row]

    # ---- building ------------------------------------------------------- #
    @property
    def world_seed(self):
        """The number a generated level is made from: the level's seed, its name, and how deep."""
        base = self.seed if self.seed is not None else zlib.crc32(str(self.id).encode())
        return zlib.crc32(("%s/%s/%d" % (base, self.id, self.depth)).encode()) & 0x3FFFFFFF

    def start_world(self, wspec):
        """A level without end (engine/chunks.py): nothing is built here but the start; the chunks round the
        player are made as he goes."""
        from .chunks import SIZE, Chunks
        self.land = None
        self.w = self.h = SIZE
        self.map_w = self.map_h = 0
        self.plate_cells, self.held_cells, self.pads, self.lifts, self.belts, self.rides = [], [], [], [], [], []
        self.fires = {}
        self.total_kills = self.total_items = self.total_secrets = 0
        self.world = Chunks(self, wspec)
        self.grid = self.world
        self.cell = self.world.cell                      # the cells come from the world's chunks
        self.player.x, self.player.y = self.world.start
        face = self.spec.get("facing")
        self.player.facing = FACING.get(str(face).lower(), 0) if face else (self.world.facing or 0)
        from .atmosphere import Atmosphere
        self.atmosphere = Atmosphere(self) if Atmosphere.wanted(self) else None    # light and weather

    def protos(self):
        """The level's monsters and items, and those its world may put about later: for their pictures."""
        mons, items = list(self.monsters), list(self.items)
        if self.world is not None:
            kinds, iids = self.world.meets()
            for k in sorted(kinds):
                spec = (self.data.monsters or {}).get(k)
                if isinstance(spec, dict):
                    mons.append(Monster(0, k, spec, 0, 0, "?"))
            for i in sorted(iids):
                spec = (self.data.items or {}).get(i)
                if isinstance(spec, dict):
                    items.append(Item(i, spec, 0, 0))
        return mons, items

    def parse_map(self):
        legend = dict(LEGEND)
        legend.update(self.spec.get("legend") or {})
        rows = [str(r) for r in self.spec.get("map") or []]
        gen = self.spec.get("generate")
        if isinstance(gen, dict):                        # a map made from a seed: a dungeon's floor
            from .levelgen import generate
            rows, more = generate(gen, random.Random(self.world_seed), self.depth, self.data, legend)
            legend.update(more)
        self.h = len(rows)
        self.w = max((len(r) for r in rows), default=0)
        self.map_w, self.map_h = self.w, self.h
        self.land = None
        ax = ay = 0
        if isinstance(self.spec.get("land"), dict):         # open land: the map stands on it, the rest is the land's
            from .land import Land
            lspec = self.spec["land"]
            self.land = Land(lspec, seed=zlib.crc32(str(self.id).encode()) & 0xFFFF)
            self.land.look(fp.sky_spec(self.spec.get("sky")))   # its light, before the ground is worked out
            ax, ay = self.land.at
            if rows:
                self.land.set_pad(ax, ay, ax + self.w - 1, ay + self.h - 1, lspec.get("pad"), lspec.get("blend", 6))
            self.w, self.h = self.land.w, self.land.h
        self.grid = []
        start = None
        for y in range(self.h):
            line = []
            for x in range(self.w):
                if self.land is not None:
                    mx, my = x - ax, y - ay
                    ch = rows[my][mx] if 0 <= my < len(rows) and 0 <= mx < len(rows[my]) else " "
                    if ch == " ":
                        line.append(Cell(x, y, self.land.char(x, y), self.land.cell_spec(x, y)))
                        continue
                    self.land.add_stamp(x, y)
                else:
                    ch = rows[y][x] if x < len(rows[y]) else " "
                spec = legend.get(ch)
                if spec is None:
                    spec = {}
                if isinstance(spec, str):
                    spec = {"monster": spec} if spec in (self.data.monsters or {}) else {"item": spec}
                cell = Cell(x, y, ch, {k: v for k, v in spec.items() if k not in ("monster", "item")})
                line.append(cell)
                if self.land is not None and cell.height:   # a terrace: the map's floor raised over the pad
                    self.land.terrace[(x, y)] = cell.height
                if spec.get("start"):
                    start = (x, y)
                if spec.get("monster"):
                    m = self.add_monster(spec["monster"], x, y)
                    if m is not None:
                        m.wake_on = spec.get("wake_on")
                        m.on_death = spec.get("on_death")
                        m.roll_dir = FACING.get(str(spec.get("roll") or "").lower()[:1])
                        if spec.get("awake"):
                            m.awake = True
                        if spec.get("squad"):
                            ai.squad.join(self, m, spec["squad"])
                if spec.get("item"):
                    it = self.add_item(spec["item"], x, y)
                    if it is not None:
                        it.on_pickup = spec.get("on_pickup")
            self.grid.append(line)
        if self.land is not None:
            start = self.place_on_land(legend, start)
        auto = (self.spec.get("squads") or {}).get("auto") if isinstance(self.spec.get("squads"), dict) else None
        if auto:                                         # brainy monsters put near each other: squads
            ai.group(self, auto)
        if start is None:
            start = next(((c.x, c.y) for row in self.grid for c in row if not c.solid), (1, 1))
        self.player.x, self.player.y = start
        self.player.facing = FACING.get(str(self.spec.get("facing", "n")).lower(), 0)
        # rooms with floors at heights: a step higher than step_up is not walked up (the mesh view draws them)
        self.heights = self.land is None and any(c.height or c.ceiling_height is not None
                                                 for row in self.grid for c in row)
        self.terraced = self.land is not None and bool(self.land.terrace)    # open land with terraces: steps too
        from .atmosphere import Atmosphere
        self.atmosphere = Atmosphere(self) if Atmosphere.wanted(self) else None    # light and weather
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
        self.rides = [c for c in cells if c.stairs or c.mag]
        self.timed_cells = [c for c in cells if c.open_for]
        self.belts = [c for c in cells if c.conveyor is not None]
        self.fires = {}                                  # (x, y) -> beats it burns on
        self.total_kills = sum(1 for m in self.monsters if not m.barrel and not m.spec.get("boss"))
        self.total_items = sum(1 for it in self.items if not it.mine) + sum(
            sum(1 for i in (c.locker or ()) + (c.supply or ()) if not self.mine_id(i)) for c in cells)
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

    def mine_id(self, iid):
        spec = (self.data.items or {}).get(iid)
        return isinstance(spec, dict) and isinstance((spec.get("pickup") or {}).get("mine"), dict)

    def add_item(self, iid, x, y):
        spec = (self.data.items or {}).get(iid)
        if not isinstance(spec, dict):
            return None
        it = Item(iid, spec, x, y)
        self.items.append(it)
        return it

    def load_models(self):
        """The 3D models the level's monsters and items use, built once for the game's data."""
        from . import model as model_mod
        table = getattr(self.data, "models", None) or {}
        built = getattr(self.data, "_built_models", None)
        if built is None or built[0] is not table:
            built = (table, {})
            try:
                self.data._built_models = built
            except AttributeError:
                pass
        mons, items = self.protos()
        want = {m.model for m in mons if m.model} | {it.model for it in items if it.model}
        if self.land is not None:
            want |= self.land.uses()[1]
        if self.world is not None:
            want |= self.world.maker.uses()[1]
        for name in want:
            if name in table and name not in built[1]:
                built[1].update(model_mod.load({name: table[name]}))
        self.models = {n: built[1][n] for n in want if n in built[1]}

    def load_sprites(self):
        from .sprite import _rgb, far_versions, walk_frames
        mons, items = self.protos()
        names = {m.sprite for m in mons} | {it.sprite for it in items}
        names |= {w.get("sprite") for w in self.weapons.values()} | {"fireball", "muzzle", "gore", "crate", "container",
                                                                     "grenade", "rocket"}
        names |= {m.vehicle.get("cockpit") for m in mons if m.vehicle}
        if self.land is not None:
            names |= self.land.uses()[0]
        if self.world is not None:
            names |= self.world.maker.uses()[0]
        names |= {(m.spec.get("attack") or {}).get("spawn") for m in mons}
        for kind in list(names):
            spec = (self.data.monsters or {}).get(kind)
            if isinstance(spec, dict):
                names.add(spec.get("sprite") or kind)
        movers = set()                                  # the pictures of monsters that walk
        for kind in {m.kind for m in mons} | {(m.spec.get("attack") or {}).get("spawn") for m in mons}:
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
            sc = data.get("scale")
            if isinstance(sc, (int, float)) and not isinstance(sc, bool) and 0.2 <= sc <= 4:
                pic.scale = float(sc)                   # a weapon drawn with more (or fewer) pixels, as big
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
        from .firstperson import clear_textures
        self.see_through |= {n for n in clear_textures() if n not in self.tiles}   # the engine's bars and fields
        self.floor_tile, self.ceiling_tile = self.spec.get("floor"), self.spec.get("ceiling")
        from .firstperson import sky_spec
        open_air = self.land is not None or (self.world is None and any(c.sky for row in self.grid for c in row))
        self.sky_look = sky_spec(self.spec.get("sky")) if open_air else None   # how the sky over open cells looks
        if self.land is not None and not (self.spec.get("land") or {}).get("sky_ridges"):
            self.sky_look["ridges"] = []                     # the land's own hills stand on the horizon
        if self.land is not None and self.world is None:     # the map's floors, drawn on the land; its walls
            for (x, y) in list(self.land.stamp):
                self.land.stamp[(x, y)] = self.stamp_floor(self.cell(x, y))
            self.land_walls = [(x, y) for (x, y) in self.land.stamp
                               if self.cell(x, y).kind in ("wall", "panel", "exit", "switch", "door")]

    def stamp_floor(self, c):
        """How a map cell's floor looks drawn on open land: a tile's rows, or None for the plain one."""
        name = c.floor or self.floor_tile
        if c.toxic and not name:
            return [[(60, 150, 50), (80, 180, 60)], [(80, 180, 60), (60, 150, 50)]]
        return fp.View.texture(self, name) if name else None

    # ---- the grid ------------------------------------------------------- #
    def place_on_land(self, legend, start):
        """Open land: its ``"things"`` where they are put, and its ``"scatter"``: so many of a monster or an
        item about the land (on the biomes named, near a place, away from the start), the same every time."""
        lspec = self.spec["land"]
        if start is None and isinstance(lspec.get("start"), list):
            start = tuple(int(v) for v in lspec["start"][:2])
        for t in lspec.get("things") or []:
            if not isinstance(t, dict) or not isinstance(t.get("at"), list):
                continue
            x, y = (int(v) for v in t["at"][:2])
            if not (0 <= x < self.w and 0 <= y < self.h):
                continue
            self.put_thing(t, x, y)
            if t.get("secret"):                          # a hidden place: found by standing on it
                self.grid[y][x].secret = True
        sx, sy = start or (self.w // 2, self.h // 2)
        for i, s in enumerate(lspec.get("scatter") or []):
            if not isinstance(s, dict) or not (s.get("monster") or s.get("item")):
                continue
            rng = random.Random("%s/%d/%d" % (self.id, self.land.seed, i))
            on = set(s.get("on") or [])
            near = s.get("near")
            radius = float(s.get("radius", max(self.w, self.h)))
            away = float(s.get("away", 8))
            floats = bool((self.data.monsters or {}).get(s.get("monster"), {}).get("float"))
            placed, tries = 0, 0
            while placed < int(s.get("count", 1)) and tries < 4000:
                tries += 1
                if isinstance(near, list):
                    x = int(near[0] + rng.uniform(-radius, radius))
                    y = int(near[1] + rng.uniform(-radius, radius))
                else:
                    x, y = rng.randrange(self.w), rng.randrange(self.h)
                c = self.cell(x, y)
                if c is VOID or c.solid or (x, y) in self.land.stamp or math.hypot(x - sx, y - sy) < away:
                    continue
                if (c.deep or c.steep) and not floats:
                    continue
                if on and self.land.biome_of(x, y) not in on:
                    continue
                if self.monster_at(x, y) is not None or any((it.x, it.y) == (x, y) for it in self.items):
                    continue
                self.put_thing(s, x, y)
                placed += 1
        return start

    def put_thing(self, spec, x, y):
        """A monster or an item of a land's ``things`` or ``scatter`` at (x, y)."""
        if spec.get("monster"):
            m = self.add_monster(spec["monster"], x, y)
            if m is not None:
                m.wake_on = spec.get("wake_on")
                m.on_death = spec.get("on_death")
                if spec.get("awake"):
                    m.awake = True
                if spec.get("squad"):
                    ai.squad.join(self, m, spec["squad"])
        if spec.get("item"):
            it = self.add_item(spec["item"], x, y)
            if it is not None:
                it.on_pickup = spec.get("on_pickup")

    def ground(self, x, y):
        """How high the ground is at (x, y) - cells or between them - above the floor the map stands on
        (in rooms, the floor of the cell there: 0 but where the map raises it)."""
        if self.land is None:
            if not getattr(self, "heights", False):
                return 0.0
            return self.floor_at(x, y)
        if (int(round(x)), int(round(y))) in self.land.stamp and float(x).is_integer() and float(y).is_integer():
            return self.land.terrace.get((int(x), int(y)), 0.0)
        return self.land.ground(x, y) - self.land.base

    def cell(self, x, y):
        if 0 <= y < self.h and 0 <= x < self.w:
            return self.grid[y][x]
        return VOID

    def crate_cells(self):
        return [(c.x, c.y) for row in self.grid for c in row if c.crate]

    def monster_at(self, x, y, skip=None):
        for m in self.monsters:
            if m.x == x and m.y == y and not m.dead and not m.gone and m is not skip:
                return m
        return None

    def passable(self, x, y, who=None, floats=False):
        """Can a monster (``who``, or one that floats) be at (x, y)? Deep water and slopes too steep to climb
        only for those that float."""
        c = self.cell(x, y)
        if c.solid:
            return False
        if c.deep or c.steep or c.pit:
            return floats or bool(getattr(who, "float", 0))
        return True

    def floor_at(self, x, y):
        """The floor's height at (x, y) in rooms: a cell's own at its middle, and between cells blended from the
        cells round the point that are not walls - walking up stairs, the eye rises smoothly."""
        ix, iy = int(math.floor(x)), int(math.floor(y))
        ux, uy = x - ix, y - iy
        total = weight = 0.0
        for cx, cy, w in ((ix, iy, (1 - ux) * (1 - uy)), (ix + 1, iy, ux * (1 - uy)), (ix, iy + 1, (1 - ux) * uy),
                          (ix + 1, iy + 1, ux * uy)):
            if w <= 0.0:
                continue
            c = self.cell(cx, cy)
            if c.drawn_as_wall():
                continue
            total += c.height * w
            weight += w
        if weight <= 0.0:
            return self.cell(int(math.floor(x + 0.5)), int(math.floor(y + 0.5))).height
        return total / weight

    def step_ok(self, x0, y0, x1, y1, floats=False):
        """Can a walker go from (x0, y0) to (x1, y1)? In rooms with heights, not up a step higher than step_up
        (down any). Floaters and fliers go anywhere."""
        if floats or not (getattr(self, "heights", False) or getattr(self, "terraced", False)):
            return True
        return self.cell(x1, y1).height - self.cell(x0, y0).height <= self.step_up + 1e-9

    def free(self, x, y, skip=None):
        p = self.player
        return self.passable(x, y, skip) and not self.monster_at(x, y, skip) and (x, y) != (p.x, p.y)

    def line_of_sight(self, x0, y0, x1, y1):
        cells = bresenham(x0, y0, x1, y1)
        for (x, y) in cells[1:-1]:
            c = self.cell(x, y)
            if c.solid and not c.clear:                  # bars and force fields are seen through
                return False
        if self.land is not None and len(cells) > 2:          # open land: a hill between hides
            h0, h1 = self.eye_height(x0, y0), self.eye_height(x1, y1)
            n = len(cells) - 1
            land = self.land
            stamp, height, base = land.stamp, land.height, land.base
            for i, (x, y) in enumerate(cells[1:-1], 1):         # ground() at a cell's middle: its own height
                g = land.terrace.get((x, y), 0.0) if (x, y) in stamp else height(x, y) - base
                if g > h0 + (h1 - h0) * i / n + 0.05:
                    return False
        elif getattr(self, "heights", False) and len(cells) > 2:     # rooms at heights: a ledge or a low ceiling
            h0, h1 = self.room_eye(x0, y0), self.room_eye(x1, y1)    # between hides, as the mesh view shows it
            n = len(cells) - 1
            for i, (x, y) in enumerate(cells[1:-1], 1):
                c = self.cell(x, y)
                line = h0 + (h1 - h0) * i / n
                if c.height > line + 0.05:
                    return False
                if c.ceiling_height is not None and not c.sky and c.ceiling_height < line - 0.05:
                    return False
        return True

    def room_eye(self, x, y):
        """How high one sees from at (x, y) in rooms at heights: the floor there, and a head above it."""
        p = self.player
        if (x, y) == (p.x, p.y) and p.ceiling:
            return self.ceiling_at(x, y) - 0.5
        m = self.monster_at(x, y)
        return self.ground(x, y) + 0.5 + (m.float if m is not None and m.float else 0.0)

    def covered(self, sx, sy, tx, ty):
        """Whether one at (tx, ty) is in cover from a shot from (sx, sy): a wall, a crate or a closed door right
        beside it that the line of fire grazes (it passes within three quarters of a cell of the middle of
        that cell, on the shooter's side), and the shooter two cells off or more. Walls along a corridor are
        no cover; the corner one leans out from is."""
        ux, uy = sx - tx, sy - ty
        uu = ux * ux + uy * uy
        if max(abs(ux), abs(uy)) < 2:
            return False
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cross = dx * uy - dy * ux
                if (dx or dy) and dx * ux + dy * uy > 0 and 16 * cross * cross < 9 * uu \
                        and self.cell(tx + dx, ty + dy).solid:
                    return True
        return False

    def crossfire(self, m):
        """How much surer a squad's gun is: others of its squad that see him from another side (60 degrees off)."""
        sq = m.squad
        if sq is None:
            return 0.0
        p = self.player
        ux, uy = m.x - p.x, m.y - p.y
        n = 0
        for o in sq.members:
            if o is m or o.dead or o.gone or not o.awake or o.attack.get("kind") not in ("hitscan", "projectile"):
                continue
            vx, vy = o.x - p.x, o.y - p.y
            dot = ux * vx + uy * vy
            if (dot <= 0 or 4 * dot * dot <= (ux * ux + uy * uy) * (vx * vx + vy * vy)) \
                    and max(abs(vx), abs(vy)) <= int(o.attack.get("range", 8)) and self.line_of_sight(o.x, o.y, p.x, p.y):
                n += 1
        return min(2, n) * CROSSFIRE

    def eye_height(self, x, y):
        """How high one sees from at (x, y) in open land: the ground, and a head above it (higher flying)."""
        p = self.player
        up = 0.5
        if (x, y) == (p.x, p.y) and p.vehicle is not None and p.vehicle.vehicle.get("fly") and p.vehicle.started:
            up = float(p.vehicle.vehicle.get("altitude", self.land.altitude))
        else:
            m = self.monster_at(x, y)
            if m is not None and m.float:
                up += m.float
        return self.ground(x, y) + up

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

    def sees(self, x0, y0, x1, y1):
        """Line of sight, and through the weather's fog no further than it lets one see."""
        if not self.line_of_sight(x0, y0, x1, y1):
            return False
        atm = getattr(self, "atmosphere", None)
        far = atm.sight() if atm is not None else None
        return far is None or max(abs(x1 - x0), abs(y1 - y0)) <= far

    def lit_enough(self, m):
        """A monster in the dark (light under 0.22) further than two cells is not seen - but through goggles."""
        atm = getattr(self, "atmosphere", None)
        if atm is None or not atm.lighting or self.player.nightvision or self.dist(m) <= 2:
            return True
        from .atmosphere import DARK
        return atm.light_here(m.x, m.y) >= DARK

    def update_seen(self):
        p = self.player
        for m in self.monsters:
            m.seen = (not m.dead and not m.gone and self.in_view(m.x, m.y)
                      and self.sees(p.x, p.y, m.x, m.y) and self.lit_enough(m))
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

    def distances(self, x0, y0, limit=40, floats=False):
        """Steps to (x0, y0) from every cell that can walk there - or float there (monsters do not block)."""
        f = Field(self, x0, y0, limit, floats)
        f.finish()
        return f.dist

    def ways(self, x0, y0, limit=40, floats=False):
        """``distances``, worked out only as far as it is asked (``.get``): the same numbers. Kept for this beat;
        if the map changes first, it is finished on the map as it was (``ways_change``)."""
        f = Field(self, x0, y0, limit, floats)
        self.__dict__.setdefault("_spreading", []).append(f)
        return f

    def ways_change(self):
        """The map is about to change: the ways still being worked out this beat are finished first, on the map as
        it was - so they give what working them out at once would have."""
        spreading = self.__dict__.get("_spreading")
        if spreading:
            for f in spreading:
                f.finish()
            del spreading[:]

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
            n = len(frames)
            for i, fx in enumerate(frames):                # the clock spinning parts turn by, within the beat
                if not fx.tick:
                    fx.tick = (i + 1) / float(n)
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
            if self.opening is None or not self.beat:        # a save from the very start begins like the level
                console.page(self, self.intro_lines())
            for text, role in self.opening or ():          # a loaded game: no title page, a word instead
                self.say(text, role)
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
        made = self.spec.get("generate") if isinstance(self.spec.get("generate"), dict) else self.spec.get("world")
        if isinstance(made, dict) and made.get("depth"):
            lines.append(("floor %d" % (self.depth + 1), "info"))   # a generated level: how deep this one is
        intro = self.spec.get("intro") or []
        for t in [intro] if isinstance(intro, str) else intro:   # a line, or a list of them
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
        """A typed line. Every line that plays is kept in the journal - a save is the journal, played
        back - except the ones about the game itself (save, load, saves, *LEVEL)."""
        line = (line or "").strip()
        if not line:
            return
        if META.fullmatch(line):
            if not self.replaying:
                self.meta(line)
            return
        self.journal.append([self.beat, line])           # the beat it was typed on: [beat, line] (player 0)
        m = DUELLED.search(line)
        if m:                                            # "use =won:57": the duel it started, as it went
            self.duel_answer, line = m.group(1), line[:m.start()]
        try:
            self.play_line(line)
        finally:
            self.duel_answer = None
            if self.over in ("quit", "load", "warp") and self.journal and self.journal[-1][1] == line:
                self.journal.pop()
        self.flush_save()

    # ---- card duels ------------------------------------------------------ #
    def duel(self, cid, spec):
        """A card duel with character ``cid`` (engine/cards.py), fought with the player's health. Its outcome is
        written into this line's journal entry (``use =won:57``), so a load plays it back without fighting
        again. Returns "won", "lost", "fled", or None when nobody is there to fight it."""
        p = self.player
        answer = self.duel_answer
        if answer is None and getattr(self, "_assume_duels", None) and self.host is None:
            answer = self._assume_duels                  # the level bot, with no game to fight it in
        if answer is None:
            if self.replaying or self.host is None or not hasattr(self.host, "duel"):
                if not self.replaying:
                    self.say("The terminal does not answer.", "dim")
                return None
            res = self.host.duel(self, cid, spec)
            if res is None:
                return None
            result, left = res
            answer = {"win": "won", "lose": "lost"}.get(result, "fled") + (":%d" % left if result == "win" else "")
            if self.journal:
                self.journal[-1][1] += " =" + answer
        result, _, left = answer.partition(":")
        if result == "won" and left.isdigit():
            p.hp = max(1, min(p.hp, int(left)))
        elif result == "lost":
            n = int(spec.get("feedback", 20))
            self.hurt(n, spec.get("feedback_text") or "Feedback through the jack: %d." % n)
        return result

    def flush_save(self):
        """A save asked for during a line (a checkpoint reached, "w; save") is made when the line is done,
        so it holds whole beats."""
        asked, self.pending_save = self.pending_save, []
        for slot, how in asked:
            if self.host is not None and not self.replaying and not self.over:
                self.host.save(self, slot, how=how)

    def play_line(self, line):
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
        if line != IDLE:                                 # a beat that passed in real time is nobody's command
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
        if META.fullmatch(t):                            # within a line: "w; save" (saved when the line is done)
            if self.replaying:
                return True
            word, _, arg = t.partition(" ")
            if word == "save":
                if self.host is None:
                    return self.meta(t)
                self.pending_save.append((arg.strip() or None, "save"))
                return True
            return self.meta(t)
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
        m = re.fullmatch(r"look(?:\s+(up|down|ahead|level))?", t)
        if m:
            return self.look_at(m.group(1))
        m = re.fullmatch(r"(?:goggles|nv)(?:\s+(on|off))?", t)
        if m:
            return self.goggles(m.group(1))
        m = re.fullmatch(r"(?:mag|magboots)(?:\s+(on|off))?", t)
        if m:
            return self.magswitch(m.group(1))
        m = re.fullmatch(r"(?:jet|jetpack)(?:\s+(on|off))?", t)
        if m:
            return self.jetpack(m.group(1))
        if t in ("dive", "surface"):
            return self.dive(None if t == "dive" and self.player.diving else ("down" if t == "dive" else "up"))
        if t == "whoami":
            self.say("rootless   (uid 1000; root was revoked)" if not self.player.sudo else "root   (for now)", "dim")
            if self.player.boots:
                self.say("Hazmat boots on: %d more beats in acid." % self.player.boots, "toxic")
            if self.saves_left is not None and not self.dev:
                self.say("Saves left in this level: %d." % self.saves_left, "dim")
            return True
        if t.startswith("sudo"):
            if self.player.sudo:
                self.say("You are root for %d more beats." % self.player.sudo, "root")
            else:
                self.say("rootless is not in the sudoers file. This incident will be reported.", "hurt")
            return True
        if t in ("?", "help"):
            self.console.page(self, HELP + (TOUCH_HELP if getattr(self.console, "touch", False) else []))
            return True
        if t in ("next", "nw", "next weapon"):
            return self.next_weapon()
        if t in ("q", "quit", "exit"):
            self.over = "quit"
            return True
        self.say("rootless: %s: command not found" % tok.strip(), "hurt")
        raise StopLine()

    # ---- saving, loading, jumping ------------------------------------------- #
    def meta(self, t):
        """``save [name]``, ``load [name]``, ``saves``, ``realtime [off|SECONDS]`` and ``*LEVEL`` (with --dev):
        about the game, not in it."""
        word, _, arg = t.partition(" ")
        arg = arg.strip() or None
        if word.startswith("*"):
            return self.jump(word[1:])
        if word == "realtime":
            return self.set_realtime(arg)
        if self.host is None:
            self.say("Saving needs the game round the level.", "dim")
            return False
        if word == "saves":
            return self.host.list(self)
        if word == "save":
            return self.host.save(self, arg)
        return self.host.load(self, arg)

    def set_realtime(self, arg):
        """``realtime``: beats pass on their own (0.8 s, or the seconds given); ``realtime off``: they wait."""
        con = self.console
        if con is None or getattr(con, "keys", None) is None or not hasattr(con, "realtime"):
            self.say("Real time needs single keys in a redrawn screen.", "dim")
            return False
        if arg == "off":
            con.realtime = 0
            self.say("The world waits for you again.", "info")
            return True
        con.realtime = float(arg) if arg not in (None, "on") else (beat_of(self) or 0.8)
        self.say("Real time: a beat passes every %.1f s, whether you act or not. (realtime off: back)"
                 % con.realtime, "alert")
        return True

    def jump(self, lid):
        """``*e1m2``: on to that level's scene, as you are (for trying levels out: with --dev)."""
        if not self.dev:
            self.say("rootless: *%s: command not found" % lid, "hurt")
            return False
        levels = sorted(self.data.levels or {})
        if not lid:
            self.say("Levels: " + ", ".join("%s (%s)" % (k, (self.data.levels[k] or {}).get("name", k))
                                            for k in levels), "dim")
            return True
        if lid not in levels:
            self.say("There is no level '%s'. There are: %s." % (lid, ", ".join(levels)), "hurt")
            return False
        if self.host is None or not self.host.scene_of(lid):
            self.say("No scene plays level '%s', so there is nowhere to go on to from it." % lid, "hurt")
            return False
        self.warp, self.over = lid, "warp"
        return True

    def fingerprint(self):
        """What the level is made of, in short: a save notes it, and says so when it has changed."""
        d = self.data
        stuff = [self.spec, d.monsters, getattr(d, "weapons", None), d.items, self.cfg]
        return "%08x" % (zlib.crc32(json.dumps(stuff, sort_keys=True, default=str).encode("utf-8")) & 0xffffffff)

    def save_block(self):
        """The level in a save: how it began (id, seed, depth, the player as he came in), a snapshot of it
        now (engine/snapshot.py) with its digest, and the lines played since it began - the last
        ``JOURNAL_KEEP`` of them; ``lines_from`` says the beat they go back to, when not to the start."""
        from . import snapshot
        lines = [list(e) if isinstance(e, list) else e for e in self.journal]
        block = {"id": self.id, "seed": self.seed, "start": self.start_player, "depth": self.depth,
                 "beat": self.beat, "saves_left": self.saves_left, "fingerprint": self.fingerprint()}
        if len(lines) > JOURNAL_KEEP:
            lines = lines[-JOURNAL_KEEP:]
            block["lines_from"] = lines[0][0] if isinstance(lines[0], list) else 1
        block["lines"] = lines
        try:
            snap = snapshot.capture(self)
            block["snapshot"], block["digest"] = snapshot.pack(snap), snapshot.digest(snap)
        except snapshot.SnapshotError as e:              # the lines still carry it
            block["snapshot_error"] = str(e)
        return block

    def state_hash(self):
        """A short sum of the level's state: the same lines played on the same seed give the same sum,
        on any machine (what only looks different is left out)."""
        from . import snapshot
        return snapshot.digest(snapshot.capture(self))

    def replay(self, lines):
        """Play ``lines`` again, unseen and unheard: True if they played through without the level ending."""
        console, audio = self.console, self.audio
        self.console, self.audio, self.replaying = TextConsole(lambda text: None, lambda prompt: None), None, True
        try:
            for entry in lines:
                if isinstance(entry, list):              # [beat, line]: it must come on the same beat
                    if len(entry) < 2 or entry[0] != self.beat:
                        return False
                    entry = entry[1]
                self.run_line(entry)
                if self.over:
                    return False
            return True
        finally:
            self.console, self.audio, self.replaying = console, audio, False

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
        p.diving = bool(getattr(m, "dived", False))
        if "fuel" in spec:
            if p.fuel:
                self.refuel(m)
            elif m.fuel <= 0:
                self.say("The tanks are dry: it will not lift. Find fuel.", "alert")
        self.update_seen()
        self.arrive()
        self.end_beat()
        return True

    def fly_eye(self, v):
        """How high a flying machine's eye is above the ground: its ``"eye"`` in rooms, its ``"altitude"`` in
        open land."""
        if self.land is not None:
            return float(v.vehicle.get("altitude", self.land.altitude))
        return float(v.vehicle.get("eye", 0.74))

    def refuel(self, v):
        """The fuel the player carries goes into the machine's tanks."""
        p = self.player
        v.fuel += p.fuel
        self.say("You pour %d beats of fuel into the tanks (%d in all)." % (p.fuel, v.fuel), "good")
        p.fuel = 0
        self.sfx("refuel", "pickup")

    def fuel_beat(self):
        """A beat of a running machine: its fuel burns, and when the last of it is gone it comes down."""
        v = self.player.vehicle
        if v is None or not v.started or "fuel" not in v.vehicle:
            return
        v.fuel = max(0, v.fuel - 1)
        if v.fuel in (10, 5):
            self.say("Fuel: %d beats left." % v.fuel, "alert")
        if v.fuel:
            return
        spec = v.vehicle
        v.started = False
        self.sfx((spec.get("sounds") or {}).get("empty") or "power_down", "power")
        self.say(spec.get("empty") or "The engines cough and stop. The %s settles." % v.name, "alert")
        up = self.fly_eye(v) if spec.get("fly") else 0.52
        p = self.player
        here = self.cell(p.x, p.y)
        if spec.get("fly") and (here.deep or here.steep or here.toxic):   # it glides down where one can stand
            spot = self.landing(p.x, p.y)
            if spot is not None:
                ox, oy = p.x, p.y
                p.x, p.y = spot
                self.anim([FX(cam=(ox + (spot[0] - ox) * ease(i / 6.0), oy + (spot[1] - oy) * ease(i / 6.0)),
                              eye=up - (up - 0.52) * 0.3 * i / 6.0) for i in range(1, 7)], 0.07)
                self.say("It glides down on its last breath to firmer ground.", "dim")
                self.update_seen()
                up = up - (up - 0.52) * 0.3
        self.anim([FX(shake=s, whiten=w, eye=up - (up - 0.52) * k) for s, w, k in
                   ((1, 0.0, 0.1), (-1, 0.0, 0.3), (1, 0.1, 0.6), (0, 0.2, 0.85), (0, 0.35, 1.0))], 0.08)
        if spec.get("on_empty") == "exit":               # the ride is the end of the level
            self.exit_kind = "exit"
            self.over = "exit"

    def landing(self, x, y, reach=12):
        """The nearest cell a machine running dry can set down on, from (x, y): firm, dry and clear, with such a
        cell beside it to climb down to - or None."""
        def firm(n):
            c = self.cell(*n)
            return not (c.solid or c.kind == "door" or c.crate or c.deep or c.steep or c.toxic) \
                and not self.monster_at(*n) and n not in self.fires

        seen, frontier = {(x, y)}, [(x, y)]
        for _ in range(reach):
            nxt = []
            for (cx, cy) in frontier:
                for dx, dy in DIRS:
                    n = (cx + dx, cy + dy)
                    if n in seen:
                        continue
                    seen.add(n)
                    c = self.cell(*n)
                    if c.solid or c.kind == "door" or c.crate:
                        continue
                    if firm(n) and any(firm((n[0] + ex, n[1] + ey)) for ex, ey in DIRS):
                        return n
                    nxt.append(n)
            frontier = nxt
        return None

    def leave(self):
        """Climb down from the vehicle: behind you, or to a side - it stays where it stands."""
        p = self.player
        v = p.vehicle
        if v is None:
            self.say("You are on your own two feet already.", "dim")
            return False
        if getattr(v, "dived", False):
            self.say("Not under water: surface first (F6).", "dim")
            return False
        fx, fy = DIRS[p.facing]
        rx, ry = DIRS[(p.facing + 1) % 4]
        sides = [(-fx, -fy), (-rx, -ry), (rx, ry), (fx, fy)]
        ok = [(p.x + dx, p.y + dy) for dx, dy in sides if self.free(p.x + dx, p.y + dy)]
        dry = [c for c in ok if not self.cell(*c).toxic and c not in self.fires] or ([] if v.vehicle.get("fly") else ok)
        if not dry:
            self.say("Not here: set down by dry floor first." if ok else "No room to climb down here.", "dim")
            return False
        v.started = False
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
    def look_at(self, way=None):
        """Look up or down a step, or straight ahead again (a free action; the mesh view draws it - the classic
        picture always looks straight ahead)."""
        p = self.player
        if way == "up":
            p.look = min(LOOK_STEPS, p.look + 1)
        elif way == "down":
            p.look = max(-LOOK_STEPS, p.look - 1)
        else:
            p.look = 0
        return True

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
        if p.ceiling:                                    # upside down: right on the screen is left in the world
            d = -d
        old_cells = self.console.snapshot(self) if self.console else None
        p.facing = (p.facing + d) % 4
        self.update_seen()
        if old_cells is not None:
            self.console.turn(self, old_cells, -1 if d < 0 else 1)
        return True

    def step(self, side, ahead):
        p = self.player
        if p.ceiling:
            return self.ceiling_step(-side, ahead)       # upside down: a step to the right is to the world's left
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
            if "fuel" in v.vehicle and not v.started:
                if v.fuel <= 0:
                    self.say("The tanks are dry: the %s will not lift. Find fuel." % v.name, "dim")
                    self.sfx("locked")
                    return False
                v.started = True
                self.sfx((v.vehicle.get("sounds") or {}).get("start") or "power", "power")
                self.say(v.vehicle.get("start") or "The engines spool up. (%d beats of fuel)" % v.fuel, "good")
                if v.vehicle.get("fly"):                    # it lifts: the eye goes up with it
                    up = self.fly_eye(v)
                    self.anim([FX(eye=0.52 + (up - 0.52) * k, shake=s) for k, s in
                               ((0.1, 1), (0.3, -1), (0.55, 1), (0.8, 0), (0.95, 0))], 0.07)
            m = self.monster_at(nx, ny)
            if (m is not None and not m.barrel and not m.spec.get("boss") and not m.float
                    and not v.vehicle.get("fly")):
                return self.stomp(m, nx, ny)
        if cell.crate and v is not None and v.vehicle.get("fly"):
            self.say("The %s bumps the %s and hovers back." % (v.name, "container" if cell.heavy else "crate"), "dim")
            return False
        if v is not None and v.vehicle.get("swim"):        # a submarine: in the water, and under its bulkheads
            if cell.bulkhead and p.diving:
                return self.under(nx, ny)
            if not cell.deep or cell.solid:
                if cell.bulkhead:
                    self.say("A bulkhead down into the water: dive (F6) to pass under it.", "dim")
                elif not cell.solid:
                    self.say("The %s stays in the water. (Enter or `out` beside a dock: climb out)" % v.name, "dim")
                else:
                    self.say("The hull grinds on the wall.", "dim")
                self.sfx("locked")
                return False
        flying = self.airborne()
        if v is None:
            boat = self.monster_at(nx, ny)
            if boat is not None and boat.vehicle and (cell.deep or cell.pit) and not flying and not p.diving:
                return self.board(boat)                      # a boat at the quay: step aboard
            if p.diving:                                     # under water: on through the water, or under a bulkhead
                if cell.bulkhead:
                    return self.under(nx, ny)
                if not cell.deep:
                    self.say("You are under water: surface first (F6, or surface).", "dim")
                    return False
        if not flying and not cell.solid and not self.step_ok(p.x, p.y, nx, ny):
            self.say("Too high a step to climb.", "dim")
            self.sfx("locked")
            return False
        if cell.pit and not cell.solid and not flying:
            self.say("A sheer drop. Without wings you would not climb out.", "dim")
            self.sfx("locked")
            return False
        swim = cell.deep and v is None and self.swims()
        if (cell.deep or cell.steep) and not cell.solid and not flying and not swim \
                and not (v is not None and v.vehicle.get("swim")):
            self.say("Too deep to wade." if cell.deep else "Too steep to climb.", "dim")
            self.sfx("locked")
            return False
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
        if m is not None and m.ball and side == 0 and ahead > 0:
            return self.push_ball(m, nx - p.x, ny - p.y)
        if m is not None and m.barrel and not m.vehicle and not m.ball:
            return self.push_barrel(m, nx - p.x, ny - p.y)
        if m is not None:
            self.say("%s is in the way." % m.tag, "dim")
            return False
        ox, oy = p.x, p.y
        was_wet = self.cell(ox, oy).deep
        p.x, p.y = nx, ny
        slid = self.slide_path(nx, ny, nx - ox, ny - oy)
        if slid and (flying or (p.mag_on and v is None)):  # in the air, or the magboots grip: no slide
            if not flying:
                self.say("Your magboots clamp to the slick deck.", "dim")
            slid = []
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
        wet = self.cell(nx, ny).toxic and not flying
        if v is not None:
            self.sfx((v.vehicle.get("sounds") or {}).get("step") or "footstep", "footstep")
        elif flying:
            self.sfx("jet", "power")
        elif cell.deep:
            self.sfx("swim", "footstep")
            if not was_wet:
                self.say("You swim. (F6: dive)", "info")
        else:
            self.sfx("wade", "footstep") if wet else self.sfx("footstep")
            if was_wet:
                self.say("You climb out of the water.", "dim")
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

    def ball_room(self, x, y):
        """Can a ball roll into (x, y)? Into anything but a wall or a crate - a hollow wall it breaks."""
        c = self.cell(x, y)
        return not c.solid or (c.kind == "panel" and c.panel == "fist")

    def set_rolling(self, b, dx, dy, cells=None):
        b.rolling = (dx, dy)
        b.left = int(b.spec.get("roll", 8)) if cells is None else cells
        b.heading = math.atan2(dy, dx)
        b.roll_wait = 0

    def push_ball(self, b, dx, dy):
        """Walk into a ball: it rolls away from you, and on, until something stops it."""
        p = self.player
        if not self.ball_room(b.x + dx, b.y + dy):
            self.say("The %s will not roll: something is behind it." % b.name, "dim")
            self.sfx("locked")
            return False
        self.set_rolling(b, dx, dy)
        self.sfx("push", "drop")
        self.anim([FX(cam=(p.x + dx * k, p.y + dy * k)) for k in (0.18, 0.3, 0.12, 0.0)], 0.035)
        self.say("You shove the %s and it rolls." % b.name, "dim")
        self.end_beat()
        return True

    def roll(self):
        """Rolling balls go on, ``speed`` cells a beat, until a wall, a crate or something that will not
        give stops them: what they meet is crushed, another ball is knocked on, a hollow wall breaks,
        and in acid they sink and make a step."""
        rolling = [m for m in self.monsters if m.ball and m.rolling and not m.gone]
        for b in rolling:
            if self.over:
                return
            if b.roll_wait:
                b.roll_wait -= 1
                self.sfx("rumble", "door")
                self.say("A rumble. Something heavy starts to move.", "alert")
                self.anim([FX(shake=s) for s in (1, -1, 1, 0)], 0.05)
                self.interrupt = self.interrupt or "something is rolling"
                continue
            for _ in range(max(1, int(b.spec.get("speed", 2)))):
                if not b.rolling or b.left <= 0 or self.over or not self.roll_on(b):
                    break
            if b.rolling and b.left <= 0:
                b.rolling = None
        if rolling:
            self.update_seen()

    def roll_on(self, b):
        """A ball's next cell: True if it got there."""
        dx, dy = b.rolling
        nx, ny = b.x + dx, b.y + dy
        c = self.cell(nx, ny)
        p = self.player
        lo, hi = b.spec.get("crush") or [25, 35]
        big = b.size >= 1.3

        def stop(text, sound="thud"):
            b.rolling, b.left = None, 0
            self.sfx(sound, "hit_wall")
            if text:
                self.say(text, "dim")
            if big:
                self.anim([FX(shake=s) for s in (1, -1, 0)], 0.05)
            return False

        if c.kind == "panel" and c.panel == "fist":         # it smashes through, and rolls on
            self.say("The %s smashes into the hollow wall - and through it." % b.name, "secret")
            self.sfx("thud", "hit_wall")
            self.open_panel(c)
        if c.solid or c is VOID:
            return stop("The %s crashes into the %s and stops." % (b.name, "crate" if c.crate else
                                                                     "door" if c.kind == "door" else "wall"))
        if (nx, ny) == (p.x, p.y):
            self.hurt(self.rng.randint(lo, hi), "The %s rolls into you." % b.name, by=b)
            return stop(None)
        o = self.monster_at(nx, ny)
        if o is not None:
            if o.ball:                                   # it stops; the one it hit rolls on
                self.set_rolling(o, dx, dy, cells=max(2, b.left))
                return stop("%s knocks %s on." % (b.tag, o.tag), "clack")
            if o.barrel and not o.vehicle:
                stop(None)
                self.kill(o)
                return False
            if o.vehicle or o.spec.get("boss"):
                return stop("The %s thuds against %s." % (b.name, o.tag))
            self.damage([(o, self.rng.randint(lo, hi))], lead="The %s rolls into it:" % b.name)
            if not o.dead or self.over:
                return stop(None)
        ox, oy = b.x, b.y
        b.x, b.y = nx, ny
        b.rolled += 1
        b.left -= 1
        self.anim([FX(pos={b.id: (ox + dx * k, oy + dy * k)}) for k in (0.34, 0.67, 1.0)], 0.03)
        if c.toxic:                                      # heavy: it sinks, and fills the pool
            self.sink(b)
            return False
        return True

    def sink(self, b):
        """A ball in acid sinks, and fills the cell: a step you can stand on."""
        c = self.cell(b.x, b.y)
        c.toxic, c.sunk = False, True
        self.marks_version += 1
        b.gone, b.rolling = True, None
        self.say("The %s sinks into the acid and settles: a step you can stand on." % b.name, "good")
        self.sfx("wade", "drop")

    def push(self, cell, dx, dy):
        """Walk into a crate: it slides one cell on, if there is room - into acid, it sinks and makes a step."""
        self.ways_change()                               # the map may change
        p = self.player
        bx, by = cell.x + dx, cell.y + dy
        beyond = self.cell(bx, by)
        if (beyond.solid or self.monster_at(bx, by) or beyond.teleport or beyond.lift
                or any(not it.taken and (it.x, it.y) == (bx, by) for it in self.items)):
            self.say("The crate will not move: something is behind it.", "dim")
            self.sfx("locked")
            return False
        heavy, load = cell.heavy, (cell.supply, cell.opened)
        cell.crate = cell.heavy = cell.opened = False
        cell.supply = None
        ox, oy = p.x, p.y
        p.x, p.y = cell.x, cell.y
        path = [(cell.x, cell.y), (bx, by)] + ([] if beyond.toxic or heavy else self.slide_path(bx, by, dx, dy, crate=True))
        bx, by = path[-1]
        beyond = self.cell(bx, by)
        beyond.crate, beyond.heavy = True, heavy
        beyond.supply, beyond.opened = load
        self.sfx("push", "drop")
        n = len(path) - 1
        frames = 4 * n
        self.anim([FX(cam=(ox + dx * ease(min(1.0, i / 4.0)), oy + dy * ease(min(1.0, i / 4.0))),
                      crates={(bx, by): self.along(path, i / float(frames))}) for i in range(1, frames + 1)], 0.035)
        if beyond.toxic:
            beyond.crate, beyond.heavy, beyond.toxic, beyond.sunk = False, False, False, True
            beyond.supply, beyond.opened = None, False
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
        weight = {(m.x, m.y) for m in self.monsters if not m.dead and not m.gone and not m.float}
        if not p.ceiling:
            weight.add((p.x, p.y))
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
                        self.ways_change()                   # the map changes: the beat's ways first
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
                    self.ways_change()
                    c.open = 0.0
            elif want and c.kind == "wall":
                self.ways_change()
                c.kind = "floor"
            elif not want and c.kind == "floor" and not here:
                self.ways_change()
                c.kind = "wall"
        self.update_seen()

    def arrive(self, teleported=False):
        p = self.player
        if p.ceiling:                                    # on the ceiling: what lies on the floor is out of reach
            self.arrive_ceiling()
            return
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
        if cell.savepoint and (p.x, p.y) not in self.reached:      # a checkpoint
            self.reached.add((p.x, p.y))
            if self.host is not None and not self.replaying:
                self.pending_save.append((None, "checkpoint"))   # saved when this line is done
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

    # ---- stairs, magnetic plating, the jetpack, the water ------------------ #
    def airborne(self):
        """In the air: on the jetpack, or in a flying machine that has lifted."""
        p = self.player
        v = p.vehicle
        return bool(p.jet_on) or (v is not None and bool(v.vehicle.get("fly")) and bool(getattr(v, "started", False)))

    def swims(self):
        """Deep water can be swum here: the level's (or the game's first_person) ``"swim"``."""
        return bool(self.spec.get("swim", self.cfg.get("swim", False)))

    def swimming(self):
        """On foot in deep water (at the top, or under it)."""
        p = self.player
        return p.vehicle is None and not p.jet_on and self.cell(p.x, p.y).deep

    def breath(self):
        return int(self.cfg.get("breath", 20))

    def landing_of(self, cell):
        """Where one steps off stairs or plating: the side its ``"facing"`` names, else the first open floor
        beside it - and the way out from it."""
        want = FACING.get(str(cell.pad_facing or "")[:1].lower())
        for dx, dy in ([DIRS[want]] if want is not None else []) + list(DIRS):
            c = self.cell(cell.x + dx, cell.y + dy)
            if not c.solid and not c.deep and not c.pit and not c.toxic and not c.crate \
                    and self.monster_at(c.x, c.y) is None:
                return (c.x, c.y), DIRS.index((dx, dy))
        return None, None

    def climb(self, cell):
        """Stairs (walked into) or magnetic plating (walked up, in magboots): to the other end of the same name,
        stepping off it facing away. The stairs climb past; on the plating the world tips on its side."""
        p = self.player
        mag = bool(cell.mag)
        if mag and not p.mag_on:
            self.say("Magnetic plating, ribbed for boots that grip it." +
                     (" (F3: magboots on)" if p.magboots else ""), "dim")
            return False
        if self.swimming():
            self.say("Not from the water.", "dim")
            return False
        name = cell.mag if mag else cell.stairs
        dest = next((c for c in self.rides if (c.mag if mag else c.stairs) == name and c is not cell), None)
        if dest is None:
            self.say("It leads nowhere." if mag else "The stairs lead nowhere.", "dim")
            return False
        (lx, ly), face = self.landing_of(dest)
        if face is None:
            self.say("Something blocks the way at the other end.", "dim")
            return False
        up = dest.deck >= cell.deck
        console = self.console
        if mag:
            old = console.snapshot(self, style="pixel") if console else None
            rolled = getattr(console, "rolled", None)
            olds = rolled(self, TIP) if rolled and old is not None else None      # the mesh view: turned whole
            p.x, p.y, p.facing = lx, ly, face
            self.update_seen()
            new = console.snapshot(self, style="pixel") if console else None
            news = rolled(self, TIP_BACK) if olds else None
            self.sfx("magwalk", "footstep")
            if console is not None and old is not None:
                console.tilt(self, old, new, up, olds, news)
            self.say("The magboots clamp; the world tips on its side; you walk %s the plating." % ("up" if up else "down"),
                     "info")
        else:
            d = 1 if up else -1
            self.anim([FX(eye=0.52 + d * 0.06 * i, shake=(1 if i % 2 else -1)) for i in range(1, 5)], 0.07)
            old = console.snapshot(self) if console else None
            p.x, p.y, p.facing = lx, ly, face
            self.update_seen()
            new = console.snapshot(self) if console else None
            self.sfx("stairs", "footstep")
            if console is not None and old is not None:
                console.ride(self, old, new, not up)
            self.anim([FX(eye=0.52 - d * 0.05 * (3 - i), shake=(1 if i % 2 else -1) if i < 3 else 0)
                       for i in range(1, 4)], 0.07)
            self.say("You climb the stairs %s." % ("up" if up else "down"), "info")
        self.arrive()
        self.end_beat()
        return True

    def under(self, nx, ny):
        """Under a bulkhead, under water: out the other side of it, a beat."""
        p = self.player
        dx, dy = nx - p.x, ny - p.y
        bx, by = nx + dx, ny + dy
        beyond = self.cell(bx, by)
        if not beyond.deep or beyond.solid or (self.monster_at(bx, by) is not None):
            self.say("The water under the bulkhead is blocked.", "dim")
            return False
        ox, oy = p.x, p.y
        p.x, p.y = bx, by
        self.sfx("swim", "footstep")
        dark = [FX(cam=(ox + 2 * dx * k, oy + 2 * dy * k), fade=f) for k, f in ((0.25, 0.5), (0.5, 0.85), (0.75, 0.5), (1.0, 0.0))]
        self.anim(dark, 0.05)
        self.say("You pass under the bulkhead." if p.vehicle is None else "The %s noses under the bulkhead." % p.vehicle.name,
                 "info")
        self.update_seen()
        self.arrive()
        self.end_beat()
        return True

    # ---- the world sideways ---------------------------------------------- #
    def down_at(self, x, y):
        """Which way in the map the world's down is at (x, y): an index into DIRS, or None (the floor is the
        floor). Walls walked as floors - a building's face, a lift shaft - say so with ``"world_up"``."""
        c = self.cell(x, y)
        return None if c is None or c.world_up is None else (c.world_up + 2) % 4

    def shed(self):
        """Cells that drop falling things (``"sheds"``: monster, every, near, first): glass from a broken
        window, a counterweight down a shaft - while the player is near enough to meet them."""
        sheds = self.__dict__.get("_sheds")
        if sheds is None:
            sheds = self.__dict__["_sheds"] = [c for row in self.grid for c in row if c.sheds] \
                if self.world is None else []
        p = self.player
        for c in sheds:
            sp = c.sheds
            every = max(1, int(sp.get("every", 6)))
            if (self.beat - int(sp.get("first", 0))) % every or \
                    max(abs(c.x - p.x), abs(c.y - p.y)) > int(sp.get("near", 14)):
                continue
            x, y = c.x, c.y
            if c.solid:                                  # out of a window in a wall: into the cell below it
                down = self.down_at(x, y)
                if down is None:
                    continue
                x, y = x + DIRS[down][0], y + DIRS[down][1]
            if not self.free(x, y) or self.cell(x, y).solid:
                continue
            m = self.add_monster(sp.get("monster", "glass"), x, y)
            if m is not None:
                m.awake = True
                m.intent = "fresh"                       # seen where it comes from first; it falls from the next beat

    def fall_step(self, m):
        """A falling thing's beat: ``speed`` cells the world's way down, hurting what it meets - the player
        (not on the ceiling, unless it ``fills`` the way), a monster - and breaking on it or on what stops it."""
        f = m.spec["falls"] if isinstance(m.spec.get("falls"), dict) else {}
        p = self.player
        if m.intent == "fresh":
            m.intent = None
            return
        for _ in range(max(1, int(f.get("speed", 2)))):
            down = self.down_at(m.x, m.y)
            if down is None:
                return self.shatter(m)
            nx, ny = m.x + DIRS[down][0], m.y + DIRS[down][1]
            cell = self.cell(nx, ny)
            if (nx, ny) == (p.x, p.y) and (not p.ceiling or f.get("fills")):
                lo, hi = f.get("damage", [6, 10])
                self.hurt(self.rng.randint(int(lo), int(hi)), "%s hits you." % m.spec.get("name", m.kind).capitalize())
                return self.shatter(m)
            other = self.monster_at(nx, ny)
            if other is not None and other is not m and not other.dead:
                lo, hi = f.get("damage", [6, 10])
                self.damage([(other, self.rng.randint(int(lo), int(hi)))])
                return self.shatter(m)
            if cell is None or cell.solid or cell.world_up is None:
                return self.shatter(m)
            m.x, m.y = nx, ny

    def shatter(self, m):
        """A falling thing breaks (or goes on down, out of sight): gone, and not counted."""
        m.dead = m.gone = True
        if m.seen or self.dist(m) <= 4:
            self.sfx((m.spec.get("sounds") or {}).get("death") or "crate", "hit")

    # ---- on the ceiling ------------------------------------------------- #
    @staticmethod
    def top_of(cell):
        """A cell's ceiling (in walls' heights): its own, else a wall's height over its floor."""
        return cell.ceiling_height if cell.ceiling_height is not None else cell.height + 1.0

    def ceiling_at(self, x, y):
        """How high the ceiling is at (x, y): a cell's own at its middle, blended between cells (1 in flat rooms)."""
        if not getattr(self, "heights", False):
            return self.top_of(self.cell(int(round(x)), int(round(y))))
        ix, iy = int(math.floor(x)), int(math.floor(y))
        ux, uy = x - ix, y - iy
        total = weight = 0.0
        for cx, cy, w in ((ix, iy, (1 - ux) * (1 - uy)), (ix + 1, iy, ux * (1 - uy)), (ix, iy + 1, (1 - ux) * uy),
                          (ix + 1, iy + 1, ux * uy)):
            c = self.cell(cx, cy)
            if w <= 0.0 or c.drawn_as_wall():
                continue
            total += self.top_of(c) * w
            weight += w
        if weight <= 0.0:
            return self.top_of(self.cell(int(math.floor(x + 0.5)), int(math.floor(y + 0.5))))
        return total / weight

    def room_over(self, cell):
        """How far a cell's ceiling is over its floor: in a room this low (1.3), both are within reach."""
        return self.top_of(cell) - cell.height

    def ceiling_ok(self, x0, y0, x1, y1):
        """Can magboots walk the ceiling from (x0, y0) to (x1, y1)? Plated, under no sky, nothing standing up to
        it (a wall, a shut door; a crate only if there is room over it), and no step in it higher than climb."""
        c = self.cell(x1, y1)
        if c is None or not c.ceiling_mag or c.sky:
            return False
        if c.solid and not (c.crate and self.room_over(c) > 1.15):
            return False
        if getattr(self, "heights", False) and abs(self.top_of(c) - self.top_of(self.cell(x0, y0))) > self.step_up + 1e-9:
            return False
        return True

    def within_reach(self, cell):
        """Whether the thing ahead can be reached: from the ceiling only what is up by it (``"high"``), from the
        floor only what is not - but in a room no higher than 1.3, both."""
        p = self.player
        low = self.room_over(self.cell(p.x, p.y)) <= 1.3
        if low or cell.kind == "door" or not (cell.solid or cell.high):
            return True
        if p.ceiling and not cell.high:
            self.say("Out of reach from up here: it is down by the floor.", "dim")
            return False
        if not p.ceiling and cell.high:
            self.say("Out of reach: it is up by the ceiling.%s" % (" Magboots could take you there." if
                                                                 p.magboots else ""), "dim")
            return False
        return True

    def reaches_up(self, m):
        """Can a monster's bite reach the player on the ceiling? Not in a room higher than 1.3, unless it flies."""
        p = self.player
        return not p.ceiling or bool(m.float) or self.room_over(self.cell(p.x, p.y)) <= 1.3

    def ceiling_step(self, side, ahead):
        """A step along the ceiling (``side`` already the world's): over what is on the floor - acid, fire,
        monsters, pits - but not past a wall, a shut door, bare or open ceiling, or a step too high."""
        p = self.player
        fx, fy = DIRS[p.facing]
        rx, ry = DIRS[(p.facing + 1) % 4]
        nx, ny = p.x + fx * ahead + rx * side, p.y + fy * ahead + ry * side
        cell = self.cell(nx, ny)
        if cell.mag_ceiling and ahead > 0 and side == 0:
            return self.up_wall(cell)
        if cell.solid and not (cell.crate and self.room_over(cell) > 1.15):
            if ahead > 0 and side == 0:
                return self.use()
            self.say("A wall.", "dim")
            return False
        if not self.ceiling_ok(p.x, p.y, nx, ny):
            if cell.sky:
                self.say("Open sky over there: nothing for the boots to hold.", "dim")
            elif not cell.ceiling_mag:
                self.say("The ceiling there is bare: nothing for the boots to hold.", "dim")
            else:
                self.say("Too high a step in the ceiling.", "dim")
            self.sfx("locked")
            return False
        m = self.monster_at(nx, ny)
        if m is not None and m.float and not m.dead:
            self.say("%s is in the way." % m.tag, "dim")
            return False
        ox, oy = p.x, p.y
        p.x, p.y = nx, ny
        self.sfx("magwalk", "footstep")
        self.anim([FX(cam=(ox + (nx - ox) * ease(i / 4.0), oy + (ny - oy) * ease(i / 4.0))) for i in range(1, 5)], 0.03)
        self.update_seen()
        self.arrive()
        self.end_beat()
        return True

    def arrive_ceiling(self):
        """On the ceiling of a cell: a secret, its event, a checkpoint - but nothing on the floor."""
        p = self.player
        cell = self.cell(p.x, p.y)
        if cell.secret and not cell.found and not cell.panel:
            cell.found = True
            self.stats["secrets"] += 1
            self.sfx("secret")
            self.say("A secret area!", "secret")
        if cell.on_enter and cell.on_enter not in self.events:
            self.event(cell.on_enter)
        if cell.savepoint and (p.x, p.y) not in self.reached:
            self.reached.add((p.x, p.y))
            if self.host is not None and not self.replaying:
                self.pending_save.append((None, "checkpoint"))

    def flip_ride(self, change, tip, back, down=False):
        """The view turning as he goes from the floor to the ceiling or back: the picture at ``tip``'s angles,
        ``change()`` done, then at ``back``'s (the mesh view turned whole; else the picture)."""
        console = self.console
        old = console.snapshot(self, style="pixel") if console else None
        rolled = getattr(console, "rolled", None)
        olds = rolled(self, tip) if rolled and old is not None else None
        change()
        self.update_seen()
        new = console.snapshot(self, style="pixel") if console else None
        news = rolled(self, back) if olds else None
        if console is not None and old is not None:
            console.tilt(self, old, new, not down, olds, news, tip, back)

    def up_wall(self, cell):
        """Plating up to the ceiling, walked into in magboots: up the wall and on to the ceiling of the cell he
        stands in, facing back into the room - or, from the ceiling, down it to the floor."""
        p = self.player
        here = self.cell(p.x, p.y)
        if not p.mag_on:
            self.say("Magnetic plating, up to the ceiling." + (" (F3: magboots on)" if p.magboots else ""), "dim")
            self.sfx("locked")
            return False
        if p.vehicle is not None or p.jet_on or self.swimming():
            self.say("Not from here.", "dim")
            return False
        if p.ceiling:
            def change():
                p.ceiling = False
                p.facing = (p.facing + 2) % 4
            self.sfx("magwalk", "footstep")
            self.flip_ride(change, (-10, -28, -52, -76, -90), TIP_BACK, down=True)
            self.say("Down the plating, and on your feet again.", "info")
        else:
            if not here.ceiling_mag or here.sky:
                self.say("The plating ends at a bare ceiling: nothing to hold on to up there.", "dim")
                self.sfx("locked")
                return False

            def change():
                p.ceiling = True
                p.facing = (p.facing + 2) % 4
            self.sfx("magwalk", "footstep")
            self.flip_ride(change, TIP, (-90, -72, -46, -22, -6))
            self.say("Up the plating and on to the ceiling: the world hangs below you. (F3: let go)", "info")
        self.update_seen()
        self.end_beat()
        return True

    def drop(self, why=None):
        """Off the ceiling: he falls to the floor (hurt by a long fall), on to whatever stands there."""
        p = self.player
        here = self.cell(p.x, p.y)
        fall = self.room_over(here)

        def change():
            p.ceiling = False
        self.flip_ride(change, (-30, -60, -90), (90, 60, 30), down=True)
        if why:
            self.say(why, "alert")
        self.sfx("land", "footstep")
        m = self.monster_at(p.x, p.y)
        if m is not None and not m.dead:                 # on to it: a stomp
            self.damage([(m, int(30 + 20 * fall))], lead="You land on it:")
            if self.over:
                return True
            if not m.dead:
                spot = next(((m.x + dx, m.y + dy) for dx, dy in DIRS if self.free(m.x + dx, m.y + dy, skip=m)), None)
                if spot is not None:
                    m.x, m.y = spot
                    self.say("%s is thrown aside." % m.tag, "hit")
                else:
                    spot = next(((p.x + dx, p.y + dy) for dx, dy in DIRS if self.free(p.x + dx, p.y + dy)), None)
                    if spot is not None:
                        p.x, p.y = spot
        hurt = int(max(0.0, fall - 1.25) * 25)
        if here.pit:
            self.hurt(999, "You fall into the pit.")
        elif hurt:
            self.hurt(hurt, "You land hard.")
        else:
            self.say("You drop, turn over and land on your feet.", "dim")
        self.update_seen()
        if not self.over:
            self.arrive()
            self.end_beat()
        return True

    def cut_plating(self, cell):
        """A plated ceiling loses its power: the boots let go of it."""
        cell.ceiling_mag = False
        p = self.player
        if p.ceiling and (p.x, p.y) == (cell.x, cell.y):
            self.sfx("mag_off", "switch")
            self.drop("The plating over you dies. Your boots let go.")
        elif p.ceiling and abs(p.x - cell.x) + abs(p.y - cell.y) <= 3:
            self.sfx("mag_off", "switch")
            self.say("The plating near you goes dead.", "alert")

    def through_hatch(self, here):
        """A hatch: from under it, on the ceiling, up through it to the floor of the deck above; from above, down
        through it - on to the ceiling below in magboots, or a drop to its floor."""
        p = self.player
        dest = next((c for row in self.grid for c in row if c.hatch == here.hatch and c is not here), None)
        if dest is None:
            self.say("The hatch is welded shut.", "dim")
            return False
        up = dest.deck > here.deck
        if up and not p.ceiling:
            self.say("A hatch in the ceiling, out of reach.%s" % (" Magboots could take you up there." if p.magboots
                                                                   else ""), "dim")
            return False
        if not up and p.ceiling:
            self.say("The hatch leads down: let go first.", "dim")
            return False
        if self.monster_at(dest.x, dest.y) is not None:
            self.say("Something is on the hatch at the other side.", "dim")
            return False
        land_on = not up and p.mag_on and dest.ceiling_mag and not dest.sky

        def change():
            p.x, p.y = dest.x, dest.y
            p.ceiling = land_on
        console = self.console
        old = console.snapshot(self, style="pixel") if console else None
        self.sfx("door")
        change()
        self.update_seen()
        new = console.snapshot(self, style="pixel") if console else None
        if console is not None and old is not None:
            console.ride(self, old, new, not up)
        if up:
            self.say("You climb up through the hatch.", "info")
        elif land_on:
            self.say("Down through the hatch; your boots catch the ceiling below.", "info")
        else:
            fall = self.room_over(dest)
            hurt = int(max(0.0, fall - 1.25) * 25)
            self.say("Down through the hatch.", "info")
            if hurt:
                self.hurt(hurt, "You land hard.")
        if not self.over:
            self.arrive()
            self.end_beat()
        return True

    def magswitch(self, how=None):
        """Magboots on (they grip: no sliding, belts do not carry him, the plating can be walked) or off."""
        p = self.player
        if not p.magboots:
            self.say("You have no magboots.", "dim")
            return False
        want = (not p.mag_on) if how is None else how == "on"
        if want == p.mag_on:
            self.say("Your magboots are %s already." % ("on" if want else "off"), "dim")
            return True
        if not want and self.cell(p.x, p.y).world_up is not None:
            self.say("Not here: the boots are all that hold you to the wall, and it is a long way down.", "alert")
            return False
        if not want and p.ceiling:                       # letting go of the ceiling
            p.mag_on = False
            self.sfx("mag_off", "switch")
            self.say("Magboots off: you let go of the ceiling.", "info")
            return self.drop()
        p.mag_on = want
        self.sfx("mag_on" if want else "mag_off", "switch")
        self.say("Magboots on: they grip the deck." if want else "Magboots off: your feet are your own again.", "info")
        return True

    def jetpack(self, how=None):
        """Up on the jetpack (a beat of fuel a beat in the air, hands free) or down again."""
        p = self.player
        want = (not p.jet_on) if how is None else how == "on"
        if want == p.jet_on:
            self.say("You are in the air already." if want else "You are on the ground already.", "dim")
            return True
        if not want:
            return self.jet_land()
        if p.vehicle is not None:
            self.say("Not in the %s." % p.vehicle.name, "dim")
            return False
        if p.jet <= 0:
            self.say("The jetpack is dry." if self.jet_known else "You have no jetpack.", "dim")
            return False
        if p.diving:
            self.say("Not under water.", "dim")
            return False
        if p.ceiling or self.cell(p.x, p.y).world_up is not None:
            self.say("Not while you hang from the ceiling." if p.ceiling else "Not on a wall.", "dim")
            return False
        p.jet_on = True
        self.sfx("jet_on", "power")
        up = self.jet_eye()
        self.anim([FX(eye=0.52 + (up - 0.52) * k, shake=sh) for k, sh in ((0.15, 1), (0.4, -1), (0.7, 1), (0.9, 0), (1.0, 0))],
                  0.06)
        self.say("The jetpack roars and you are up. (%d beats of fuel; F4: land)" % p.jet, "good")
        self.end_beat()
        return True

    @property
    def jet_known(self):
        return any(it.taken and it.pickup.get("power") == "jetpack" for it in self.items)

    def jet_eye(self):
        if self.land is not None:
            return float(self.cfg.get("jet_altitude", self.land.altitude * 0.6))
        return float(self.cfg.get("jet_eye", 0.86))

    def jet_land(self, dry=False):
        """Down from the jetpack: here if it can be stood on (or swum, where swimming is), else - out of fuel -
        gliding to the nearest place that can; a drop with nowhere near is a fall."""
        p = self.player
        here = self.cell(p.x, p.y)
        ok = lambda c: not c.solid and not c.pit and not c.steep and not c.crate and (not c.deep or self.swims())  # noqa: E731
        spot = (p.x, p.y) if ok(here) and self.monster_at(p.x, p.y) is None else None
        if spot is None and not dry:
            self.say("Not here: there is nothing to land on.", "dim")
            return False
        if spot is None:                                 # dry over a drop: glide to the nearest edge
            seen, ring = {(p.x, p.y)}, [(p.x, p.y)]
            for _ in range(4):
                nxt = []
                for x, y in ring:
                    for dx, dy in DIRS:
                        n = (x + dx, y + dy)
                        if n not in seen and not self.cell(*n).solid:
                            seen.add(n)
                            nxt.append(n)
                spot = next((n for n in nxt if ok(self.cell(*n)) and self.monster_at(*n) is None), None)
                if spot or not nxt:
                    break
                ring = nxt
        p.jet_on = False
        if spot is None:
            self.say("The jetpack coughs and dies. You fall.", "hurt")
            self.anim([FX(eye=0.52 - 0.12 * i, fade=0.2 * i) for i in range(1, 5)], 0.06)
            p.hp = 0
            self.over = "dead"
            return True
        ox, oy = p.x, p.y
        p.x, p.y = spot
        eye = self.jet_eye()
        self.anim([FX(cam=(ox + (spot[0] - ox) * k, oy + (spot[1] - oy) * k), eye=eye - (eye - 0.52) * k)
                   for k in (0.25, 0.5, 0.75, 1.0)], 0.06)
        self.sfx("land", "footstep")
        self.say("The jetpack sputters out: you glide down." if dry else "You touch down.", "alert" if dry else "dim")
        self.update_seen()
        self.arrive()
        if not dry:
            self.end_beat()
        return True

    def dive(self, how=None):
        """Under the water and up again: swimming (breath runs down under it), or in a submarine."""
        p = self.player
        v = p.vehicle
        want = (not p.diving) if how is None else how == "down"
        if v is not None:
            if not v.vehicle.get("dive"):
                self.say("The %s cannot dive." % v.name, "dim")
                return False
        elif not self.swimming():
            self.say("You are not in deep water." if want else "You are not under water.", "dim")
            return False
        if want == p.diving:
            self.say("Under water already." if want else "At the top already.", "dim")
            return True
        p.diving = want
        if v is not None:
            v.dived = want
        if not want and v is None:
            p.air = self.breath()
        bubbles = Bits(self.vrng).burst(p.x + DIRS[p.facing][0] * 0.6, p.y + DIRS[p.facing][1] * 0.6, 0.1,
                                        [(200, 230, 255), (150, 200, 230)], n=12, speed=0.2, up=1.6, size=0.5).frames(4, 0.05)
        self.anim([FX(parts=bubbles[i]) for i in range(4)], 0.05)
        self.sfx("dive" if want else "surface", "footstep")
        if v is not None:
            self.say("The %s %s." % (v.name, "dives" if want else "surfaces"), "info")
        else:
            self.say("You dive. (%d beats of breath; F6: up)" % p.air if want else "You come up for air.", "info")
        self.end_beat()
        return True

    def air_beat(self):
        """A beat of the jetpack's fuel, and of breath under water."""
        p = self.player
        if p.jet_on:
            p.jet -= 1
            if p.jet == 5:
                self.say("The jetpack's gauge: 5 beats of fuel.", "alert")
            if p.jet <= 0:
                p.jet = 0
                self.jet_land(dry=True)
        if p.diving and p.vehicle is None:
            p.air -= 1
            if p.air == 5:
                self.say("Your lungs burn: 5 beats of air. (F6: up)", "alert")
            if p.air <= 0:
                p.air = 0
                self.hurt(int(self.cfg.get("drown_damage", 8)), "You are drowning.")
        elif p.air < self.breath() and not p.diving:
            p.air = self.breath()

    def take(self, it):
        p, pk = self.player, it.pickup
        name = it.spec.get("name", it.iid)
        if it.mine:                                      # stepped on a mine
            it.taken = True
            self.sfx("mine_click", "switch")
            self.say("Click. %s" % (pk["mine"].get("text") or "A mine!"), "hurt")
            self.blast(it.x, it.y, int(pk["mine"].get("blast", 40)), lead="The mine:")
            return
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
        if pk.get("fuel"):
            p.fuel += int(pk["fuel"])
        if pk.get("power") == "magboots":
            p.magboots = p.mag_on = True
        if pk.get("power") == "jetpack":
            p.jet += int(pk.get("beats", 30))
        elif pk.get("jet"):
            p.jet += int(pk["jet"])
        it.taken = True
        self.stats["items"] += 1
        self.say(pk.get("text") or "You pick up the %s." % name, "root" if pk.get("power") else "good")
        self.sfx(pk.get("sound") or ("special" if pk.get("weapon") or pk.get("power") else "pickup"))
        if pk.get("fuel") and p.vehicle is not None and "fuel" in p.vehicle.vehicle:
            self.refuel(p.vehicle)
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
        here = self.cell(p.x, p.y)
        usable = cell.kind in ("door", "switch", "exit", "locker", "panel") or cell.stairs or cell.mag \
            or cell.mag_ceiling or cell.crate
        if here.hatch and p.vehicle is None and not usable:
            return self.through_hatch(here)             # a hatch overhead (or underfoot): through it
        if cell.mag_ceiling:
            return self.up_wall(cell)
        if not self.within_reach(cell):
            return False
        if p.ceiling and not cell.solid:
            self.say("Nothing up here to use. (F3: magboots off - you drop)", "dim")
            return False
        if p.vehicle is not None and cell.kind not in ("exit", "switch"):   # in the cage, Enter climbs down
            if cell.kind == "door":
                self.say("The %s will not fit through the door: you climb down." % p.vehicle.name, "dim")
            return self.leave()
        here = self.cell(p.x, p.y)
        if here.lift and not (cell.kind in ("door", "exit") and not cell.pressed and cell.open < 1.0):
            return self.ride(here)
        if cell.stairs or cell.mag:
            return self.climb(cell)
        if cell.bulkhead:
            self.say("A bulkhead, down into the water. Dive (F6) to pass under it." if self.swimming()
                     else "A bulkhead, down into the water.", "dim")
            return False
        if cell.kind == "door" and cell.open < 1.0 and cell.open_while:
            self.say("It will not open: something holds it shut. A plate somewhere keeps it.", "dim")
            self.sfx("locked")
            return False
        if cell.crate and cell.supply is not None:
            return self.open_box(cell)
        if cell.crate:
            self.say("A crate. Walk into it to push it.", "dim")
            return False
        if cell.kind == "locker":
            return self.open_box(cell)
        if cell.kind == "field":
            return self.zapped(cell)
        if cell.kind == "door" and cell.open < 1.0:
            if cell.from_side is not None and (p.x - cell.x, p.y - cell.y) != DIRS[cell.from_side]:
                self.say("It does not open from this side.", "dim")
                self.sfx("locked")
                return False
            if cell.sealed and cell.open_for:
                self.say("Shut. A switch somewhere opens it - for a few beats.", "dim")
                self.sfx("locked")
                return False
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
        m = self.monster_at(x, y)
        if m is not None and m.spec.get("duel") and not m.dead:          # a challenger: a card duel
            got = self.duel(m.spec["duel"], m.spec)
            if got == "won":
                self.say(m.spec.get("duel_won") or "The %s folds its hand." % m.name, "good")
                self.kill(m)
            self.end_beat()
            return got is not None
        if cell.kind == "switch" and cell.duel and not cell.pressed:     # a terminal: hack it
            got = self.duel(cell.duel["duel"], cell.duel)
            if got != "won":
                self.end_beat()
                return got is not None
            self.say(cell.duel.get("duel_won") or "Access granted.", "good")
        if cell.kind == "switch":
            if cell.pressed:
                self.say("It is thrown already.", "dim")
                return False
            cell.pressed = True
            self.sfx("switch", "power")
            self.say("You throw the switch.", "good")
            self.anim([FX() for _ in range(3)], 0.06)
            self.event(cell.switch)
            self.end_beat()
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
        self.ways_change()                               # the map may change
        self.sfx("door")
        self.anim([FX(doors={(cell.x, cell.y): k}) for k in (0.2, 0.4, 0.6, 0.8, 0.95)], 0.04)
        cell.open = 1.0
        if cell.open_for:
            cell.closes_at = self.beat + cell.open_for
            self.say("It will shut again in %d beats." % cell.open_for, "alert")
        self.update_seen()

    def open_box(self, cell):
        """A locker or a supply crate opened: what is in it falls at his feet, and he takes what he can use."""
        p = self.player
        what = "locker" if cell.kind == "locker" else "crate"
        if cell.opened:
            self.say("An empty %s." % what, "dim")
            return False
        if cell.key and cell.key not in p.keys:
            self.say("Locked: this %s needs the %s key." % (what, cell.label), "hurt")
            self.sfx("locked")
            return False
        inside = cell.locker if what == "locker" else cell.supply
        cell.opened = True
        if what == "locker":
            cell.locker = ()
        else:
            cell.supply = ()
        self.sfx("locker" if what == "locker" else "crate_open", "open")
        self.anim([FX(shake=s) for s in (1, 0)], 0.04)
        found = [it for it in (self.add_item(i, p.x, p.y) for i in inside) if it is not None]
        if not found:
            self.say("You open the %s. Nothing in it." % what, "dim")
        else:
            self.say("You %s." % ("open the locker" if what == "locker" else "pry the crate open"), "good")
            for it in found:
                if not it.taken and not self.over:
                    self.take(it)
        if cell.on_open:
            self.event(cell.on_open)
        self.end_beat()
        return True

    def zapped(self, cell):
        """Walking into a force field: it throws him back."""
        self.sfx("zap", "hurt")
        self.anim([FX(whiten=k) for k in (0.35, 0.15, 0.0)], 0.04)
        if cell.zap:
            self.hurt(cell.zap, "The field throws you back.")
        else:
            self.say("The field will not let you through.", "dim")
        self.end_beat()
        return True

    def shut_doors(self):
        """Timed doors shut once their beats are up - not on whoever stands in them; the switch that opened one
        can open it again."""
        p = self.player
        for c in getattr(self, "timed_cells", ()):
            if c.closes_at is None or c.open < 1.0:
                continue
            left = c.closes_at - self.beat
            if left == 0:
                self.sfx("door_warn", "tick")
                self.say("A door starts to close!", "alert")
            if left >= 0:
                continue
            if (c.x, c.y) == (p.x, p.y) or self.monster_at(c.x, c.y) is not None or c.crate:
                continue                                 # something stands in it: it waits
            self.ways_change()                           # the map changes: the beat's ways first
            c.open, c.closes_at = 0.0, None
            if c.opens_on:                               # shut till the switch is thrown again
                c.sealed = True
                self.events.discard(c.opens_on)
                for row in self.grid:
                    for o in row:
                        if o.kind == "switch" and o.switch == c.opens_on:
                            o.pressed = False
            self.sfx("door")
            self.say("A door slams shut.", "alert")
            self.anim([FX(doors={(c.x, c.y): k}) for k in (0.7, 0.4, 0.1)], 0.04)
            self.update_seen()

    def open_panel(self, cell):
        self.ways_change()                               # the map may change
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

    def next_weapon(self):
        """The next weapon he has (with ammunition, if it needs any), in weapons.json's order, round to
        the first."""
        p = self.player
        order = [k for k in self.weapons if k in p.weapons]
        if p.weapon in order:
            i = order.index(p.weapon)
            order = order[i + 1:] + order[:i]
        for k in order:
            w = self.weapons[k]
            if not w.get("ammo") or p.ammo.get(w["ammo"], 0) > 0:
                return self.switch(k)
        self.say("Nothing else to change to.", "dim")
        return True

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
        w = self.weapons.get(p.weapon) or WEAPONS["1"]
        if p.vehicle is not None:
            gun = p.vehicle.vehicle.get("gun")
            if not isinstance(gun, dict):
                return self.claw()
            w = dict(gun, ammo=None)                     # the machine's own guns: they never run dry
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
                           and abs(self.rel(m.x, m.y)[0]) < 0.5 and not m.vehicle and not m.ball]   # one straight ahead
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
        stopped = 0
        cover = not melee and self.covered(p.x, p.y, target.x, target.y)
        lo, hi = w.get("damage", [5, 10])
        if melee:
            if rng.random() < float(w.get("accuracy", 0.85)):
                hits[target] = rng.randint(lo, hi) * (3 if w.get("berserk") else 1)
        else:
            for _ in range(int(w.get("burst", 1))):
                for _ in range(int(w.get("pellets", 1))):
                    acc = (PELLET if w.get("pellets", 1) > 1 else ACCURACY)[min(d, 8)]
                    if rng.random() < acc:
                        if cover and rng.random() < COVER:
                            stopped += 1                 # into the wall or crate it stands behind
                            continue
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
        elif stopped:
            self.say("Your shot hits the cover in front of %s." % target.tag, "dim")
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
            ball = self.monster_at(x, y)
            if ball is not None and ball.ball:
                self.sfx("clack", "hit_wall")
                self.say("Your shot pings off the %s." % ball.name, "dim")
                return
            if cell.solid and cell.clear:
                continue                                 # through the bars, through the field
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
        hits = [(m, d) for m, d in hits if not m.dead and not m.gone and not m.ball]     # a ball takes no harm
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
        built = [m for m in dying if m.model and m.model in self.models]   # 3D models break into shards instead
        burst = [m for m in burst if m not in built]
        gibs = Bits(self.vrng)
        for m in burst:                                      # overkill, or a blast: it comes apart
            pic = self.sprites.get(m.sprite)
            cols = [c for row in (pic.rows if pic else []) for c in row if c is not None][::3] or [(150, 20, 20)]
            gibs.burst(m.x, m.y, 0.6 * m.size, cols + [(150, 10, 10), (110, 0, 0)], n=22, speed=1.8, up=2.0, size=1.2)
        flying = gibs.frames(4, 0.05) if burst else [()] * 4
        steps = 8 if built else 4
        for i in range(steps if dying else 0):
            k = (i + 1) / float(steps)
            frames.append(FX(dissolve={m.id: (k if m in built else 1.0 if m in burst else min(1.0, k * steps / 4.0))
                                       for m in dying},
                             tint={m.id: (150, 8, 8) for m in dying if m not in built},
                             texts=[(m, "-%d" % d, "hit", 3 + i) for m, d in hits],
                             parts=flying[i] if i < len(flying) else ()))
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
            if m.on_death and not self.over:
                self.event(m.on_death)
            return
        if not m.spec.get("boss") and not m.spec.get("falls"):
            self.stats["kills"] += 1
        if m is self.boss and self.marks:                # its schedule dies with it: no more fire marked
            self.marks = {}
            self.marks_version += 1
        gore = self.sprites.get(m.spec.get("remains", None if m.model in self.models else "gore"))
        if gore is not None:
            self.decals.append((m.x, m.y, gore))
        if m.spec.get("burst_fire"):                   # its tanks burst: fire all round
            beats = int(m.spec["burst_fire"])
            for dx, dy in ((0, 0),) + DIRS:
                self.ignite(m.x + dx, m.y + dy, beats)
            self.say("Its tanks burst into flame.", "alert")
        self.say((m.spec.get("death") or "%s dies.") % m.tag, "good")
        self.sfx((m.spec.get("sounds") or {}).get("death") or "enemy_down")
        if m.on_death:
            self.event(m.on_death)
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
        for it in [it for it in self.items if it.mine and not it.taken and max(abs(it.x - x), abs(it.y - y)) <= 1]:
            if not it.taken and not self.over:           # and the mines
                it.taken = True
                self.blast(it.x, it.y, int(it.pickup["mine"].get("blast", 40)), lead="A mine goes up:")

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
        if c.kind not in WALLS or c.crate or c is VOID:
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
        self.ways_change()                               # the map may change
        sign = lambda v: (v > 0) - (v < 0)                    # noqa: E731
        moved, slid = [], {}
        for c in [self.cell(x, y) for y in range(y0 - 1, y0 + 2) for x in range(x0 - 1, x0 + 2)]:
            if not c.crate or c.heavy:
                continue
            dx, dy = sign(c.x - x0), sign(c.y - y0)
            t = self.cell(c.x + dx, c.y + dy)
            if (dx or dy) and not t.solid and not self.monster_at(t.x, t.y) and (t.x, t.y) != (self.player.x, self.player.y):
                load = (c.supply, c.opened)
                c.crate = c.opened = False
                c.supply = None
                if t.toxic:
                    t.toxic, t.sunk = False, True
                    self.marks_version += 1
                else:
                    t.crate = True
                    t.supply, t.opened = load
                    slid[(t.x, t.y)] = (c.x, c.y)
        for m in self.monsters:
            if m.ball and not m.gone and max(abs(m.x - x0), abs(m.y - y0)) == 1 and (m.x == x0 or m.y == y0) \
                    and self.ball_room(m.x + sign(m.x - x0), m.y + sign(m.y - y0)):
                self.set_rolling(m, sign(m.x - x0), sign(m.y - y0))      # it rolls away: next beat
                self.say("The blast sets %s rolling." % m.tag, "dim")
                continue
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
        self.ways_change()                               # the map may change
        if name in self.events:
            return
        self.events.add(name)
        opened = closed = timed = 0
        for row in self.grid:
            for c in row:
                if c.closes_on == name and c.kind == "door" and c.open >= 1.0:
                    c.open, c.sealed = 0.0, True
                    closed += 1
                if c.closes_on == name and c.field and c.kind == "floor" and self.monster_at(c.x, c.y) is None \
                        and (c.x, c.y) != (self.player.x, self.player.y):
                    c.kind = "field"                     # the field comes back on
                    closed += 1
                if c.mag_off_on == name and c.ceiling_mag:
                    if c.mag_delay:
                        self.cuts.append((self.beat + c.mag_delay, c.x, c.y))
                    else:
                        self.cut_plating(c)
                if c.opens_on == name:
                    if c.kind == "door":
                        c.sealed = False
                        c.open = 1.0
                        if c.open_for:
                            c.closes_at = self.beat + c.open_for
                            timed = c.open_for
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
        if timed:
            self.say("It will shut again in %d beats." % timed, "alert")
        for m in self.monsters:
            if m.wake_on == name and not m.dead:
                if m.ball and m.roll_dir is not None:     # a ball let go: it rolls after a beat's rumble
                    self.set_rolling(m, *DIRS[m.roll_dir], cells=999)
                    m.roll_wait = int(m.spec.get("delay", 1))
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
        self.__dict__["_spreading"] = []                 # the last beat's ways are done with
        atm = getattr(self, "atmosphere", None)
        if atm is not None and atm.flash(self.beat):     # lightning: the thunder after it
            self.sfx("thunder", "boom")
        if self.cuts:                                    # plated ceilings whose power goes now
            due = [(x, y) for b, x, y in self.cuts if b <= self.beat]
            self.cuts = [(b, x, y) for b, x, y in self.cuts if b > self.beat]
            for x, y in due:
                self.cut_plating(self.cell(x, y))
            if self.over:
                return
        p = self.player
        self.shed()
        if self.world is not None:
            self.world.follow()                          # wake what is near, put what he left to sleep
        self.fly()
        if self.over:
            return
        heard = self.wake_up()
        ai.beat(self, heard)                             # squads share what they know, give out roles
        self.moved, self.queue = [], []
        for m in list(self.monsters):
            if not m.dead and not m.gone and m.awake and not m.barrel:
                self.act(m)
        for m, x0, y0 in self.moved:                    # it faces the way it went
            if (m.x, m.y) != (x0, y0):
                m.heading = math.atan2(m.y - y0, m.x - x0)
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
        self.roll()
        if self.over:
            return
        if self.boss is not None and self.boss.awake and not self.boss.dead and not self.boss.gone:
            self.boss_beat()
        self.convey()
        if self.over:
            return
        self.fuses()
        if self.over:
            return
        self.plates()
        self.shut_doors()
        self.burn()
        if self.over:
            return
        burning = [(m, int(self.cfg.get("toxic_damage", 5))) for m in self.monsters if not m.dead and not m.gone
                   and not m.float and not m.spec.get("boss") and self.cell(m.x, m.y).toxic
                   and not (m.vehicle and m.vehicle.get("wades", True))]
        if burning and not self.over:
            self.damage(burning, lead="The acid:")
        cell = self.cell(p.x, p.y)
        if cell.toxic and not self.over and not p.jet_on and not p.ceiling:
            self.acid()
        self.air_beat()
        if self.over:
            return
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
        self.fuel_beat()
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
        if (p.x, p.y) in self.fires and not p.jet_on and not p.ceiling:
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
                if p.mag_on and p.vehicle is None and not self.airborne():
                    self.say("Your magboots hold you to the belt.", "dim")
                elif not self.airborne() and self.room(tx, ty):
                    cam = ((p.x, p.y), (tx, ty))
                    p.x, p.y = tx, ty
            elif c.crate:
                if self.room(tx, ty, crate=True):
                    self.ways_change()                   # the map changes: the beat's ways first
                    heavy, load = c.heavy, (c.supply, c.opened)
                    c.crate = c.heavy = c.opened = False
                    c.supply = None
                    t = self.cell(tx, ty)
                    if t.toxic:
                        t.toxic, t.sunk = False, True
                        self.marks_version += 1
                    else:
                        t.crate, t.heavy = True, heavy
                        t.supply, t.opened = load
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
            for m, _x, _y in moves:                       # a ball carried into acid sinks
                if m.ball and self.cell(m.x, m.y).toxic:
                    self.sink(m)
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
            if (near and self.sees(m.x, m.y, p.x, p.y)) or (m.x, m.y) in heard:
                self.wake(m)
        return heard

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
        if not self.step_ok(m.x, m.y, x, y, getattr(m, "float", 0)):
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
        if m.spec.get("duel") and not m.spec.get("fights"):   # a challenger waits to be dealt with
            return
        a = m.attack
        kind = a.get("kind", "melee")
        if m.spec.get("falls"):                          # it falls, the world's way down, and stops for nothing
            self.fall_step(m)
            return
        if kind in ("cron", "none"):                     # Cron keeps its own time; "none" only stands there
            return
        m.cool = max(0, m.cool - 1)
        if m.stun:                                      # still reeling: no aim, no step
            m.stun -= 1
            m.intent = None
            m.spin, m.spun = 0, False
            return
        if m.grudge is not None and (m.grudge.dead or m.grudge.gone):
            m.grudge = None
        if ai.brain.has(self, m):                        # a brain: it weighs what to do (engine/ai)
            return ai.brain.act(self, m)
        foe = m.grudge
        tx, ty = (foe.x, foe.y) if foe else (p.x, p.y)
        d = max(abs(m.x - tx), abs(m.y - ty))
        adjacent = abs(m.x - tx) + abs(m.y - ty) == 1
        los = self.sees(m.x, m.y, tx, ty)
        reach = int(a.get("range", 8))
        fl = bool(m.float) and self.land is not None             # in open land, a floater takes its own way
        lim = 24 if self.land is not None else 40                # open land: the hunt goes this far, no further
        if not hasattr(self, "_field") or self._field[0] != (tx, ty, self.beat):
            self._field = ((tx, ty, self.beat), self.ways(tx, ty, limit=lim), None)
        if fl and self._field[2] is None:
            self._field = (self._field[0], self._field[1], self.ways(tx, ty, limit=lim, floats=True))
        field = self._field[2] if fl else self._field[1]
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
        p = self.player
        sure = acc[min(d, len(acc) - 1)] + self.crossfire(m)
        cover = self.covered(m.x, m.y, p.x, p.y)
        total = stopped = 0
        for _ in range(pellets):
            if self.rng.random() < sure:
                if cover and self.rng.random() < COVER:
                    stopped += 1
                    continue
                total += self.rng.randint(lo, hi)
        if total:
            self.hurt(total, "%s shoots you." % m.tag, by=m)
        elif stopped:
            self.sfx("hit_wall")
            self.say("%s's shot hits your cover." % m.tag, "dim")
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

    def lob_at(self, m, x, y):
        """A monster's grenade, thrown at (x, y) (``"grenades"`` in monsters.json): it lands there, its fuse
        burning ``fuse`` beats (3: time to get out of it), and goes off for ``blast``."""
        if m.dead or m.gone or m.grenades_left <= 0:
            return
        g = m.spec.get("grenades") or {}
        m.grenades_left -= 1
        m.lobbed = self.beat
        p = self.player
        way = bresenham(m.x, m.y, x, y)
        n = max(3, 3 * (len(way) - 1))
        self.sfx((m.spec.get("sounds") or {}).get("throw") or "throw")
        self.anim([FX(missiles=[(gx, gy, 0.6 * (1 - k) + 1.1 * k * (1 - k), "grenade", None)])
                   for gx, gy, k in [self.along(way, i / float(n)) + (i / float(n),) for i in range(1, n + 1)]], 0.035)
        self.grenades.append(Grenade(x, y, int(g.get("fuse", 3)), int(g.get("blast", 30))))
        dd = max(abs(x - p.x), abs(y - p.y))
        where = "at your feet" if dd == 0 else "next to you" if dd == 1 else "%d cells away" % dd
        self.say("%s throws a grenade - it lands %s!" % (m.tag if m.seen else "Someone", where), "alert")
        self.sfx("bounce", "hit_wall")
        self.interrupt = self.interrupt or "a grenade"

    def lay_mine(self, m):
        """A monster lays one of its mines (``"mines"`` in monsters.json) where it stands."""
        spec = m.spec.get("mines") or {}
        it = self.add_item(spec.get("item", "mine"), m.x, m.y)
        if it is None or not it.mine:
            if it is not None:
                self.items.remove(it)
            m.mines_left = 0
            return None
        m.mines_left -= 1
        if m.seen:
            self.say("%s kneels and sets something on the floor." % m.tag, "dim")
        return it

    def bite(self, m, foe, dmg):
        if m.dead or m.gone:
            return
        lo, hi = dmg
        if foe is not None and not foe.dead:
            if abs(foe.x - m.x) + abs(foe.y - m.y) == 1:
                self.damage([(foe, self.rng.randint(lo, hi))], lead="%s tears into %s:" % (m.tag, foe.tag), source=m)
            return
        p = self.player
        if not self.reaches_up(m):                       # he is up on the ceiling of a tall room
            return
        if abs(p.x - m.x) + abs(p.y - m.y) == 1:
            self.sfx((m.spec.get("sounds") or {}).get("attack") or "hit")
            pack = 0                                     # the others of its squad at him too: worse together
            if m.squad is not None:
                pack = sum(1 for o in m.squad.members if o is not m and not o.dead and not o.gone
                           and abs(p.x - o.x) + abs(p.y - o.y) == 1)
            dmg = self.rng.randint(lo, hi) * (4 + min(3, pack)) // 4      # a quarter more for each other one
            text = (m.spec.get("bite") or "%s bites you.") % m.tag
            self.hurt(dmg, text if pack < 2 else text[:-1] + " - the pack is all over you.", by=m)

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
                if job.get("in_arena") and (p.x, p.y) not in getattr(self, "arena", ()):
                    continue                             # it forks only while he is in its hall
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
            stat = {"aim": "A", "windup": "W", "charge": "C"}.get(m.intent) or (ai.brain.stat(m) if m.awake else None) \
                or ("R" if m.awake else "S")
            out.append(("%5d  %-4s %4d  %4d  %s (%s)" % (100 + m.id, stat, max(0, m.hp), self.dist(m), m.name, m.tag),
                        STATE_ROLE.get(m.intent, "text")))
        if len(out) == 1:
            out.append(("(nothing in sight)", "dim"))
        out += [("", "text"), ("STAT  A aiming  W winding up  C charging  R running  S sleeping", "dim"),
                ("      D in cover  F flanking  K keeping away  H holding", "dim"),
                ("      B falling back  ? searching", "dim")]
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
        mind = ai.brain.describe(spec.get("brain"))
        if mind:
            lines.append((mind, "dim"))
        lines.append(("", "text"))
        return lines + [(t, "text") for t in spec.get("man") or ["No description."]]

    def snapshot_state(self):
        return {"x": self.player.x, "y": self.player.y}


# --------------------------------------------------------------------------- #
# consoles: how a level is shown and asked
# --------------------------------------------------------------------------- #
class FrameConsole:
    """Frame mode: the first-person picture, redrawn in place; keys act at once."""

    def __init__(self, term, style="pixel", keys=True, keymap=None, animate=True, speed=1.0, detail="auto",
                 realtime=None, touch=False, render=None, render_game=None):
        from .frame import Screen
        from .keys import KeyReader
        self.screen = Screen(term, KeyReader() if keys else None, keymap or KEYMAP, animate, speed)
        self.touch = bool(touch)                         # taps and swipes act (where the terminal reports them)
        if self.touch:
            self.screen.pointer = self.touch_key
        self.swiped = None
        self.realtime = realtime          # seconds a beat lasts when no key is pressed (0: off; None: the level's)
        self.keymap = self.screen.keymap
        self.keys = self.screen.keys
        self.style = style
        self.detail = detail if detail in DETAILS else "auto"   # how fine the floor is: see View
        self.render, self.render_game = render, render_game      # how rooms are drawn: the player's, the game's
        self.view = None
        self.views = {}
        self.size = None
        self.phase = 0
        self.status = ""

    def start(self):
        self.screen.start()
        if self.touch and self.screen.keys is not None:      # (typed lines only: no reports in the way)
            self.screen.write("\x1b[?1000h\x1b[?1006h")     # taps as clicks, swipes as the wheel; SGR numbers
            self.mouse_on = True

    mouse_on = False

    def stop(self):
        if self.mouse_on and self.screen.started:
            self.screen.write("\x1b[?1000l\x1b[?1006l")
            self.mouse_on = False
        self.screen.stop()

    def said(self, text, role):
        pass

    def touch_key(self, name):
        """A tap or a swipe (a mouse report: engine/keys.py) as the key it stands for. The picture in
        thirds: left and right turn, their bottom corners strafe; the middle's top steps forward, its
        centre fires, its bottom uses. A swipe up or down (the wheel, in Termux) steps forward or back,
        a step per SWIPE_GAP however long the swipe. The status line: the next weapon; under the
        picture: the map."""
        try:
            kind, b, x, y = name.split(":")
            b, x, y = int(b), int(x), int(y)
        except ValueError:
            return None
        if kind != "mouse":
            return None                                   # a release: the press has acted
        if b & 64:
            now = self.screen.now()
            if self.swiped is not None and 0 <= now - self.swiped < SWIPE_GAP:
                return None
            self.swiped = now
            # Termux: a finger moving up scrolls down (65); moving down, up (64)
            return {0: "down", 1: "up", 2: "left", 3: "right"}[b & 3]
        if b & 3:
            return None                                   # only the first button: a tap
        W, H, VR = self.layout()
        if y == 0:
            return "]"
        if y > VR:
            return "tab"
        col = 0 if x < W // 3 else 2 if x >= W - W // 3 else 1
        row = min(2, (y - 1) * 3 // VR)
        return (("left", "up", "right"), ("left", "space", "right"), (",", "enter", "."))[row][col]

    def layout(self):
        W, H = self.screen.size()
        VR = max(6, min(H - 7, 34))
        if (W, VR) != self.size:
            self.size = (W, VR)
            self.view = View(W, VR, self.style, self.detail, self.render, self.render_game)
            self.views = {}
        return W, H, VR

    def view_for(self, lv, style=None):
        """The view to draw with: the game's style, or another for a moment (a teleport), or the goggles' dots."""
        style = style or ("dots" if lv.player.nightvision else None)
        if not style or style == self.style:
            return self.view
        if style not in self.views:
            self.views[style] = View(self.size[0], self.size[1], style, self.detail, self.render, self.render_game)
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
                     + ([("fuel %d" % p.vehicle.fuel, "alert" if p.vehicle.fuel <= 5 else "ammo"), bar]
                        if "fuel" in p.vehicle.vehicle else [])
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
        p = lv.player
        if p.magboots:
            segs.append(("  mag: ceiling" if p.ceiling else "  mag" if p.mag_on else "  mag off",
                         "info" if p.mag_on else "dim"))
        if p.jet or p.jet_on:
            segs.append(("  jet%s: %d" % (" up" if p.jet_on else "", p.jet), "alert" if p.jet_on and p.jet <= 5 else "ammo"))
        if p.diving and p.vehicle is None:
            segs.append(("  air: %d" % p.air, "hurt" if p.air <= 5 else "info"))
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
        land = lv.land
        beacons = {(int(m["at"][0]), int(m["at"][1])) for m in land.marks} if land is not None else set()

        def colour(x, y):
            if (x, y) in beacons:                        # a landmark is seen from far off: on the map from the start
                return (230, 90, 70)
            if (x, y) not in lv.seen_cells:
                return dark
            if (x, y) == (p.x, p.y):
                return (120, 255, 160)
            m = lv.monster_at(x, y)
            if m is not None and m.seen:
                return (240, 70, 60) if not m.barrel else (90, 170, 90)
            c = lv.cell(x, y)
            if any(not it.taken and (it.x, it.y) == (x, y) and not it.mine for it in lv.items):
                return (240, 210, 90)
            if any(not it.taken and (it.x, it.y) == (x, y) and it.mine for it in lv.items) \
                    and max(abs(x - p.x), abs(y - p.y)) <= fp.MINE_SEEN:
                return (255, 40, 30)
            if c.kind == "door":
                return fp.KEY_COLOURS.get(c.key, (150, 150, 170) if c.gate else (170, 140, 90)) if c.open < 1 \
                    else (90, 80, 60)
            if c.kind == "field":
                return (90, 200, 255)
            if c.kind == "locker":
                return (120, 124, 136) if c.opened else fp.KEY_COLOURS.get(c.key, (176, 150, 210))
            if c.kind == "exit":
                return (90, 230, 120)
            if c.kind == "switch":
                return (230, 190, 70) if not c.pressed else (90, 230, 120)
            if c.crate:
                return (200, 160, 60) if c.supply else (140, 104, 64)
            if c.kind in ("wall", "panel"):
                return (120, 124, 136)
            if land is not None and (x, y) not in land.stamp:   # open land: its own colours, darker
                rgb = land.at_cell(x, y)[1]
                return (int(rgb[0] * 0.62), int(rgb[1] * 0.62), int(rgb[2] * 0.62))
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
        elif self.realtime_now:
            text = "REAL TIME %.1fs  %s" % (self.realtime_now, text)
        return sc.paint.text([(text, "dim")], self.size[0] if self.size else 80, sc.glyphs["ell"])

    realtime_now = 0

    def draw(self, lv, fx=None, prompt="> ", cells=None):
        self.realtime_now = self.beat(lv) if self.keys is not None else 0
        self.screen.frame(self.rows(lv, fx, cells), prompt=prompt, status=self.status, footer=self.hint())

    def read(self, lv):
        self.phase += 1
        self.status = ""
        beat = self.beat(lv)
        if beat and self.keys is not None:
            return self.screen.read(lambda: self.draw(lv), deadline=self.screen.now() + beat, idle=IDLE)
        return self.screen.read(lambda: self.draw(lv))

    def beat(self, lv):
        """Seconds a beat lasts in real time (0: the level waits for the player)."""
        return beat_of(lv, self.realtime)

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
        view = self.view_for(lv)
        if view.meshed(lv) and getattr(lv, "land", None) is None and abs(direction) == 1:
            # the mesh view turns: the picture at angles between the old facing and the new
            face = lv.player.facing
            frames = [view.render(lv, FX(yaw=(face - direction * (1 - k)) * math.pi / 2), self.phase)
                      for k in (0.25, 0.5, 0.75)]
        else:
            new = view.render(lv, FX(), self.phase)
            side = -direction if getattr(lv.player, "ceiling", False) else direction    # upside down: the screen's way
            frames = [slide(old, new, k, side) for k in (0.3, 0.6, 0.85)]
        self.screen.play(frames, lambda cells: self.draw(lv, prompt=None, cells=cells), 0.03)

    def ride(self, lv, old, new, down):
        """A lift's ride, in dots: the view slides away, the shaft goes by, the other end comes in."""
        frames = [vslide(old, new, k, down) for k in (0.08, 0.18, 0.3, 0.42, 0.52, 0.62, 0.72, 0.82, 0.92, 1.0)]
        self.screen.play(frames, lambda cells: self.draw(lv, prompt=None, cells=cells), 0.11)

    def rolled(self, lv, angles):
        """The mesh view at each of ``angles`` (degrees) turned about its middle (View.rolled); None in the
        classic view, whose picture is turned as it is."""
        view = self.view_for(lv, "pixel")
        if not view.meshed(lv) or getattr(lv, "land", None) is not None:
            return None
        return [view.rolled(lv, a, self.phase) for a in angles]

    def tilt(self, lv, old, new, up, olds=None, news=None, tip=TIP, back=TIP_BACK):
        """Magboots up (or down) a wall: the world tips on its side, goes by, and tips back at the other end.
        ``olds``/``news``: the mesh view at ``tip``'s and ``back``'s angles (rolled), else the picture is turned
        through them. (On to the ceiling: back from -90 to 0, the picture upside down already.)"""
        from .firstperson import tilt
        if olds and news:
            frames = list(olds) + [vslide(olds[-1], news[0], k, not up) for k in (0.2, 0.45, 0.7, 0.9, 1.0)]
            frames += list(news[1:]) + [new]
            self.screen.play(frames, lambda cells: self.draw(lv, prompt=None, cells=cells), 0.06)
            return
        frames = [tilt(old, a) for a in tip]
        frames += [vslide(tilt(old, tip[-1]), tilt(new, back[0]), k, not up) for k in (0.2, 0.45, 0.7, 0.9, 1.0)]
        frames += [tilt(new, a) for a in tuple(back[1:]) + (0,)]
        self.screen.play(frames, lambda cells: self.draw(lv, prompt=None, cells=cells), 0.06)

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

    def tilt(self, lv, old, new, up, olds=None, news=None, tip=TIP, back=TIP_BACK):
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
        if lv.world is not None:                         # no end to it: the part round the player
            ys, xs = range(p.y - 20, p.y + 21), range(p.x - 38, p.x + 39)
        else:
            ys, xs = range(lv.h), range(lv.w)
        for y in ys:
            row = []
            for x in xs:
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
            return "/" if c.open >= 1 else (c.key or "+").upper() if c.key else "H" if c.gate else "+"
        if c.kind == "field":
            return "%"
        if c.kind == "locker":
            return "#" if c.opened else "L"
        if c.kind == "exit":
            return "E"
        if c.kind == "switch":
            return "|" if c.pressed else "\\"
        if c.crate:
            return "$" if c.supply else "&"
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
            if "fuel" in p.vehicle.vehicle:
                ammo += ", fuel %d" % p.vehicle.fuel
        elif p.fuel:
            ammo += " | fuel cans %d" % p.fuel
        power = "".join(" | %s %d" % (n, v) for n, v in (("root", p.sudo), ("boots", p.boots),
                                                          ("goggles" if p.goggles_on else "goggles off", p.goggles),
                                                          ("jet up" if p.jet_on else "jet", p.jet),
                                                          ("air", p.air if p.diving and p.vehicle is None else 0)) if v)
        if p.magboots:
            power += " | mag %s" % ("on" if p.mag_on else "off")
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
class Host:
    """The game round a level, as the level sees it: saves (the world as it was when the level began, and
    the level's journal), loads, card duels, and finds the scene that plays a level."""

    def __init__(self, game, auto_duels=False):
        self.game = game
        self.auto_duels = auto_duels

    def duel(self, lv, cid, spec):
        """Fight a card duel off the level's screen (the screen is given back after). ``(result, health
        left)``, or None if the game has no such character."""
        from . import cards
        g = self.game
        if cid not in g.world.characters:
            lv.say("Nobody answers.", "dim")
            return None
        con = lv.console
        frame = isinstance(con, FrameConsole)
        if frame:
            con.stop()
            if getattr(g.term, "ansi", False):
                g.term.out.write("\x1b[H\x1b[2J")            # the duel on a clear screen
                g.term.out.flush()
        try:
            return cards.fight_duel(g, cid, lv.player.hp, 100, auto=self.auto_duels or not g.term.is_tty,
                                    can_flee=spec.get("flee", True))
        finally:
            if frame:
                con.start()

    def path(self, slot):
        from .world import slot_path
        return slot_path(self.game.saves(), slot or self.game.slot)

    def scene_of(self, lid):
        return next((sid for sid, sc in self.game.world.scenes.items() if sc.get("level") == lid), None)

    def save(self, lv, slot, how="save"):
        """``how``: "save" (typed; counted when the game limits them), "start" or "checkpoint" (free)."""
        from .world import write_save
        if how == "save" and lv.saves_left is not None and not lv.dev and lv.saves_left <= 0:
            lv.say("No saves left in this level. (A checkpoint still saves.)", "hurt")
            return False
        if how == "save" and lv.saves_left is not None and not lv.dev:
            lv.saves_left -= 1
        blob = self.game.world.to_save()
        blob["level"] = lv.save_block()
        try:
            write_save(self.path(slot), blob)
        except (OSError, TypeError, ValueError) as e:
            lv.say("Could not save: %s" % e, "hurt")
            return False
        if how == "start":
            return True
        lv.sfx("save")
        left = ("  (%d left in this level)" % lv.saves_left) if lv.saves_left is not None and not lv.dev else ""
        lv.say(("Checkpoint: saved." if how == "checkpoint" else "Saved%s." % (" as '%s'" % slot if slot else ""))
               + (left if how == "save" else ""), "good")
        return True

    def list(self, lv):
        from .world import list_saves
        found = list_saves(self.game.saves())
        lv.say("Saved games: " + (", ".join(s[0] for s in found) if found else "none"), "dim")
        return True

    def load(self, lv, slot):
        from .world import read_save
        path = self.path(slot)
        if not os.path.isfile(path):
            lv.say("There is no saved game%s." % (" called '%s'" % slot if slot else ""), "hurt")
            return False
        try:
            blob = read_save(path)
        except (OSError, ValueError) as e:
            lv.say("Could not read that save: %s" % e, "hurt")
            return False
        if blob.get("game") != self.game.data.id:
            lv.say("That save belongs to another game.", "hurt")
            return False
        if blob.pop("_backup", False):
            lv.say("That save was damaged: loading the one made before it.", "alert")
        lv.loaded, lv.over = blob, "load"
        return True


def resume(data, block, audio=None):
    """A level as a save left it. Returns ``(level, note)``; a note says when it did not come back exactly.

    The level is built as it began and its snapshot put back on it; the snapshot's digest must come out
    the same. When the level has changed since the save (its data are not what they were) or the save
    has no snapshot (an older one), its lines are played back instead; when nothing fits, the level
    starts again from where it began."""
    from . import snapshot
    depth = block.get("depth") if isinstance(block.get("depth"), int) else 0

    def fresh():
        return Level(data, block["id"], seed=block.get("seed"), player=block.get("start"), depth=depth)

    def finish(lv, note):
        if isinstance(block.get("saves_left"), int):
            lv.saves_left = block["saves_left"]
        lv.audio = audio
        return lv, note

    lv = fresh()
    lines = block.get("lines") or []
    same = not block.get("fingerprint") or block["fingerprint"] == lv.fingerprint()
    snap = block.get("snapshot")
    whole = not block.get("lines_from")                  # the lines go back to the level's beginning

    def from_snapshot(lv):
        snapshot.restore(lv, snapshot.unpack(snap))
        if block.get("digest") and lv.state_hash() != block["digest"]:
            raise snapshot.SnapshotError("it did not come back the same")
        lv.journal = [list(e) if isinstance(e, list) else e for e in lines]
        return lv
    if snap and (same or not whole):
        try:
            return finish(from_snapshot(lv), None if same else "The level has changed since this save was made.")
        except (snapshot.SnapshotError, KeyError, IndexError, TypeError, AttributeError, ValueError):
            lv = fresh()
    note = None if same else "The level has changed since this save was made."
    if not whole or not lv.replay(lines):
        lv = fresh()
        note = "That save no longer plays back on this level: it starts again from the beginning."
    return finish(lv, note)


def _termux():
    from .term import is_termux
    return is_termux()


def play_scene(game, scene, resume_from=None):
    """Run the level of a scene for a CLIo game, then go on with the story. ``resume_from``: a save's
    level block, to go on from. Loading a save or jumping to a level (--dev) plays on here."""
    w = game.world
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
                               speed=max(0.0, float(term.speed or 1.0)), realtime=settings.get("realtime"),
                               touch=settings.get("touch", _termux()), render=settings.get("render"),
                               render_game=cfg.get("render"))
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
    dev = bool(settings.get("dev"))
    host = Host(game)
    while True:
        lid = scene.get("level")
        note = None
        if resume_from is not None and resume_from.get("id") == lid:
            lv, note = resume(game.data, resume_from, game.audio)
        else:
            lv = Level(game.data, lid, audio=game.audio, seed=game.seed, player=w.vars.get("_fp_player"),
                       depth=level_depth(game.data, lid, w.vars))
        lv.host, lv.dev = host, dev
        if resume_from is None and cfg.get("autosave"):
            host.save(lv, None, how="start")             # the level's beginning: what dying goes back to
        if resume_from is not None:
            lv.opening = [("Loaded%s." % (" - beat %d" % lv.beat if lv.beat else ""), "good")]
            if note:
                lv.opening.append((note, "alert"))
        resume_from = None
        outcome = lv.run(console)
        if outcome == "load":
            blob = lv.loaded
            try:
                w.load_save(blob)
            except (KeyError, ValueError) as e:
                lv.say("Could not load that save: %s" % e, "hurt")
                resume_from = lv.save_block()           # back where we were
                continue
            game.over, game.started = None, True
            scene = w.scene
            if not scene.get("level"):
                game.resume_music()
                game.describe_scene(full=True)
                return "loaded"
            resume_from = blob.get("level") or None
            continue
        if outcome == "warp":
            w.vars["_fp_player"] = lv.player.keep()
            sid = host.scene_of(lv.warp)
            w.scene_id = sid
            if sid not in w.visited:
                w.visited.append(sid)
            scene = w.scene
            continue
        break
    w.vars["_fp_player"] = lv.player.keep()
    stats = dict(lv.stats, beats=lv.beat, par=lv.par, secrets_total=lv.total_secrets, kills_total=lv.total_kills,
                 items_total=lv.total_items)
    w.vars.setdefault("levels", {})[lv.id] = stats
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


def beat_of(lv, setting=None):
    """Seconds a beat of ``lv`` lasts in real time: ``setting`` (the command line's ``--realtime``), else the
    level's ``"realtime"``, else game.json's ``first_person`` ``"realtime"``; 0 or false: not in real time."""
    for v in (setting, lv.spec.get("realtime"), lv.cfg.get("realtime")):
        if v is None:
            continue
        if v is False:
            return 0.0
        try:
            return max(0.0, float(v))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def level_depth(data, lid, variables):
    """How deep a generated level is this time: the game variable its ``"depth"`` names (0 if none)."""
    spec = (data.levels or {}).get(lid) or {}
    made = spec.get("generate") if isinstance(spec.get("generate"), dict) else spec.get("world")
    name = made.get("depth") if isinstance(made, dict) else None
    v = variables.get(name, 0) if isinstance(name, str) else 0
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def made_problems(lv, data, sprites):
    """What is wrong with a level made as it goes (``"world"``) or from a seed (``"generate"``)."""
    out = []
    if lv.get("world") is not None and lv.get("generate") is not None:
        out.append("a level is made as it goes (\"world\") or from a seed (\"generate\"), not both")
    if lv.get("map") is not None:
        out.append("a %s level makes its own map: leave \"map\" out" % ("world" if lv.get("world") is not None
                                                                          else "generated"))
    if lv.get("generate") is not None:
        from . import levelgen
        out += levelgen.problems(lv["generate"], data)
        return out
    from . import chunks as world_mod
    wspec = lv["world"]
    out += world_mod.problems(wspec, data)
    if not isinstance(wspec, dict):
        return out
    if wspec.get("kind", "land") == "land":
        from . import land as land_mod
        land = dict(lv.get("land") or {})
        land.pop("size", None)
        out += land_mod.problems(land, sprites, getattr(data, "models", None) or {})
        mons = data.monsters or {}
        ends = False
        for s in wspec.get("sites") or []:
            if not isinstance(s, dict) or not isinstance(s.get("at"), list):
                continue
            legend = dict(LEGEND)
            legend.update(lv.get("legend") or {})
            legend.update(s.get("legend") or {})
            for ch in set("".join(str(r) for r in s.get("map") or [])):
                sp = legend.get(ch)
                if not isinstance(sp, dict):
                    sp = {"monster": sp} if sp in mons else {}
                veh = (mons.get(sp.get("monster")) or {}).get("vehicle") if sp.get("monster") else None
                if sp.get("exit") or (isinstance(veh, dict) and veh.get("on_empty") == "exit"):
                    ends = True
        if not ends:
            out.append("there is no exit (E) in a site with an \"at\": a world without end needs one somewhere")
    return out


def duel_problems(data):
    """Card duels in levels: each names a character the game has (one with stats to fight with)."""
    out = []
    chars = getattr(data, "characters", None) or {}
    for mid, m in (data.monsters or {}).items():
        if isinstance(m, dict) and m.get("duel") and m["duel"] not in chars:
            out.append("monster '%s': its duel is with '%s', not a character" % (mid, m["duel"]))
    for lid, spec in (data.levels or {}).items():
        for ch, v in ((spec or {}).get("legend") or {}).items():
            if isinstance(v, dict) and v.get("duel"):
                if v["duel"] not in chars:
                    out.append("level '%s' legend '%s': its duel is with '%s', not a character" % (lid, ch, v["duel"]))
                if v.get("switch") is None:
                    out.append("level '%s' legend '%s': a duel is on a switch (a terminal)" % (lid, ch))
    return out


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
        if a.get("kind") not in (None, "melee", "hitscan", "projectile", "spawner", "cron", "barrel", "flame", "none"):
            problems.append("monster '%s': unknown attack kind '%s'" % (kind, a.get("kind")))
        spawn = a.get("spawn")
        if spawn and spawn not in mons:
            problems.append("monster '%s': spawns unknown monster '%s'" % (kind, spawn))
        for job in a.get("crontab") or []:
            if job.get("do") == "fork" and job.get("spawn") and job["spawn"] not in mons:
                problems.append("monster '%s': its crontab forks unknown monster '%s'" % (kind, job["spawn"]))
        if spec.get("drops") and spec["drops"] not in items:
            problems.append("monster '%s': drops unknown item '%s'" % (kind, spec["drops"]))
        if spec.get("kind") == "ball":
            for key in ("roll", "speed"):
                if key in spec and (not isinstance(spec[key], int) or isinstance(spec[key], bool) or spec[key] < 1):
                    problems.append("monster '%s': %s should be a whole number, 1 or more" % (kind, key))
            c = spec.get("crush")
            if c is not None and not (isinstance(c, list) and len(c) == 2 and all(isinstance(v, int) for v in c)):
                problems.append("monster '%s': crush should be [least, most]" % kind)
        veh = spec.get("vehicle")
        if isinstance(veh, dict):
            if "fuel" in veh and (not isinstance(veh["fuel"], int) or isinstance(veh["fuel"], bool) or veh["fuel"] < 0):
                problems.append("monster '%s': its vehicle's fuel should be a number of beats (0 or more)" % kind)
            if veh.get("on_empty") not in (None, "exit", "land"):
                problems.append("monster '%s': on_empty should be \"exit\" or \"land\", not '%s'" % (kind, veh["on_empty"]))
            gun = veh.get("gun")
            if gun is not None and not (isinstance(gun, dict) and isinstance(gun.get("damage"), list)
                                        and len(gun["damage"]) == 2):
                problems.append("monster '%s': its vehicle's gun should be a weapon with damage [least, most]" % kind)
        problems += ai.brain.problems(spec.get("brain"), "monster '%s'" % kind)
        if spec.get("squad_tactic") is not None and spec["squad_tactic"] not in ai.squad.TACTICS:
            problems.append("monster '%s': squad_tactic should be one of %s" % (kind, ", ".join(ai.squad.TACTICS)))
        for gear, keys in (("grenades", ("count", "range", "fuse", "blast", "every")), ("mines", ("count",))):
            g = spec.get(gear)
            if g is None:
                continue
            if not isinstance(g, dict):
                problems.append("monster '%s': %s should be an object" % (kind, gear))
                continue
            for k in keys:
                if k in g and not (isinstance(g[k], int) and not isinstance(g[k], bool) and g[k] >= 0):
                    problems.append("monster '%s': %s %s should be a whole number" % (kind, gear, k))
            if gear == "mines" and not ((data.items or {}).get(g.get("item", "mine")) or {}).get("pickup", {}).get("mine"):
                problems.append("monster '%s': its mines should be an item with \"pickup\": {\"mine\": ...} (\"%s\")"
                                % (kind, g.get("item", "mine")))
        sp = spec.get("sprite") or kind
        models = getattr(data, "models", None) or {}
        if spec.get("model") and spec["model"] not in models:
            problems.append("monster '%s': no model '%s' in models.json" % (kind, spec["model"]))
        elif sp not in sprites and not spec.get("model"):
            problems.append("monster '%s': no sprite '%s' in sprites.json" % (kind, sp))
    from . import model as model_mod
    models = getattr(data, "models", None) or {}
    problems += model_mod.problems(models)
    for iid, it in items.items():
        pk = (it or {}).get("pickup") if isinstance(it, dict) else None
        if isinstance(pk, dict) and pk.get("model") and pk["model"] not in models:
            problems.append("item '%s': no model '%s' in models.json" % (iid, pk["model"]))
        if isinstance(pk, dict) and "fuel" in pk and (not isinstance(pk["fuel"], int) or pk["fuel"] < 1):
            problems.append("item '%s': fuel should be a number of beats, 1 or more" % iid)
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
        land = lv.get("land")
        if lv.get("death_text") and lv["death_text"] not in (getattr(data, "texts", None) or {}):
            problems.append("level '%s': death_text '%s' is not a text in texts.json" % (lid, lv["death_text"]))
        if lv.get("squads") is not None:
            problems.extend("level '%s': %s" % (lid, p) for p in ai.squad.problems(lv["squads"]))
        if lv.get("world") is not None or lv.get("generate") is not None:   # made as it goes, or from a seed
            problems.extend("level '%s': %s" % (lid, p) for p in made_problems(lv, data, sprites))
            continue
        if lv.get("render") is not None and lv.get("render") not in ("classic", "mesh"):
            problems.append("level '%s': render should be classic or mesh" % lid)
        if lv.get("climb") is not None and (isinstance(lv["climb"], bool) or not isinstance(lv["climb"], (int, float))
                                             or lv["climb"] < 0):
            problems.append("level '%s': climb should be the highest step walked up (walls' heights)" % lid)
        rows = lv.get("map")
        if land is not None and rows is None:
            rows = []                                # open land: the map (a camp, a compound) is optional
        elif not isinstance(rows, list) or not rows or not all(isinstance(r, str) for r in rows):
            problems.append("level '%s': map should be a list of rows of text" % lid)
            continue
        legend = dict(LEGEND)
        legend.update(lv.get("legend") or {})
        starts = sum(r.count(ch) for r in rows for ch, spec in legend.items()
                     if isinstance(spec, dict) and spec.get("start"))
        if land is not None:
            from . import land as land_mod
            problems.extend("level '%s': %s" % (lid, p) for p in land_mod.problems(
                land, sprites, getattr(data, "models", None) or {}))
            if isinstance(land, dict):
                size = land.get("size") if isinstance(land.get("size"), list) else [96, 96]
                st = land.get("start")
                if starts == 0 and st is None:
                    problems.append("level '%s': give the land a \"start\": [x, y], or the map a start (@)" % lid)
                elif starts > 1 or (starts and st is not None):
                    problems.append("level '%s': one start: the map's (@) or the land's \"start\", not both" % lid)
                elif st is not None and not (isinstance(st, list) and len(st) == 2 and
                                             all(isinstance(v, int) for v in st) and 0 <= st[0] < size[0] and 0 <= st[1] < size[1]):
                    problems.append("level '%s': the land's start should be [x, y] inside its size" % lid)
                for t in list(land.get("things") or []) + list(land.get("scatter") or []):
                    if not isinstance(t, dict):
                        continue
                    if t.get("monster") and t["monster"] not in mons:
                        problems.append("level '%s': the land has an unknown monster '%s'" % (lid, t["monster"]))
                    if t.get("item") and t["item"] not in (data.items or {}):
                        problems.append("level '%s': the land has an unknown item '%s'" % (lid, t["item"]))
        elif starts != 1:
            problems.append("level '%s': the map should have one start (@), it has %d" % (lid, starts))
        used = set("".join(rows))

        def ends(sp):                                # a way the level ends: an exit, or a ride that ends it
            if not isinstance(sp, dict):
                sp = {"monster": sp} if sp in mons else {}
            veh = (mons.get(sp.get("monster")) or {}).get("vehicle") if sp.get("monster") else None
            return bool(sp.get("exit")) or (isinstance(veh, dict) and veh.get("on_empty") == "exit")
        land_things = list(land.get("things") or []) if isinstance(land, dict) else []
        if not any(ends(legend.get(ch)) for ch in used) and not any(ends(t) for t in land_things):
            problems.append("level '%s': there is no exit (E)" % lid)
        if lv.get("sky") is not None and not isinstance(lv["sky"], dict):
            problems.append("level '%s': sky should be an object (top, horizon, sun, ridges, clouds, stars)" % lid)
        listening = set()
        for ch in used:
            sp = legend.get(ch)
            if isinstance(sp, dict):
                listening |= {sp.get("opens_on"), sp.get("closes_on"), sp.get("wake_on"), sp.get("mag_off_on")}
                if isinstance(sp.get("lamp"), dict):
                    listening |= {sp["lamp"].get("on_on"), sp["lamp"].get("off_on")}
        for key in ("lights", "weather"):
            if isinstance(lv.get(key), dict) and isinstance(lv[key].get("events"), dict):
                listening |= set(lv[key]["events"])
        listening |= set((lv.get("events") or {}))
        counts = {}
        for ch in used:
            sp = legend.get(ch)
            if isinstance(sp, dict):
                for key in ("teleport", "lift", "plate", "open_while", "stairs", "mag", "hatch"):
                    if sp.get(key):
                        counts.setdefault((key, sp[key]), 0)
                        counts[(key, sp[key])] += sum(r.count(ch) for r in rows)
        for (key, name), n in sorted(counts.items()):
            if key in ("stairs", "mag") and n != 2:
                problems.append("level '%s': the %s '%s' should have two ends, it has %d"
                                % (lid, "stairs" if key == "stairs" else "magnetic plating", name, n))
            if key == "hatch" and n != 2:
                problems.append("level '%s': the hatch '%s' should have two ends, it has %d" % (lid, name, n))
            if key == "teleport" and n < 2:
                problems.append("level '%s': the teleporter '%s' has one pad; it needs another to lead to" % (lid, name))
            if key == "lift" and n != 2:
                problems.append("level '%s': the lift '%s' should have two ends, it has %d" % (lid, name, n))
            if key == "open_while" and ("plate", name) not in counts:
                problems.append("level '%s': no plate called '%s' holds what opens while it is down" % (lid, name))
        from .atmosphere import problems as atmosphere_problems
        problems += atmosphere_problems(lid, lv, {ch: legend.get(ch) for ch in used})
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
            if spec.get("switch") is not None:
                if not isinstance(spec["switch"], str) or not spec["switch"]:
                    problems.append("level '%s': '%s' is a switch; its value should be the name of the event it sets off"
                                    % (lid, ch))
                elif spec["switch"] not in listening:
                    problems.append("level '%s': the switch '%s' sets off '%s', but nothing opens, closes or wakes on it"
                                    % (lid, ch, spec["switch"]))
            for key in ("locker", "supply"):
                if spec.get(key) is not None:
                    v = spec[key]
                    ids = [v] if isinstance(v, str) else v if isinstance(v, list) else [] if v is True else None
                    if ids is None or not all(isinstance(i, str) for i in ids):
                        problems.append("level '%s': '%s' is a %s; its value should be a list of item ids (or true: "
                                        "empty)" % (lid, ch, "locker" if key == "locker" else "supply crate"))
                    else:
                        for i in ids:
                            if i not in items:
                                problems.append("level '%s': the %s '%s' holds an unknown item '%s'"
                                                % (lid, "locker" if key == "locker" else "supply crate", ch, i))
            if spec.get("from") is not None:
                if str(spec["from"]).lower()[:1] not in FACING or not spec["from"]:
                    problems.append("level '%s': '%s' opens from '%s'; it should be n, e, s or w" % (lid, ch, spec["from"]))
                elif not (spec.get("door") or spec.get("gate")):
                    problems.append("level '%s': '%s' has \"from\", but only a door opens from one side" % (lid, ch))
            for key in ("height", "ceiling_height"):
                v = spec.get(key)
                if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
                    problems.append("level '%s': '%s' %s should be a number (walls' heights)" % (lid, ch, key))
            if isinstance(spec.get("ceiling_height"), (int, float)) and \
                    spec["ceiling_height"] <= (spec.get("height") if isinstance(spec.get("height"), (int, float)) else 0):
                problems.append("level '%s': '%s' has its ceiling at or under its floor" % (lid, ch))
            if spec.get("world_up") is not None and str(spec["world_up"]).lower() not in FACING:
                problems.append("level '%s': '%s' world_up should be n, e, s or w (the way in the map the world's up "
                                "is)" % (lid, ch))
            if spec.get("sheds") is not None:
                sh = spec["sheds"]
                kind = sh.get("monster", "glass") if isinstance(sh, dict) else None
                mspec = (data.monsters or {}).get(kind) if kind else None
                if not isinstance(sh, dict) or not isinstance(mspec, dict):
                    problems.append("level '%s': '%s' sheds should name a monster the game has (\"monster\")"
                                    % (lid, ch))
                elif not mspec.get("falls"):
                    problems.append("level '%s': '%s' sheds '%s', which does not fall (its \"falls\")" % (lid, ch, kind))
                elif isinstance(sh.get("every", 6), bool) or not isinstance(sh.get("every", 6), int) or sh.get("every", 6) < 1:
                    problems.append("level '%s': '%s' sheds every so many beats (1 or more)" % (lid, ch))
            if spec.get("high") and not (spec.get("switch") or spec.get("exit") or spec.get("locker") is not None
                                         or spec.get("panel")):
                problems.append("level '%s': '%s' is \"high\", but only a switch, an exit, a locker or a panel is "
                                "reached from the ceiling" % (lid, ch))
            if (spec.get("mag_off_on") or spec.get("mag_delay")) and not spec.get("ceiling_mag"):
                problems.append("level '%s': '%s' cuts the power of a plated ceiling, but its ceiling is not plated "
                                "(\"ceiling_mag\": true)" % (lid, ch))
            if spec.get("mag_delay") is not None and (isinstance(spec["mag_delay"], bool)
                                                      or not isinstance(spec["mag_delay"], int) or spec["mag_delay"] < 0):
                problems.append("level '%s': '%s' mag_delay should be the beats after its event (0 or more)" % (lid, ch))
            if spec.get("open_for") is not None:
                v = spec["open_for"]
                if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                    problems.append("level '%s': '%s' open_for should be the beats it stays open (1 or more)" % (lid, ch))
                elif not (spec.get("door") or spec.get("gate")):
                    problems.append("level '%s': '%s' has open_for, but only a door shuts on its own" % (lid, ch))
            if spec.get("zap") is not None and (isinstance(spec["zap"], bool) or not isinstance(spec["zap"], int)
                                                or spec["zap"] < 0):
                problems.append("level '%s': '%s' zap should be the damage the field does (0 or more)" % (lid, ch))
            for key, what in (("on_open", "opening it"), ("on_death", "its death")):
                if spec.get(key) is not None and (not isinstance(spec[key], str) or not spec[key]):
                    problems.append("level '%s': '%s' %s should be the name of the event %s sets off"
                                    % (lid, ch, key, what))
                elif spec.get(key) and spec[key] not in listening:
                    problems.append("level '%s': '%s' sets off '%s' (%s), but nothing opens, closes or wakes on it"
                                    % (lid, ch, spec[key], key))
            if spec.get("roll") is not None:
                if str(spec["roll"]).lower()[:1] not in FACING or not spec["roll"]:
                    problems.append("level '%s': '%s' rolls '%s'; it should be n, e, s or w" % (lid, ch, spec["roll"]))
                elif (mons.get(spec.get("monster")) or {}).get("kind") != "ball":
                    problems.append("level '%s': '%s' has roll, but only a ball (a monster of kind \"ball\") rolls"
                                    % (lid, ch))
    fp = data.config.get("first_person") or {}
    saves = fp.get("saves")
    if saves is not None and (isinstance(saves, bool) or not isinstance(saves, int) or saves < 0):
        problems.append("first_person \"saves\" should be a number of saves a level allows (0 or more), not %r" % (saves,))
    if "autosave" in fp and not isinstance(fp["autosave"], bool):
        problems.append("first_person \"autosave\" should be true or false")
    for where, v in [("first_person", fp.get("realtime"))] + [("level '%s'" % k, (lv or {}).get("realtime"))
                                                           for k, lv in (data.levels or {}).items() if isinstance(lv, dict)]:
        if v is not None and v is not False and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
            problems.append("%s \"realtime\" should be the seconds a beat lasts (0 or false: not in real time)" % where)
    return problems
