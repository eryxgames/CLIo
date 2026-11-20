# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Arcade stages: a platformer, or a top-down chase, played in real time.

A stage (``stages.json``) is a map of characters, a line a row::

    "map": ["#..........E#",
            "#.....*..===#",
            "#@..w....^^.#",
            "#############"]

``#`` wall, ``=`` a platform (stood on from above, jumped through from below; down and jump drop
through it), ``H`` ladder, ``^`` spikes, ``~`` a pit (lava, the void: a life lost), ``D`` a door (a
key opens it), ``E`` the exit, ``!`` a checkpoint, ``*`` a chip, ``+`` a heart, ``k`` a key, ``@``
where the player starts; a letter of an enemy kind is an enemy (``w`` walker, ``h`` hopper, ``f``
flyer, ``c`` chaser, ``t`` turret). A stage's ``legend`` gives other characters a meaning.

``mode``: ``platformer`` (gravity, jumps, ladders) or ``topdown`` (four ways and the diagonals).
``goal``: ``exit`` (reach it, with ``need`` chips if said), ``chips`` (take them all), ``clear``
(no enemy left) or ``survive`` (``time`` seconds). ``time`` is otherwise a limit; ``lives`` and
``health`` the player's; ``gun``: the fire key shoots.

It runs at a fixed rate (engine/realtime.py) on whole numbers alone: positions and speeds in 256ths
of a tile, no chance and no clock - the same keys at the same ticks play it the same way, so a
journal of them plays a run back.
"""

from __future__ import annotations

import hashlib
import math

from .realtime import RATE, Controls

FP = 256                                             # a tile, in the units positions and speeds are kept in
MODES = ("platformer", "topdown")
GOALS = ("exit", "chips", "clear", "survive")
MOVES = ("walk", "hop", "fly", "chase", "still")
TILES = ("empty", "wall", "platform", "ladder", "spikes", "pit", "door", "exit", "checkpoint")
THINGS = ("chip", "heart", "key", "start")
CHARS = {".": "empty", " ": "empty", "#": "wall", "=": "platform", "H": "ladder", "^": "spikes", "~": "pit",
         "D": "door", "E": "exit", "!": "checkpoint", "*": "chip", "+": "heart", "k": "key", "@": "start"}

# The keys (any of them): arrows, WASD, the vi keys; space or z jumps, x or f fires.
LEFT, RIGHT = ("left", "a", "h"), ("right", "d", "l")
UP, DOWN = ("up", "w", "k"), ("down", "s", "j")
JUMP, FIRE = ("space", "z"), ("x", "f", "enter")
PAUSE = ("esc", "p")

PHYSICS = {"speed": 5.0,      # tiles a second, running (top-down: walking)
           "jump": 3.5,       # tiles high, a jump held to the top
           "gravity": 1.0,    # 1: as the engine has it; 0.5 is the moon
           "fall": 12.0,      # tiles a second, falling at most
           "climb": 4.0,      # tiles a second, on a ladder
           "shot": 12.0,      # tiles a second, the player's shots
           "range": 12.0,     # tiles a shot flies
           "every": 0.3}      # seconds between the player's shots, at most

ENEMIES = {
    "walker": {"move": "walk", "char": "w", "speed": 2.5, "color": "#e0604a", "color2": "#ffb4a0"},
    "hopper": {"move": "hop", "char": "h", "speed": 2.0, "hop": 2.0, "every": 1.2, "color": "#8fd14f",
               "color2": "#d8ffb0"},
    "flyer": {"move": "fly", "char": "f", "speed": 2.0, "sight": 7, "color": "#b07cff", "color2": "#e6d4ff"},
    "chaser": {"move": "chase", "char": "c", "speed": 3.0, "sight": 8, "color": "#ff8a3d", "color2": "#ffd2a8"},
    "turret": {"move": "still", "char": "t", "shoots": True, "every": 1.5, "sight": 9, "hp": 2,
               "color": "#b8b8c0", "color2": "#ff5050"},
}
ENEMY = {"move": "walk", "speed": 2.0, "hp": 1, "damage": 1, "score": 50, "sight": 8, "stomp": True,
         "edges": "turn", "shoots": False, "every": 1.5, "shot": 7.0, "hop": 2.0, "aim": None}

COLORS = {"sky": "#10131c", "star": "#262c3c", "wall": "#4a5368", "wall_top": "#8a96b0", "wall_dark": "#3a4254",
          "platform": "#5fb0c8", "ladder": "#c8a050", "spikes": "#e04848", "spikes_tip": "#ffc0c0",
          "pit": "#d05020", "pit2": "#ff9030", "door": "#a06030", "door_dark": "#704020", "exit": "#60e080",
          "exit2": "#c0ffd0", "checkpoint": "#7080a0", "checkpoint_on": "#60e0ff", "chip": "#ffd84a",
          "heart": "#ff5a7a", "key": "#ffe070", "player": "#40c8ff", "player2": "#e8f8ff", "shot": "#ffffa0",
          "enemy_shot": "#ff7050", "flash": "#ffffff"}

SOUNDS = {"jump": ("jump", "tick"), "chip": ("chip", "coin"), "heart": ("heart", "heal"), "key": ("key", "pickup"),
          "door": ("door_open", "unlock"), "hurt": ("hurt", None), "die": ("die", "lose"), "stomp": ("stomp", "hit"),
          "kill": ("kill", "enemy_down"), "shoot": ("shoot", "tick"), "enemy_shoot": ("enemy_shoot", "tick"),
          "checkpoint": ("checkpoint", "save"), "clear": ("clear", "win"), "locked": ("locked", "locked")}
ACTIVE = 32 * FP                                     # enemies further from the player than this wait


def colour(c, default=(128, 128, 128)):
    """``"#rrggbb"`` or ``[r, g, b]`` as a tuple."""
    if isinstance(c, (list, tuple)) and len(c) == 3:
        return tuple(int(v) for v in c)
    if isinstance(c, str) and len(c) == 7 and c.startswith("#"):
        try:
            return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            pass
    return default


def sign(n):
    return (n > 0) - (n < 0)


def clamp(n, lo, hi):
    return lo if n < lo else hi if n > hi else n


def launch(g, tiles):
    """The speed up that rises ``tiles`` in ticks under gravity ``g`` (a tick's rise counted as it comes:
    v + (v - g) + (v - 2g) ... until it falls)."""
    h = int(float(tiles) * FP)
    return max(1, math.isqrt(2 * g * h + g * g // 4) - g // 2)


def approach(v, target, step):
    if v < target:
        return min(target, v + step)
    if v > target:
        return max(target, v - step)
    return v


class Body:
    """A thing that moves: the player, an enemy, a shot. ``x, y`` its top left corner, ``w, h`` its size."""
    __slots__ = ("x", "y", "w", "h", "vx", "vy", "kind", "hp", "dir", "timer", "hop", "flash", "alive",
                 "home", "axis", "climbing", "drop", "invuln", "cool", "fx", "fy", "owner", "ttl", "damage", "spec")

    def __init__(self, x, y, w, h, kind="player"):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.vx = self.vy = 0
        self.kind = kind
        self.hp, self.dir, self.timer, self.hop, self.flash = 1, 1, 0, 0, 0
        self.alive = True
        self.home = y
        self.axis = "x"
        self.climbing, self.drop, self.invuln, self.cool = False, 0, 0, 0
        self.fx, self.fy = 1, 0
        self.owner, self.ttl, self.damage, self.spec = None, 0, 1, None

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def copy(self):
        b = Body.__new__(Body)
        for k in Body.__slots__:
            setattr(b, k, getattr(self, k))
        return b

    def key(self):
        return (self.x, self.y, self.vx, self.vy, self.hp, self.dir, self.timer, self.hop, self.alive,
                self.climbing, self.drop, self.invuln, self.cool, self.fx, self.fy, self.ttl)


def overlap(a, b):
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


def settings_of(data):
    """game.json's ``arcade``: enemies, colours, physics and sounds of all the game's stages."""
    cfg = (getattr(data, "config", None) or {}).get("arcade") or {}
    return cfg if isinstance(cfg, dict) else {}


def enemy_kinds(data=None, spec=None):
    """The engine's enemy kinds, the game's over them, and a stage's over those."""
    kinds = {k: dict(v) for k, v in ENEMIES.items()}
    for src in (settings_of(data).get("enemies") if data is not None else None, (spec or {}).get("enemies")):
        for k, v in (src or {}).items():
            if isinstance(v, dict):
                kinds[k] = dict(kinds.get(k, {}), **v)
    return kinds


def legend_of(kinds, spec):
    """Each character of a map: ``(tile, thing)``; a thing is a pickup, ``start``, or ``("enemy", kind, more)``."""
    out = {ch: ((k, None) if k in TILES else ("empty", k)) for ch, k in CHARS.items()}
    for kind, s in kinds.items():
        ch = s.get("char")
        if isinstance(ch, str) and len(ch) == 1 and ch not in CHARS:
            out[ch] = ("empty", ("enemy", kind, {}))
    for ch, v in ((spec or {}).get("legend") or {}).items():
        if not (isinstance(ch, str) and len(ch) == 1):
            continue
        more = {}
        if isinstance(v, dict):
            more = {k: x for k, x in v.items() if k not in ("tile", "enemy", "thing")}
            v = v.get("enemy") or v.get("tile") or v.get("thing")
        if v in TILES:
            out[ch] = (v, None)
        elif v in THINGS:
            out[ch] = ("empty", v)
        elif v in kinds:
            out[ch] = ("empty", ("enemy", v, more))
    return out


def map_rows(spec):
    m = spec.get("map")
    if isinstance(m, str):
        m = m.split("\n")
    return [r for r in m if isinstance(r, str)] if isinstance(m, list) else []


class Stage:
    """One stage being played: :meth:`step` it a tick at a time with :class:`engine.realtime.Controls`.

    ``result`` is ``won``, ``lost`` or ``quit`` as soon as it is decided; ``over`` follows when the
    stage has shown it (a second or two)."""

    def __init__(self, spec, sid="stage", data=None, rate=RATE):
        self.id, self.spec, self.rate = sid, spec, rate
        self.name = spec.get("title") or spec.get("name") or sid
        self.mode = spec.get("mode") if spec.get("mode") in MODES else "platformer"
        self.topdown = self.mode == "topdown"
        self.goal = spec.get("goal") if spec.get("goal") in GOALS else "exit"
        cfg = settings_of(data)
        self.kinds = enemy_kinds(data, spec)
        ph = dict(PHYSICS, **(cfg.get("physics") or {}))
        ph.update(spec.get("physics") or {})
        self.ph = self._physics(ph)
        self.colors = {k: colour(v) for k, v in dict(COLORS, **(cfg.get("colors") or {}),
                                                     **(spec.get("colors") or {})).items()}
        self.sound_names = dict(SOUNDS)
        for src in (cfg.get("sounds"), spec.get("sounds")):
            for k, v in (src or {}).items():
                if isinstance(v, str):
                    self.sound_names[k] = (v, SOUNDS.get(k, (None, None))[1])
        self.gun = bool(spec.get("gun"))
        self.max_health = max(1, int(spec.get("health", 3)))
        self.health = self.max_health
        self.lives = max(1, int(spec.get("lives", 3)))
        self.time_ticks = int(round(float(spec["time"]) * rate)) if spec.get("time") else 0
        rows = map_rows(spec)
        self.W = max([len(r) for r in rows] or [1])
        self.H = max(1, len(rows))
        legend = legend_of(self.kinds, spec)
        self.grid = []
        self.items = {}                                  # (tx, ty) -> chip / heart / key
        self.enemies = []
        start = (1, 1)
        for ty in range(self.H):
            row = rows[ty] if ty < len(rows) else ""
            out = []
            for tx in range(self.W):
                ch = row[tx] if tx < len(row) else "."
                tile, thing = legend.get(ch, ("empty", None))
                out.append(tile)
                if thing == "start":
                    start = (tx, ty)
                elif thing in ("chip", "heart", "key"):
                    self.items[(tx, ty)] = thing
                elif isinstance(thing, tuple):
                    self.enemies.append(self._enemy(thing[1], thing[2], tx, ty, len(self.enemies)))
            self.grid.append(out)
        pw, ph_ = (FP * 11 // 16, FP * 7 // 8) if not self.topdown else (FP * 11 // 16, FP * 11 // 16)
        self.player = Body(0, 0, pw, ph_)
        self.check = start
        self._place(self.player, start)
        self.chips_total = sum(1 for v in self.items.values() if v == "chip")
        need = spec.get("need")
        self.need = self.chips_total if need == "all" or self.goal == "chips" else \
            (min(int(need), self.chips_total) if isinstance(need, (int, float)) and not isinstance(need, bool) else 0)
        self.kills_total = len(self.enemies)
        self.tick = self.ticks = 0
        self.chips = self.keys = self.score = self.kills = self.deaths = 0
        self.coyote = self.buffer = 0
        self.result = self.over = self.why = None
        self.paused = "ready" if spec.get("intro") or spec.get("ready", True) else None
        self.dying = self.ending = 0
        self.shots = []
        self.events = []
        self.note = ("", "text", 0)
        self.opened = []                                 # doors opened, as (tx, ty)

    # ---- set up ------------------------------------------------------------ #
    def _physics(self, p):
        r = self.rate

        def per_tick(tiles_a_second):
            return max(1, int(round(float(tiles_a_second) * FP / r)))
        g = max(1, int(round(18 * float(p["gravity"]) * (20.0 / r) ** 2)))
        speed = per_tick(p["speed"])
        jump = launch(g, p["jump"])
        return {"speed": speed, "accel": max(1, speed // 4), "air": max(1, speed // 6),
                "friction": max(1, speed // 3), "gravity": g, "jump": jump, "bounce": jump * 3 // 4,
                "fall": min(FP * 3 // 4, per_tick(p["fall"])), "climb": per_tick(p["climb"]),
                "shot": min(FP * 3 // 4, per_tick(p["shot"])), "range": max(1, int(float(p["range"]) * FP)),
                "every": max(1, int(round(float(p["every"]) * r))), "coyote": max(1, r // 7),
                "buffer": max(1, r // 7), "invulnerable": r * 3 // 2, "knock": per_tick(4)}

    def _enemy(self, kind, more, tx, ty, i):
        s = dict(ENEMY, **self.kinds.get(kind, {}))
        s.update(more or {})
        size = FP * 13 // 16
        e = Body(tx * FP + (FP - size) // 2, (ty + 1) * FP - size, size, size, kind)
        e.spec = s
        e.hp = max(1, int(s.get("hp", 1)))
        e.dir = -1 if s.get("dir") in ("left", "up", -1) else 1
        e.axis = "y" if s.get("axis") == "y" else "x"
        e.home = e.y
        every = max(1, int(round(float(s.get("every", 1.5)) * self.rate)))
        e.timer = every // 2 + (i * 7) % every            # not all at once
        e.hop = every
        return e

    def _place(self, b, at):
        tx, ty = at
        b.x = tx * FP + (FP - b.w) // 2
        b.y = (ty + 1) * FP - b.h
        b.vx = b.vy = 0

    def _speed(self, s, key):
        return max(0, int(round(float(s.get(key, 2)) * FP / self.rate)))

    # ---- the map ----------------------------------------------------------- #
    def kind_at(self, tx, ty):
        if tx < 0 or tx >= self.W or ty < 0:
            return "wall"
        if ty >= self.H:
            return "wall" if self.topdown else "empty"
        return self.grid[ty][tx]

    def _top(self, tx, ty):
        """A surface stood on from above but passed from below: a platform, a ladder's top."""
        k = self.kind_at(tx, ty)
        if self.topdown:
            return False
        return k == "platform" or (k == "ladder" and self.kind_at(tx, ty - 1) != "ladder")

    def _blocks(self, b, tx, ty):
        k = self.kind_at(tx, ty)
        if k == "wall" or (k == "platform" and self.topdown):
            return True
        if k == "door":
            if b is self.player and self.keys > 0:
                self.keys -= 1
                self.grid[ty][tx] = "empty"
                self.opened.append((tx, ty))
                self.events.append("door")
                self.tell("A key opens the door.", "good")
                return False
            if b is self.player and self.note[0] != "Locked: a key opens it.":
                self.events.append("locked")
                self.tell("Locked: a key opens it.", "alert")
            return True
        return False

    def _cols(self, b):
        return range(b.x // FP, (b.x + b.w - 1) // FP + 1)

    def _rows(self, b):
        return range(b.y // FP, (b.y + b.h - 1) // FP + 1)

    def _move_x(self, b, dx):
        """Move across; True when a wall stopped it."""
        if dx == 0:
            return False
        nx = b.x + dx
        tx = (nx + b.w - 1) // FP if dx > 0 else nx // FP
        for ty in self._rows(b):
            if self._blocks(b, tx, ty):
                b.x = tx * FP - b.w if dx > 0 else (tx + 1) * FP
                return True
        b.x = nx
        return False

    def _move_y(self, b, dy, drop=False):
        """Move up or down; True when something stopped it (a floor, a ceiling)."""
        if dy == 0:
            return False
        ny = b.y + dy
        if dy > 0:
            ty = (ny + b.h - 1) // FP
            above = b.y + b.h <= ty * FP
            for tx in self._cols(b):
                if self._blocks(b, tx, ty) or (not drop and above and self._top(tx, ty)):
                    b.y = ty * FP - b.h
                    return True
        else:
            ty = ny // FP
            for tx in self._cols(b):
                if self._blocks(b, tx, ty):
                    b.y = (ty + 1) * FP
                    return True
        b.y = ny
        return False

    def _on_ground(self, b, drop=False, solid_only=False):
        if self.topdown or (b.y + b.h) % FP:
            return False
        ty = (b.y + b.h) // FP
        for tx in self._cols(b):
            k = self.kind_at(tx, ty)
            if k in ("wall", "door") or (not drop and not solid_only and self._top(tx, ty)):
                return True
        return False

    def _ladder_col(self, b):
        return b.cx // FP

    def _on_ladder(self, b):
        tx = self._ladder_col(b)
        return any(self.kind_at(tx, ty) == "ladder" for ty in self._rows(b))

    def _ladder_under(self, b):
        return (b.y + b.h) % FP == 0 and self.kind_at(self._ladder_col(b), (b.y + b.h) // FP) == "ladder"

    def _sees(self, e, sight):
        p = self.player
        dx, dy = p.cx - e.cx, p.cy - e.cy
        r = int(sight * FP)
        if dx * dx + dy * dy > r * r:
            return False
        n = max(abs(dx), abs(dy)) // (FP // 2) + 1
        for i in range(1, n):
            x, y = e.cx + dx * i // n, e.cy + dy * i // n
            if self.kind_at(x // FP, y // FP) in ("wall", "door"):
                return False
        return True

    # ---- a tick ------------------------------------------------------------ #
    def tell(self, text, role="text", seconds=2.0):
        self.note = (text, role, self.tick + int(seconds * self.rate))

    def step(self, c):
        """One tick: the player's keys, then the enemies, the shots, what touches what."""
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
            elif c.pressed and (self.paused == "ready" or c.hit(*(PAUSE + ("enter", "space")))):
                self.paused = None
            return
        if c.hit(*PAUSE):
            self.paused = "paused"
            return
        if self.dying:
            self.dying -= 1
            if not self.dying:
                self._respawn()
            return
        self.ticks += 1
        self._player(c)
        p = self.player
        for e in self.enemies:
            if e.alive and abs(e.x - p.x) <= ACTIVE and abs(e.y - p.y) <= ACTIVE:
                self._enemy_step(e)
        self._shots()
        self._touch(c)
        self._goal()

    def _player(self, c):
        p = self.player
        ax, ay = c.axis(LEFT, RIGHT), c.axis(UP, DOWN)
        if p.cool:
            p.cool -= 1
        if p.invuln:
            p.invuln -= 1
        if ax:
            p.dir = p.fx = ax
        if ax or ay:
            p.fx, p.fy = (ax, ay) if self.topdown else (p.fx, 0)
        if self.topdown:
            self._walk(p, ax, ay)
        else:
            self._platform(p, c, ax, ay)
        if self.gun and c.down(*FIRE) and not p.cool:
            self._fire(p)

    def _walk(self, p, ax, ay):
        ph = self.ph
        s = ph["speed"] * 181 // 256 if ax and ay else ph["speed"]
        p.vx = approach(p.vx, ax * s, ph["accel"] if ax else ph["friction"])
        p.vy = approach(p.vy, ay * s, ph["accel"] if ay else ph["friction"])
        if self._move_x(p, p.vx):
            p.vx = 0
        if self._move_y(p, p.vy):
            p.vy = 0

    def _platform(self, p, c, ax, ay):
        ph = self.ph
        up, down = ay < 0, ay > 0
        p.hop = p.y + p.h                                # where its feet were (a stomp lands from above)
        ground = self._on_ground(p, drop=p.drop > 0)
        if p.drop:
            p.drop -= 1
        self.coyote = ph["coyote"] if ground else max(0, self.coyote - 1)
        lad = self._on_ladder(p)
        if c.hit(*JUMP) or (c.hit(*UP) and not lad and not p.climbing):
            self.buffer = ph["buffer"]
        held = c.down(*JUMP) or (up and not lad and not p.climbing)
        if not p.climbing and ((up and lad) or (down and ((lad and not ground) or self._ladder_under(p)))):
            p.climbing, p.vx, p.vy = True, 0, 0
            p.x = self._ladder_col(p) * FP + (FP - p.w) // 2
        if p.climbing:
            if self.buffer:                              # a jump off the ladder
                p.climbing, self.buffer = False, 0
                p.vy, p.vx = -ph["jump"] * 3 // 4, ax * ph["speed"]
                self.events.append("jump")
            else:
                p.vx = ax * ph["climb"] // 2
                p.vy = -ph["climb"] if up else (ph["climb"] if down else 0)
                self._move_x(p, p.vx)
                stopped = self._move_y(p, p.vy, drop=True)
                if not self._on_ladder(p) or (stopped and down and ax):
                    p.climbing = False
                p.vy = 0
                return
        if down and self.buffer and ground and not self._on_ground(p, solid_only=True):
            p.drop, self.buffer, ground = ph["buffer"] + 3, 0, False      # down through a platform
        if self.buffer and (ground or self.coyote):
            p.vy, self.coyote, self.buffer = -ph["jump"], 0, 0
            self.events.append("jump")
        elif self.buffer:
            self.buffer -= 1
        if not held and p.vy < -ph["jump"] // 3:
            p.vy = -ph["jump"] // 3                       # let go early: a lower jump
        step = ph["accel"] if ground else ph["air"]
        if not ax and ground:
            step = ph["friction"]
        p.vx = approach(p.vx, ax * ph["speed"], step)
        if self._move_x(p, p.vx):
            p.vx = 0
        if self._move_y(p, p.vy, drop=p.drop > 0) and p.vy < 0:
            p.vy = 0                                      # a ceiling
        if self._on_ground(p, drop=p.drop > 0) and p.vy >= 0:
            p.vy = 0
        else:
            p.vy = min(ph["fall"], p.vy + ph["gravity"])

    def _fire(self, b, at=None):
        """A shot from ``b``: the player's where it faces, an enemy's at ``at`` (dx, dy)."""
        ph = self.ph
        if at is None:
            fx, fy = (b.fx, b.fy) if self.topdown else (b.dir, 0)
            if not fx and not fy:
                fx = b.dir
            speed, ttl, owner = ph["shot"], ph["range"] // max(1, ph["shot"]), "player"
            b.cool = ph["every"]
            self.events.append("shoot")
        else:
            fx, fy = at
            speed = self._speed(b.spec, "shot")
            ttl, owner = int(float(b.spec.get("sight", 8)) * FP * 3 // 2) // max(1, speed), "enemy"
            self.events.append("enemy_shoot")
        if fx and fy:
            speed = speed * 181 // 256
        s = Body(b.cx - FP // 8, b.cy - FP // 8, FP // 4, FP // 4, "shot")
        s.vx, s.vy, s.owner, s.ttl = fx * speed, fy * speed, owner, ttl
        s.damage = int(b.spec.get("damage", 1)) if b.spec else 1
        self.shots.append(s)

    def _enemy_step(self, e):
        s, p, ph = e.spec, self.player, self.ph
        if e.flash:
            e.flash -= 1
        move = s.get("move", "walk")
        speed = self._speed(s, "speed")
        sight = s.get("sight", 8)
        if self.topdown:
            if move in ("chase", "fly") and self._sees(e, sight):
                dx, dy = p.cx - e.cx, p.cy - e.cy
                k = 181 if dx and dy and abs(dx) > FP // 8 and abs(dy) > FP // 8 else 256
                e.vx = clamp(dx, -speed * k // 256, speed * k // 256)
                e.vy = clamp(dy, -speed * k // 256, speed * k // 256)
            elif move == "still":
                e.vx = e.vy = 0
            else:
                e.vx, e.vy = (e.dir * speed, 0) if e.axis == "x" else (0, e.dir * speed)
            hx = self._move_x(e, e.vx)
            hy = self._move_y(e, e.vy)
            if (hx and e.axis == "x") or (hy and e.axis == "y"):
                e.dir = -e.dir
        elif move == "fly":
            if self._sees(e, sight):
                e.vx = clamp(p.cx - e.cx, -speed, speed)
                e.vy = clamp(p.cy - e.cy, -speed, speed)
            else:
                e.vx = e.dir * max(1, speed // 2)
                e.vy = clamp(e.home - e.y, -max(1, speed // 2), max(1, speed // 2))
            if self._move_x(e, e.vx):
                e.dir = -e.dir
            self._move_y(e, e.vy, drop=True)
        elif move != "still":
            ground = self._on_ground(e)
            chasing = move == "chase" and self._sees(e, sight)
            if chasing and abs(p.cx - e.cx) > FP // 4:
                e.dir = sign(p.cx - e.cx)
            if move == "hop":
                e.hop -= 1
                if ground and e.hop <= 0:
                    e.vy = -launch(ph["gravity"], s.get("hop", 2))
                    e.hop = max(1, int(round(float(s.get("every", 1.2)) * self.rate)))
                    ground = False
            go = True
            if ground and s.get("edges", "turn") == "turn":
                fx = e.x + e.w + speed if e.dir > 0 else e.x - speed - 1
                ty = (e.y + e.h) // FP
                if not (self.kind_at(fx // FP, ty) in ("wall", "door") or self._top(fx // FP, ty)):
                    if chasing:
                        go = False                       # it waits at the edge for its prey
                    else:
                        e.dir = -e.dir
            if go and self._move_x(e, e.dir * speed):
                e.dir = -e.dir
            self._move_y(e, e.vy)
            if self._on_ground(e) and e.vy >= 0:
                e.vy = 0
            else:
                e.vy = min(ph["fall"], e.vy + ph["gravity"])
            if e.y >= self.H * FP:
                e.alive = False                          # off the bottom of the map
        if s.get("shoots"):
            e.timer -= 1
            if e.timer <= 0 and self._sees(e, sight):
                dx, dy = p.cx - e.cx, p.cy - e.cy
                aim = s.get("aim") or ("level" if not self.topdown else "any")
                if aim == "level":
                    if abs(dy) < FP * 3 // 4 and dx:
                        self._fire(e, (sign(dx), 0))
                        e.timer = max(1, int(round(float(s.get("every", 1.5)) * self.rate)))
                else:
                    fx = sign(dx) if 2 * abs(dx) >= abs(dy) else 0
                    fy = sign(dy) if 2 * abs(dy) >= abs(dx) else 0
                    self._fire(e, (fx, fy))
                    e.timer = max(1, int(round(float(s.get("every", 1.5)) * self.rate)))

    def _shots(self):
        keep = []
        for s in self.shots:
            s.x += s.vx
            s.y += s.vy
            s.ttl -= 1
            k = self.kind_at(s.cx // FP, s.cy // FP)
            if s.ttl <= 0 or k in ("wall", "door") or (self.topdown and k == "platform"):
                continue
            if s.owner == "player":
                hit = next((e for e in self.enemies if e.alive and overlap(s, e)), None)
                if hit is not None:
                    self._hurt_enemy(hit, s.damage)
                    continue
            elif overlap(s, self.player) and not self.dying:
                if not self.player.invuln:
                    self._hurt(s.damage, s.cx)
                    continue
            keep.append(s)
        self.shots = keep

    def _hurt_enemy(self, e, n, how="kill"):
        e.hp -= n
        e.flash = 4
        if e.hp <= 0:
            e.alive = False
            self.kills += 1
            self.score += int(e.spec.get("score", 50))
            self.events.append(e.spec.get("sound_death") or how)
        else:
            self.events.append(e.spec.get("sound_hurt") or "stomp")

    def _hurt(self, n, from_x):
        p = self.player
        if p.invuln or self.dying or self.result:
            return
        self.health -= n
        p.invuln = self.ph["invulnerable"]
        self.events.append("hurt")
        knock = self.ph["knock"]
        p.vx = knock if p.cx >= from_x else -knock
        if not self.topdown:
            p.climbing = False
            p.vy = -knock * 2
        if self.health <= 0:
            self._die()

    def _die(self):
        self.deaths += 1
        self.lives -= 1
        self.health = 0
        self.events.append("die")
        if self.lives <= 0:
            self._end("lost", "lives")
        else:
            self.dying = self.rate
            self.tell("Lost a life. %d left." % self.lives, "hurt")

    def _respawn(self):
        p = self.player
        self._place(p, self.check)
        p.climbing, p.drop = False, 0
        p.invuln = self.ph["invulnerable"] * 2
        self.health = self.max_health
        self.shots = [s for s in self.shots if s.owner == "player"]

    def _end(self, result, why=None):
        self.result, self.why = result, why
        self.ending = self.rate * 3 // 2
        if result == "won":
            self.events.append("clear")

    def _touch(self, c):
        p = self.player
        if self.dying:
            return
        # pickups, under any part of the player
        for tx in self._cols(p):
            for ty in self._rows(p):
                what = self.items.get((tx, ty))
                if what is None:
                    continue
                if what == "heart" and self.health >= self.max_health:
                    continue
                del self.items[(tx, ty)]
                if what == "chip":
                    self.chips += 1
                    self.score += 10
                elif what == "heart":
                    self.health += 1
                else:
                    self.keys += 1
                    self.tell("A key.", "good")
                self.events.append(what)
        # hazards
        bottom = (p.y + p.h - 1) // FP
        if not self.topdown and p.y >= self.H * FP:
            return self._die()
        for tx in self._cols(p):
            for ty in self._rows(p):
                k = self.kind_at(tx, ty)
                if k == "pit" and (self.topdown or p.y + p.h > ty * FP + FP // 3):
                    return self._die()
                if k == "spikes" and (self.topdown or (ty == bottom and p.y + p.h > ty * FP + FP // 2)):
                    self._hurt(1, tx * FP + FP // 2 if self.topdown else p.cx - p.vx * 4)
                    if not self.topdown and not self.dying:
                        p.vy = -self.ph["jump"] * 2 // 3  # thrown up off the spikes
        # enemies
        for e in self.enemies:
            if not e.alive or self.dying or not overlap(p, e):
                continue
            if (not self.topdown and e.spec.get("stomp", True) and p.vy > 0
                    and p.hop <= e.y + FP // 4 and not p.climbing):
                self._hurt_enemy(e, 99, "stomp")
                p.y = e.y - p.h
                p.vy = -(self.ph["jump"] if c.down(*JUMP) or c.down(*UP) else self.ph["bounce"])
                continue
            self._hurt(int(e.spec.get("damage", 1)), e.cx)
        # a checkpoint
        tx, ty = p.cx // FP, (p.y + p.h - 1) // FP
        if self.kind_at(tx, ty) == "checkpoint" and self.check != (tx, ty):
            self.check = (tx, ty)
            self.events.append("checkpoint")
            self.tell("Checkpoint.", "good")

    def _goal(self):
        if self.dying or self.result:
            return
        p = self.player
        g = self.goal
        if g == "survive":
            if self.ticks >= self.time_ticks:
                self._end("won")
            return
        if self.time_ticks and self.ticks >= self.time_ticks:
            self._end("lost", "time")
            return
        if g == "chips" and self.chips >= self.chips_total:
            self._end("won")
        elif g == "clear" and not any(e.alive for e in self.enemies):
            self._end("won")
        elif g == "exit" and self.kind_at(p.cx // FP, p.cy // FP) == "exit":
            if self.chips >= self.need:
                self._end("won")
            elif self.note[0][:4] != "Need":
                left = self.need - self.chips
                self.events.append("locked")
                self.tell("Need %d more chip%s." % (left, "" if left == 1 else "s"), "alert")

    # ---- what is kept ------------------------------------------------------ #
    def state_hash(self):
        """A digest of everything that decides what happens next (two runs alike are alike in it)."""
        parts = (self.tick, self.ticks, self.result, self.over, self.paused, self.dying, self.ending, self.health,
                 self.lives, self.chips, self.keys, self.score, self.kills, self.deaths, self.coyote, self.buffer,
                 self.check, self.player.key(), [e.key() for e in self.enemies], [s.key() for s in self.shots],
                 sorted(self.items.items()), self.opened)
        return hashlib.sha1(repr(parts).encode()).hexdigest()[:16]

    def clone(self):
        """A copy to play on without touching this one (the stage bot tries its moves on copies)."""
        st = Stage.__new__(Stage)
        st.__dict__.update(self.__dict__)
        st.grid = [r[:] for r in self.grid]
        st.items = dict(self.items)
        st.player = self.player.copy()
        st.enemies = [e.copy() for e in self.enemies]
        st.shots = [s.copy() for s in self.shots]
        st.opened = list(self.opened)
        st.events = []
        return st

    def stats(self):
        return {"result": self.result, "score": self.score, "chips": self.chips, "chips_total": self.chips_total,
                "kills": self.kills, "kills_total": self.kills_total, "deaths": self.deaths,
                "seconds": round(self.ticks / float(self.rate), 1)}


def make(data, sid, rate=RATE):
    """The stage ``sid`` of a game, ready to play."""
    spec = (getattr(data, "stages", None) or {}).get(sid)
    if not isinstance(spec, dict):
        raise KeyError("no stage '%s'" % sid)
    return Stage(spec, sid, data, rate)


# --------------------------------------------------------------------------- #
# Pictures
# --------------------------------------------------------------------------- #
GLYPH = {"empty": " ", "wall": "#", "platform": "=", "ladder": "H", "spikes": "^", "pit": "~", "door": "D",
         "exit": "E", "checkpoint": "!", "chip": "*", "heart": "+", "key": "k"}


class View:
    """What the stage looks like: half-block pixels (a tile two by two) or a character a tile. The camera
    follows the player and keeps inside the map; it is the picture's, not the stage's (no part of a run)."""

    def __init__(self, stage):
        self.st = stage
        self.cam = None
        self.size = None

    def _follow(self, pc, cam, view, size):
        if size <= view:
            return -((view - size) // 2)
        if cam is None:
            cam = pc - view // 2
        dz = max(1, view // 8)
        mid = cam + view // 2
        if pc < mid - dz:
            cam = pc - view // 2 + dz
        elif pc > mid + dz:
            cam = pc - view // 2 - dz
        return clamp(cam, 0, size - view)

    def camera(self, cols, rows, scale):
        st, p = self.st, self.st.player
        if self.size != (cols, rows, scale):
            self.cam, self.size = None, (cols, rows, scale)
        cx, cy = (None, None) if self.cam is None else self.cam
        cx = self._follow(p.cx * scale // FP, cx, cols, st.W * scale)
        cy = self._follow(p.cy * scale // FP, cy, rows * (2 if scale == 2 else 1), st.H * scale)
        self.cam = (cx, cy)
        return cx, cy

    def _tile_px(self, tx, ty, phase):
        """A tile's four pixels: top left, top right, bottom left, bottom right."""
        st, C = self.st, self.st.colors
        k = st.kind_at(tx, ty) if 0 <= tx < st.W and 0 <= ty < st.H else "out"
        sky = C["sky"]
        if k == "out":
            return (C["wall_dark"],) * 4
        if k == "empty":
            star = C["star"] if (tx * 7 + ty * 13) % 23 == 0 else sky
            return star, sky, sky, sky
        if k == "wall":
            top = C["wall_top"] if st.kind_at(tx, ty - 1) not in ("wall", "door") else C["wall"]
            return top, top, C["wall"], C["wall_dark"] if (tx + ty) % 2 else C["wall"]
        if k == "platform":
            return C["platform"], C["platform"], sky, sky
        if k == "ladder":
            return C["ladder"], C["ladder"], sky, sky
        if k == "spikes":
            return sky, C["spikes_tip"] if phase % 4 < 2 else sky, C["spikes"], C["spikes"]
        if k == "pit":
            a, b = (C["pit"], C["pit2"]) if phase % 4 < 2 else (C["pit2"], C["pit"])
            return a, b, b, a
        if k == "door":
            return C["door"], C["door"], C["door"], C["door_dark"]
        if k == "exit":
            a, b = (C["exit"], C["exit2"]) if phase % 2 else (C["exit2"], C["exit"])
            return a, b, b, a
        if k == "checkpoint":
            on = C["checkpoint_on"] if st.check == (tx, ty) else C["checkpoint"]
            return on, sky, on, sky
        return sky, sky, sky, sky

    def _bodies(self):
        """What to draw over the map: ``(body, colour on top, colour below)``, the player last."""
        st, C = self.st, self.st.colors
        out = []
        for e in st.enemies:
            if e.alive:
                hi, lo = colour(e.spec.get("color2"), C["flash"]), colour(e.spec.get("color"), C["spikes"])
                if e.flash:
                    hi = lo = C["flash"]
                out.append((e, hi, lo))
        for s in st.shots:
            c = C["shot"] if s.owner == "player" else C["enemy_shot"]
            out.append((s, c, c))
        p = st.player
        if not (p.invuln and st.tick % 4 < 2) and not st.dying:
            out.append((p, C["player2"], C["player"]))
        return out

    def pixels(self, cols, rows, phase=0):
        """Rows of cells ``(None, top, bottom)``: two pixels a cell, a tile two by two."""
        st, C = self.st, self.st.colors
        cx, cy = self.camera(cols, rows, 2)
        ph = rows * 2
        buf = [[C["sky"]] * cols for _ in range(ph)]
        tx0, ty0 = cx // 2, cy // 2
        for ty in range(ty0, (cy + ph - 1) // 2 + 1):
            for tx in range(tx0, (cx + cols - 1) // 2 + 1):
                px = self._tile_px(tx, ty, phase)
                item = st.items.get((tx, ty))
                if item:
                    c = C[item]
                    px = (c, px[1], px[2], c) if item == "chip" else ((c, c, px[2], c) if item == "heart" else
                                                                      (c, c, c, px[3]))
                for i, (ox, oy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
                    x, y = tx * 2 + ox - cx, ty * 2 + oy - cy
                    if 0 <= x < cols and 0 <= y < ph:
                        buf[y][x] = px[i]
        for b, hi, lo in self._bodies():
            if b.kind == "shot":
                x, y = b.cx * 2 // FP - cx, b.cy * 2 // FP - cy
                if 0 <= x < cols and 0 <= y < ph:
                    buf[y][x] = hi
                continue
            x, y = b.cx * 2 // FP - 1 - cx, (b.y + b.h) * 2 // FP - 2 - cy
            for ox, oy, c in ((0, 0, hi), (1, 0, hi), (0, 1, lo), (1, 1, lo)):
                if 0 <= x + ox < cols and 0 <= y + oy < ph:
                    buf[y + oy][x + ox] = c
        return [[(None, buf[2 * r][x], buf[2 * r + 1][x]) for x in range(cols)] for r in range(rows)]

    def glyphs(self, cols, rows, color=True, unicode=True):
        """Rows of cells ``(char, fg, bg)``: a character a tile."""
        st, C = self.st, self.st.colors
        cx, cy = self.camera(cols, rows, 1)
        sky = C["sky"] if color else None
        fgs = {"wall": "wall_top", "platform": "platform", "ladder": "ladder", "spikes": "spikes", "pit": "pit",
               "door": "door", "exit": "exit", "checkpoint": "checkpoint", "chip": "chip", "heart": "heart",
               "key": "key"}
        wall = "█" if unicode else "#"
        out = []
        for r in range(rows):
            ty = cy + r
            row = []
            for c in range(cols):
                tx = cx + c
                k = st.kind_at(tx, ty) if 0 <= tx < st.W and 0 <= ty < st.H else "out"
                if k == "out":
                    row.append((" ", None, None))
                    continue
                k = st.items.get((tx, ty)) or k
                ch = wall if k == "wall" else GLYPH.get(k, " ")
                if k == "checkpoint" and st.check == (tx, ty):
                    fg = C["checkpoint_on"]
                else:
                    fg = C[fgs[k]] if k in fgs else None
                row.append((ch, fg if color else None, sky))
            out.append(row)
        for b, hi, lo in self._bodies():
            x, y = b.cx // FP - cx, b.cy // FP - cy
            if 0 <= x < cols and 0 <= y < rows:
                if b.kind == "shot":
                    ch = "*" if b.owner == "enemy" else ("·" if unicode else ".")
                elif b is st.player:
                    ch = "@"
                else:
                    ch = b.spec.get("glyph") or b.spec.get("char") or b.kind[:1]
                out[y][x] = (ch, (lo if b is st.player else hi if b.kind == "shot" else lo) if color else None, sky)
        return out

    def hud(self, unicode=True):
        """The line above the picture: ``[(text, role)]``."""
        st = self.st
        parts = [(st.name + "   ", "title")]
        if unicode:
            parts.append(("♥" * max(0, st.health) + "♡" * max(0, st.max_health - st.health), "hurt"))
            parts.append(("  ×%d" % st.lives, "text"))
        else:
            parts.append(("HP %d/%d  LIVES %d" % (max(0, st.health), st.max_health, st.lives), "hurt"))
        if st.chips_total:
            parts.append(("   CHIPS %d/%d" % (st.chips, st.need or st.chips_total), "ammo"))
        if st.keys:
            parts.append(("   KEYS %d" % st.keys, "key_w"))
        if st.goal == "clear":
            parts.append(("   LEFT %d" % sum(1 for e in st.enemies if e.alive), "alert"))
        parts.append(("   SCORE %d" % st.score, "text"))
        if st.time_ticks:
            left = max(0, st.time_ticks - st.ticks) // st.rate
            parts.append(("   TIME %d:%02d" % (left // 60, left % 60), "alert" if left < 10 else "info"))
        return parts

    def banner(self):
        """Lines shown over the picture now (the intro, paused, the end), or []."""
        st = self.st
        if st.result == "won":
            return [("STAGE CLEAR", "good"), ("Score %d" % st.score, "text")]
        if st.result == "lost":
            return [("TIME UP" if st.why == "time" else "GAME OVER", "hurt")]
        if st.paused == "ready":
            intro = st.spec.get("intro") or []
            lines = [(st.name, "title"), ("", "text")]
            lines += [(t, "text") for t in (intro if isinstance(intro, list) else [intro])]
            return lines + [("", "text"), ("Press any key to start.", "prompt")]
        if st.paused:
            return [("PAUSED", "title"), ("P, Esc or Enter goes on; Q leaves the stage.", "dim")]
        return []


def help_line(stage, unicode=True):
    arrows = "←→" if unicode else "<>"
    s = "%s move   " % arrows
    if stage.topdown:
        s = ("↑↓←→" if unicode else "arrows") + " move   "
    else:
        s += "SPACE/↑ jump   " if unicode else "SPACE/up jump   "
        s += "↑↓ ladders   ↓+SPACE drop   " if unicode else "up/down ladders   down+SPACE drop   "
    if stage.gun:
        s += "X fire   "
    return s + "P pause"


# --------------------------------------------------------------------------- #
# Playing it
# --------------------------------------------------------------------------- #
class Runner:
    """A stage on the terminal for :class:`engine.realtime.Loop`: steps it, plays its sounds, draws it."""

    def __init__(self, stage, screen=None, audio=None):
        self.stage, self.screen, self.audio = stage, screen, audio
        self.view = View(stage)
        self.frames = 0

    @property
    def over(self):
        return self.stage.over

    def step(self, c):
        st = self.stage
        st.step(c)
        if self.audio is not None:
            for name in st.events[:2]:
                own, fallback = st.sound_names.get(name, (name, None))
                try:
                    self.audio.sfx(own, fallback) if fallback else self.audio.sfx(own)
                except Exception:
                    pass

    def rows(self, W, H, depth=3, unicode=True):
        """The screen's rows: the line above, the picture, with any banner over it."""
        from .frame import Painter
        st = self.stage
        paint = self.screen.paint if self.screen is not None else Painter(depth)
        vh = max(3, H - 3)
        if unicode and depth:
            pic = self.view.pixels(W, vh, st.tick // 3)
        else:
            pic = self.view.glyphs(W, vh, color=bool(depth), unicode=unicode)
        rows = [paint.text(self.view.hud(unicode), W)] + pic
        lines = self.view.banner()
        if lines:
            top = 1 + max(0, (vh - len(lines)) // 2)
            for i, (text, role) in enumerate(lines):
                if top + i < len(rows):
                    pad = max(0, (W - len(text)) // 2)
                    rows[top + i] = paint.text([(" " * pad + text + " " * max(0, W - pad - len(text)), role)], W)
        return rows

    def status(self):
        st = self.stage
        text, role, until = st.note
        return text if text and st.tick < until else ""

    def draw(self):
        if self.screen is None:
            return
        self.frames += 1
        scr = self.screen
        W, H = scr.size()
        unicode = scr.unicode and scr.glyphs.get("half") == "▀"
        rows = self.rows(W, H, scr.paint.depth, unicode)
        scr.frame(rows, status=self.status(), footer=scr.paint.text([(help_line(self.stage, unicode), "dim")], W))


def play_frame(stage, term, audio=None, keys=None, clock=None):
    """Play a stage on the terminal's own screen until it is over. The Recorder (its journal) is returned."""
    from .frame import Screen
    from .keys import KeyReader
    from .realtime import Loop
    screen = Screen(term, None, {}, term.animate)
    runner = Runner(stage, screen, audio)
    loop = Loop(runner, keys or KeyReader(), stage.rate, clock=clock)
    screen.start()
    try:
        loop.run()
    except KeyboardInterrupt:
        stage.result = stage.over = stage.result or "quit"
    finally:
        screen.stop()
    return loop.recorder


WORDS = {"left": "left", "l": "left", "right": "right", "r": "right", "up": "up", "u": "up", "down": "down",
         "d": "down", "jump": "space", "j": "space", "fire": "x", "f": "x", "wait": None, "w": None}
TEXT_HELP = ("Moves, a comma between them: keys held for a number of ticks (%d a second), e.g. "
             "'right 10, jump right 8, wait 5'. Words: left right up down jump fire wait (or l r u d j f w); "
             "'quit' leaves the stage. An empty line waits half a second.")


def parse_moves(line, default=6):
    """A typed line as ``[(keys, ticks), ...]``; ``None`` for quit; raises ValueError on a word not known."""
    line = line.strip().lower()
    if line in ("q", "quit", "exit"):
        return None
    if not line:
        return [((), 10)]
    out = []
    for part in line.replace(";", ",").split(","):
        words = part.split()
        if not words:
            continue
        keys, n = [], default
        for w in words:
            if w.isdigit():
                n = max(1, min(200, int(w)))
            elif w in WORDS:
                if WORDS[w]:
                    keys.append(WORDS[w])
            else:
                raise ValueError(w)
        out.append((tuple(keys), n))
    return out


def text_picture(stage, cols=40, rows=13):
    view = View(stage)
    lines = ["".join(ch for ch, _, _ in r).rstrip() for r in view.glyphs(cols, rows, color=False, unicode=False)]
    hud = "".join(t for t, _ in view.hud(unicode=False))
    return [hud] + lines


def play_text(stage, write, read):
    """A stage a typed line at a time (no screen of its own: piped input, a screen reader): each line is
    moves, each move keys held for some ticks; the picture after each line."""
    stage.paused = None
    intro = stage.spec.get("intro") or []
    write(stage.name)
    for t in (intro if isinstance(intro, list) else [intro]):
        write(t)
    write(TEXT_HELP % stage.rate)
    held = frozenset()
    tick = 0
    while not stage.result:
        for line in text_picture(stage):
            write(line)
        text, role, until = stage.note
        if text and stage.tick < until:
            write(text)
        line = read("> ")
        if line is None:
            stage.result = stage.over = "quit"
            break
        if line.strip().lower() in ("help", "?"):
            write(TEXT_HELP % stage.rate)
            continue
        try:
            moves = parse_moves(line)
        except ValueError as e:
            write("Not a move: %s. %s" % (e, "Type help for the words."))
            continue
        if moves is None:
            stage.result = stage.over = "quit"
            break
        for keys, n in moves:
            now = frozenset(keys)
            for i in range(n):
                pressed = sorted(now - held) if i == 0 else ()
                released = sorted(held - now) if i == 0 else ()
                stage.step(Controls(tick, now, pressed, released))
                held = now
                tick += 1
                if stage.result:
                    break
            if stage.result:
                break
    if stage.result in ("won", "lost"):
        for line in text_picture(stage):
            write(line)
        write({"won": "STAGE CLEAR. Score %d." % stage.score,
               "lost": "TIME UP." if stage.why == "time" else "GAME OVER."}[stage.result])
    stage.over = stage.result
    return stage.result


def play_scene(game, scene):
    """Play the stage of a CLIo scene, then go on with the story: the scene's (or the stage's) effects
    for a clear or a failure; a failure with none ends the game."""
    from . import conditions
    w, term, settings = game.world, game.term, game.settings
    sid = scene.get("stage")
    spec = game.data.stages.get(sid) or {}
    stage = make(game.data, sid)
    size_ok = True
    try:
        cols, rows = term.size()
        size_ok = cols >= 30 and rows >= 12
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
        play_frame(stage, term, game.audio)
    else:
        def read(prompt):
            try:
                return term.read(prompt)
            except Exception as e:
                if e.__class__.__name__ == "QuitGame":
                    return None
                raise
        play_text(stage, term.line, read)
    outcome = stage.result
    w.vars.setdefault("stages", {})[sid] = stage.stats()
    best = w.vars.setdefault("stage_best", {})
    if outcome == "won":
        w.flags["%s_cleared" % sid] = True
        best[sid] = max(best.get(sid, 0), stage.score)
        effects = scene.get("on_stage_clear") or spec.get("on_clear")
        if effects:
            conditions.run(effects, game)
        else:
            game.say("Stage clear. Score %d." % stage.score, "success")
    elif outcome == "lost":
        effects = scene.get("on_stage_fail") or spec.get("on_fail")
        if effects:
            conditions.run(effects, game)
        else:
            game.end_game("lose", spec.get("death_text") or "outro_lose")
    else:
        effects = scene.get("on_stage_quit")
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
def _num(v, lo=None, hi=None):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return (lo is None or v >= lo) and (hi is None or v <= hi)


def problems(data):
    """What is wrong with a game's stages (for --check)."""
    out = []
    stages = getattr(data, "stages", None) or {}
    cfg = settings_of(data)
    for k, v in (cfg.get("enemies") or {}).items():
        if not isinstance(v, dict):
            out.append("arcade enemy '%s' should be an object" % k)
        elif v.get("move") is not None and v["move"] not in MOVES:
            out.append("arcade enemy '%s': move should be one of %s" % (k, ", ".join(MOVES)))
    for sid, spec in stages.items():
        where = "stage '%s'" % sid
        if not isinstance(spec, dict):
            out.append("%s should be an object" % where)
            continue
        if spec.get("mode") is not None and spec["mode"] not in MODES:
            out.append("%s: mode should be platformer or topdown" % where)
        if spec.get("goal") is not None and spec["goal"] not in GOALS:
            out.append("%s: goal should be one of %s" % (where, ", ".join(GOALS)))
        for key, lo in (("lives", 1), ("health", 1), ("time", 1)):
            if spec.get(key) is not None and not _num(spec[key], lo):
                out.append("%s: %s should be a number, at least %d" % (where, key, lo))
        for k, v in (spec.get("physics") or {}).items():
            if k not in PHYSICS:
                out.append("%s: physics '%s' is not one of %s" % (where, k, ", ".join(PHYSICS)))
            elif not _num(v, 0.05, 100):
                out.append("%s: physics '%s' should be a number" % (where, k))
        rows = map_rows(spec)
        if not rows:
            out.append("%s: map should be a list of lines" % where)
            continue
        kinds = enemy_kinds(data, spec)
        legend = legend_of(kinds, spec)
        for ch, v in (spec.get("legend") or {}).items():
            name = v.get("enemy") or v.get("tile") or v.get("thing") if isinstance(v, dict) else v
            if name not in TILES and name not in THINGS and name not in kinds:
                out.append("%s: legend '%s' is '%s', not a tile, a thing or an enemy kind" % (where, ch, name))
        unknown = sorted({ch for r in rows for ch in r if ch not in legend})
        if unknown:
            out.append("%s: the map has characters nothing says the meaning of: %s" % (where, " ".join(unknown)))
        found = [legend.get(ch, ("empty", None)) for r in rows for ch in r]
        starts = sum(1 for t, th in found if th == "start")
        if starts != 1:
            out.append("%s: the map should have one start (@), not %d" % (where, starts))
        goal = spec.get("goal", "exit")
        if goal == "exit" and not any(t == "exit" for t, th in found):
            out.append("%s: the goal is the exit, and the map has none (E)" % where)
        if goal == "survive" and not spec.get("time"):
            out.append("%s: a survive goal needs a time" % where)
        if goal == "clear" and not any(isinstance(th, tuple) for t, th in found):
            out.append("%s: the goal is to clear it, and it has no enemies" % where)
        chips = sum(1 for t, th in found if th == "chip")
        need = spec.get("need")
        if need is not None and need != "all" and (not _num(need, 0) or need > chips):
            out.append("%s: need is %s chips, and the map has %d" % (where, need, chips))
        doors = sum(1 for t, th in found if t == "door")
        keys = sum(1 for t, th in found if th == "key")
        if doors > keys:
            out.append("%s: %d doors and only %d keys" % (where, doors, keys))
    for sid, sc in (getattr(data, "scenes", None) or {}).items():
        if sc.get("stage") and sc["stage"] not in stages:
            out.append("scene '%s': unknown stage '%s'" % (sid, sc["stage"]))
    return out
