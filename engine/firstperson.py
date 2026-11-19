# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""A first-person picture of a grid level, for frame mode.

The level is a grid of cells seen from the player's cell, facing north, east,
south or west.  Distance shrinks things to ``DECAY ** d`` of their size: not a
camera's true perspective, but steady and readable on a terminal.  Walls are
drawn far to near with their faces textured (small pictures made here), the
floor and ceiling are fixed to the world (so they slide by as one walks),
monsters, items and fire are pictures standing in their cells, and the gun is
at the bottom.

The picture is made of small pixels: two to a character in the ``pixel``
style (half blocks), eight in the braille styles (``dots``: one colour to a
character, the dots carry the brightness; ``dots-fill``: dots over a second
colour).

What is drawn comes from a level (see :mod:`engine.level`) through a few
attributes: ``cells`` (``cell(x, y)``), ``player``, ``monsters``, ``items``,
``shots``, ``decals``, ``marks`` (cells marked on the floor) and ``sprites``
(name -> :class:`Picture`).  What an animation frame changes comes in an
:class:`FX`.
"""
from __future__ import annotations

import math

from .frame import mix, shade, lum

DECAY = 0.64                 # apparent size falls to 64% with each cell of distance
FAR = 7                      # cells drawn ahead
REF_H, REF_W = 18, 12        # the yardstick: a sprite this big is a person's size
DIRS = ((0, -1), (1, 0), (0, 1), (-1, 0))          # north, east, south, west
STYLES = {"pixel": (1, 2), "dots": (2, 4), "dots-fill": (2, 4)}
BRAILLE_BIT = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))     # [row][column]
BAYER_2X4 = ((0, 4), (6, 2), (1, 5), (7, 3))
LN = math.log(DECAY)


def noise(i, j, k):
    """A steady pseudo-random number in [0, 1) for a pixel."""
    h = (i * 374761393 + j * 668265263 + k * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0


def _avg(cols):
    n = len(cols)
    return (sum(c[0] for c in cols) // n, sum(c[1] for c in cols) // n, sum(c[2] for c in cols) // n)


# --------------------------------------------------------------------------- #
# pictures
# --------------------------------------------------------------------------- #
class Picture:
    """A sprite as rows of colours (None is clear), with smaller versions for distance."""

    def __init__(self, rows, lods=()):
        self.rows = rows
        self.h, self.w = len(rows), max((len(r) for r in rows), default=0)
        self.lods = sorted(lods, key=lambda p: p.h)

    def pick(self, height):
        """The drawing to scale to ``height`` pixels: the smallest that is not much smaller."""
        for p in self.lods:
            if p.h >= height * 0.92:
                return p
        return self

    @classmethod
    def from_data(cls, data, palette_rgb, far=None):
        """From sprite data (``pixels``, ``lod``) and a palette already turned into colours."""
        def rows_of(pixels):
            return [[palette_rgb.get(ch) for ch in row] for row in pixels]
        lods = [cls(rows_of(d["pixels"] if isinstance(d, dict) else d)) for d in (data.get("lod") or far or [])]
        return cls(rows_of(data.get("pixels") or []), [p for p in lods if p.h and p.w])


# --------------------------------------------------------------------------- #
# wall textures: small pictures made once
# --------------------------------------------------------------------------- #
TS = 32
STEEL, SEAM, BAND, HILITE, RIVET, KICK = (58, 62, 72), (30, 32, 38), (40, 42, 50), (78, 82, 94), (110, 114, 126), (48, 51, 60)
KEY_COLOURS = {"r": (210, 60, 50), "w": (225, 190, 50), "x": (70, 125, 240)}


def _blank(c):
    return [[c] * TS for _ in range(TS)]


def _steel():
    t = _blank(STEEL)
    for y in range(TS):
        for x in range(TS):
            c = STEEL
            if x in (0, TS - 1) or y in (0, TS - 1):
                c = SEAM
            elif x == 16:
                c = SEAM
            elif 10 <= y <= 11:
                c = BAND
            elif y == 12:
                c = HILITE
            elif y >= 26:
                c = KICK
            elif noise(x, y, 7) < 0.04:
                c = shade(STEEL, 0.9)
            t[y][x] = c
    for x, y in ((3, 3), (12, 3), (20, 3), (28, 3), (3, 28), (28, 28)):
        t[y][x] = RIVET
    return t


def _screens(seed=1):
    t = _blank((40, 42, 48))
    for y in range(TS):
        t[y][0] = t[y][TS - 1] = SEAM
    for y in range(4, 22):
        for x in range(3, 29):
            t[y][x] = (10, 22, 16)
    for i, y in enumerate((6, 9, 12, 15, 18)):
        n = 6 + int(noise(i, seed, 3) * 18)
        for x in range(5, min(27, 5 + n)):
            if noise(x, y, seed) < 0.82:
                t[y][x] = (70, 210, 120) if i % 2 == 0 else (40, 130, 75)
    t[18][5 + int(noise(9, seed, 4) * 14)] = (190, 255, 210)       # the cursor
    for y in (25, 27, 29):
        for x in range(6, 26):
            t[y][x] = SEAM
    return t


def _hazard():
    t = _steel()
    for y in range(24, TS - 1):
        for x in range(1, TS - 1):
            t[y][x] = (215, 175, 40) if ((x + y) // 4) % 2 else (34, 32, 30)
    return t


def _door(stripe=None, sealed=False):
    body, frame = (98, 88, 72), (64, 64, 72)
    t = _blank(body)
    for y in range(TS):
        for x in range(TS):
            c = body
            if x < 3 or x > TS - 4 or y < 2:
                c = frame
            elif x in (15, 16):
                c = (40, 36, 30)
            elif (y - 2) % 6 == 0:
                c = shade(body, 1.18)
            elif (y - 2) % 6 == 5:
                c = shade(body, 0.82)
            t[y][x] = c
    if stripe:
        for y in range(13, 18):
            for x in range(3, TS - 3):
                if x not in (15, 16):
                    t[y][x] = stripe
    if sealed:
        for i in range(3, TS - 3):
            for d in (-1, 0, 1):
                for x, y in ((i, i + d), (i, TS - 1 - i + d)):
                    if 2 <= y < TS and 3 <= x < TS - 3:
                        t[y][x] = (170, 30, 26)
    return t


def _exit(on=False):
    t = _hazard()
    for y in range(5, 22):
        for x in range(8, 24):
            t[y][x] = (28, 28, 32) if (x in (8, 23) or y in (5, 21)) else (44, 44, 50)
    light = (70, 230, 100) if on else (220, 50, 40)
    for y in range(7, 10):
        for x in range(11, 21):
            t[y][x] = light
    lever_top = 12 if on else 18
    for y in range(min(lever_top, 15), max(lever_top, 15) + 1):
        t[y][15] = t[y][16] = (170, 170, 180)
    for x in range(13, 19):
        t[lever_top][x] = (200, 60, 50)
    return t


def _fist_panel():
    t = _steel()
    x = 11.0
    for y in range(3, 29):
        x += (noise(y, 3, 11) - 0.45) * 1.6
        xi = int(x)
        if 1 <= xi < TS - 1:
            t[y][xi] = shade(STEEL, 0.78)
    return t


def _shoot_panel():
    t = _steel()
    for y in range(TS):
        for x in range(TS):
            d = math.hypot(x - 15.5, y - 17.5)
            if d < 6:
                t[y][x] = (24, 24, 28) if int(d) % 2 == 0 else (90, 94, 104)
    return t


def _make_textures():
    out = {"steel": _steel(), "screens": _screens(1), "screens2": _screens(2), "hazard": _hazard(),
           "door": _door(), "sealed": _door(sealed=True), "exit": _exit(False), "exit_on": _exit(True),
           "fist": _fist_panel(), "shoot": _shoot_panel()}
    for k, c in KEY_COLOURS.items():
        out["door_" + k] = _door(stripe=c)
    return out


TEXTURES = _make_textures()
TILE_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def tile_frames(data):
    """A game's tile (tiles.json: ``pixels``, ``palette``, ``frames`` - the sprites' format, any size) as
    drawings of colours, one for each frame; ``None`` is clear (what is behind the wall shows through)."""
    from .sprite import _rgb
    pal = {k: _rgb(v) for k, v in (data.get("palette") or {}).items()}
    out = []
    for drawing in [data.get("pixels") or []] + list(data.get("frames") or []):
        rows = [[pal.get(ch) for ch in r] for r in drawing if isinstance(r, str)]
        w = max((len(r) for r in rows), default=0)
        if rows and w:
            out.append([r + [None] * (w - len(r)) for r in rows])
    return out


def tile_data(name):
    """One of the engine's own tiles as tiles.json data (letters and a palette), or None: to draw over."""
    rows = TEXTURES.get(name)
    if rows is None:
        return None
    letters, pixels = {}, []
    for r in rows:
        line = ""
        for c in r:
            if c not in letters:
                if len(letters) < len(TILE_LETTERS):
                    letters[c] = TILE_LETTERS[len(letters)]
                else:                                    # more colours than letters: the nearest one already named
                    near = min(letters, key=lambda k: sum((a - b) ** 2 for a, b in zip(k, c)))
                    letters[c] = letters[near]
            line += letters[c]
        pixels.append(line)
    palette = {}
    for c, ch in letters.items():
        palette.setdefault(ch, "#%02x%02x%02x" % tuple(c))
    return {"pixels": pixels, "palette": palette}

FLOOR_A, FLOOR_B, FLOOR_LINE = (68, 61, 53), (58, 53, 47), (94, 86, 72)
CEIL, CEIL_LINE, LIGHT = (30, 30, 36), (24, 24, 29), (168, 162, 122)
TOXIC, TOXIC_HI = (36, 140, 54), (130, 240, 110)


class FX:
    """What one animation frame changes in the picture of the level as it is."""

    def __init__(self, **kw):
        self.cam = None          # (x, y) between cells while walking
        self.pos = {}            # monster id -> (x, y) while it walks
        self.flash = ()          # monster ids drawn white
        self.tint = {}           # id -> colour
        self.dissolve = {}       # id -> 0..1 of its pixels gone
        self.texts = []          # (monster, text, role, rise)
        self.booms = []          # (x, y, phase 0..1)
        self.shots = None        # [(x, y)] in place of the shots' own places
        self.doors = {}          # (x, y) -> how open, 0..1
        self.hurt = 0.0
        self.hurt_dir = None     # "left", "right", "back": where the hurt came from, out of sight
        self.shake = 0
        self.recoil = 0
        self.muzzle = False
        self.emuzzle = ()
        self.lunge = {}
        self.fade = 0.0
        self.whiten = 0.0
        self.rise = {}           # id -> how far it has risen out of sight (an escape)
        self.parts = ()          # small things flying: (x, y, height, colour, size) - see Bits
        self.casing = 0.0        # a spent case thrown from the gun, 0..1 of its flight
        self.crates = {}         # (x, y) of a crate's cell -> (x, y) where it is drawn while it slides
        self.lift_items = {}     # an Item -> how high it bounces as it falls
        self.style = None        # draw this frame in another style (a teleport's dots)
        self.face = None         # the way the picture looks, in place of the player's (a teleport)
        self.__dict__.update(kw)


class Bits:
    """Small things flying for the frames of an animation - debris, gibs, sparks, drops - in the level's
    own units (cells across, a person's height up). Cheap: a few dozen points, gravity and a bounce."""

    def __init__(self, rng):
        self.rng, self.p = rng, []

    def burst(self, x, y, h, colours, n=16, speed=1.6, up=1.6, size=1.0, toward=(0.0, 0.0)):
        rng = self.rng
        for _ in range(n):
            ang = rng.uniform(0, 2 * math.pi)
            sp = speed * rng.uniform(0.25, 1.0)
            self.p.append([x, y, h, math.cos(ang) * sp + toward[0], math.sin(ang) * sp + toward[1],
                           up * rng.uniform(0.4, 1.3), rng.choice(colours), size * rng.uniform(0.6, 1.3)])
        return self

    def frames(self, n, dt=0.05, gravity=5.0):
        out = []
        for _ in range(n):
            for q in self.p:
                q[0] += q[3] * dt
                q[1] += q[4] * dt
                q[5] -= gravity * dt
                q[2] += q[5] * dt
                if q[2] < 0:                                   # the floor: a bounce, slower each time
                    q[2], q[5], q[3], q[4] = 0.0, -q[5] * 0.3, q[3] * 0.55, q[4] * 0.55
            out.append([(q[0], q[1], q[2], q[6], q[7]) for q in self.p])
        return out


def _crate_picture():
    wood, dark, band, bolt = (122, 92, 58), (80, 58, 36), (70, 74, 82), (150, 154, 160)
    rows = []
    for y in range(13):
        row = []
        for x in range(14):
            c = wood
            if y in (0, 12) or x in (0, 13):
                c = band
            elif y in (1, 11) or x in (1, 12):
                c = dark
            elif x == y or x == 13 - y:
                c = dark
            elif y % 4 == 2:
                c = shade(wood, 0.86)
            if (x, y) in ((1, 1), (12, 1), (1, 11), (12, 11)):
                c = bolt
            row.append(c)
        rows.append(row)
    return Picture(rows)


CRATE = _crate_picture()


def vslide(old, new, k, down, gap=3):
    """Cells of a lift's ride half done: the old view slides away, the shaft goes by, the new one comes."""
    H = len(old or new or [])
    if not H:
        return new
    W = len((old or new)[0])
    dark = lambda i: [(" ", None, (14, 14, 18) if i % 3 else (60, 58, 50))] * W     # noqa: E731
    shaft = [dark(i) for i in range(gap)]
    if new is None:                                           # down into the dark: the shaft goes on
        new = [dark(i + 1) for i in range(H)]
    if old is None:
        old = [dark(i + 1) for i in range(H)]
    strip = (old + shaft + new) if down else (new + shaft + old)
    n = int(round(max(0.0, min(1.0, k)) * (H + gap)))
    return strip[n:n + H] if down else strip[H + gap - n: 2 * H + gap - n]


class View:
    """The picture of a level from the player's place, ``W`` x ``VR`` characters."""

    def __init__(self, W, VR, style="pixel"):
        self.style = style if style in STYLES else "pixel"
        self.sx, self.sy = STYLES[self.style]
        self.W, self.VR = W, VR
        self.PW, self.PH = W * self.sx, VR * self.sy
        self.yh = round(self.PH * 0.40)                       # the horizon, in pixel rows
        self.FS = self.PH - self.yh                           # floor height on screen at distance 0
        self.CH = self.FS * 0.92                              # ceiling height
        self.LW = self.sx * max(W * 0.40, min(30.0, W * 0.6))  # a cell's width on screen at distance 0
        self.K = min(self.FS * 1.45 / REF_H, self.LW * 1.25 / REF_W)
        self.cache = {}
        self.cover = {}
        self.half = self.PW / 2.0

    # ---- projection ----------------------------------------------------- #
    def X(self, a, z):
        return self.half + a * self.LW * DECAY ** z

    @staticmethod
    def texture(lv, name, phase=0):
        """The drawing of a tile: the game's own (tiles.json, a frame a beat), else the engine's."""
        frames = (getattr(lv, "tiles", None) or {}).get(name)
        if not frames:
            return TEXTURES.get(name) or TEXTURES["steel"]
        return frames[phase % len(frames)]

    # ---- the room ------------------------------------------------------- #
    def backdrop(self, lv, cx, cy, f, phase):
        key = (round(cx, 3), round(cy, 3), f, phase, lv.marks_version)
        rows = self.cache.get(key)
        if rows is None:
            if len(self.cache) > 40:
                self.cache.clear()
            rows = self.cache[key] = self._backdrop(lv, cx, cy, f, phase)
        return [r[:] for r in rows]

    def _backdrop(self, lv, cx, cy, f, phase):
        fx, fy = DIRS[f]
        rx, ry = DIRS[(f + 1) % 4]
        PW, PH = self.PW, self.PH
        floor_tile, ceiling_tile = getattr(lv, "floor_tile", None), getattr(lv, "ceiling_tile", None)
        drawings = {}

        def sample(name, ux, uy):                            # a floor or ceiling tile, fixed to the world
            tex = drawings.get(name)
            if tex is None:
                tex = drawings[name] = self.texture(lv, name, phase)
            th, tw = len(tex), len(tex[0])
            return tex[min(th - 1, int((uy + 0.5) * th))][min(tw - 1, int((ux + 0.5) * tw))]

        out = []
        for y in range(PH):
            if y >= self.yh:
                t, floor = (y - self.yh + 0.5) / self.FS, True
            else:
                t, floor = (self.yh - y - 0.5) / self.CH, False
            z = math.log(t) / LN
            fog = 0.18 + 0.82 * min(1.0, t) ** 0.75
            span = self.LW * t
            row = [None] * PW
            for x in range(PW):
                a = (x + 0.5 - self.half) / span
                wx, wy = cx + fx * z + rx * a, cy + fy * z + ry * a
                ix, iy = int(math.floor(wx + 0.5)), int(math.floor(wy + 0.5))
                ux, uy = wx - ix, wy - iy
                cell = lv.cell(ix, iy)
                if floor:
                    mark = lv.marks.get((ix, iy))
                    tile = None
                    if cell is not None:
                        tile = getattr(cell, "floor", None) or (None if cell.toxic else floor_tile)
                    c = sample(tile, ux, uy) if tile else None
                    if c is None and cell is not None:
                        c = self.fixture(cell, ux, uy, phase)
                    if c is None and cell is not None and cell.toxic:
                        c = TOXIC_HI if noise(int(ux * 8) + ix * 8, int(uy * 8) + iy * 8, phase) < 0.07 else TOXIC
                        row[x] = shade(c, 0.45 + 0.55 * fog)
                        continue
                    if c is None:
                        c = FLOOR_A if (ix + iy) & 1 else FLOOR_B
                        if abs(ux) > 0.46 or abs(uy) > 0.46:
                            c = FLOOR_LINE
                    if mark == "warn":                   # fire is scheduled here: hatched and glowing
                        hatch = int((ux + uy + 1.0) * 6) % 2 == 0
                        c = mix(c, (255, 90, 30) if hatch else (150, 30, 20), 0.55 + 0.2 * (phase % 2))
                        row[x] = shade(c, 0.6 + 0.4 * fog)
                        continue
                    elif mark == "burn":
                        k = noise(int(ux * 10) + ix * 10, int(uy * 10) + iy * 10, phase + 5)
                        c = (255, 230, 120) if k < 0.25 else (255, 140, 40) if k < 0.7 else (200, 50, 20)
                        row[x] = c
                        continue
                    row[x] = shade(c, fog)
                else:
                    tile = (getattr(cell, "ceiling", None) if cell is not None else None) or ceiling_tile
                    c = sample(tile, ux, uy) if tile else None
                    if c is None:
                        c = CEIL
                        if abs(ux) > 0.47 or abs(uy) > 0.47:
                            c = CEIL_LINE
                        elif (ix * 7 + iy * 3) % 4 == 0 and abs(ux) < 0.24 and abs(uy) < 0.24:
                            c = LIGHT
                    row[x] = shade(c, fog)
            out.append(row)
        return out

    @staticmethod
    def fixture(cell, ux, uy, phase):
        """What is set in a floor: a pressure plate, a crate sunk in acid, a teleporter's pad, a lift."""
        m = max(abs(ux), abs(uy))
        if getattr(cell, "plate", None):
            if m < 0.34:
                c = (150, 128, 70) if not cell.down else (96, 82, 46)
                return shade(c, 1.15) if m > 0.3 and not cell.down else c
            return (34, 32, 30) if m < 0.38 else None
        if getattr(cell, "sunk", False):
            return (104, 78, 50) if int((uy + 0.5) * 6) % 2 else (88, 64, 40)
        if getattr(cell, "teleport", None):
            d = math.hypot(ux, uy)
            if d < 0.44:
                ring = int(d * 14 - phase) % 3
                return ((90, 40, 160), (60, 200, 230), (20, 16, 40))[ring]
            return None
        if getattr(cell, "lift", None):
            if m > 0.42:
                return (215, 175, 40) if int((ux + uy + 2) * 8) % 2 else (34, 32, 30)
            return (70, 74, 84) if int((ux + 0.5) * 8) % 4 else (52, 55, 62)
        return None

    # ---- drawing helpers ------------------------------------------------ #
    def blit(self, px, rows, x0, y0, s, fn=None, dist=None):
        nh, nw = len(rows), len(rows[0]) if rows else 0
        if not nh or not nw:
            return 0, 0
        sw, sh = max(1, int(round(nw * s))), max(1, int(round(nh * s)))
        for j in range(sh):
            yy = y0 + j
            if not 0 <= yy < self.PH:
                continue
            src, row = rows[min(nh - 1, int(j / s))], px[yy]
            for i in range(sw):
                xx = x0 + i
                if not 0 <= xx < self.PW:
                    continue
                c = src[min(nw - 1, int(i / s))]
                if c is None:
                    continue
                if fn is not None:
                    c = fn(c, i, j)
                    if c is None:
                        continue
                row[xx] = c
                if dist is not None:
                    key = (yy // self.sy, xx // self.sx)
                    if dist < self.cover.get(key, 99.0):
                        self.cover[key] = dist
        return sw, sh

    def glow(self, px, cx, cy, r, colour, k):
        for yy in range(int(cy - r), int(cy + r) + 1):
            if not 0 <= yy < self.PH:
                continue
            for xx in range(int(cx - r), int(cx + r) + 1):
                if 0 <= xx < self.PW:
                    dd = math.hypot(xx - cx, yy - cy)
                    if dd < r:
                        px[yy][xx] = mix(px[yy][xx], colour, k * (1 - dd / r))

    def _mark_cover(self, x0, x1, y0, y1, dist):
        for yy in range(max(0, y0) // self.sy, (min(self.PH, y1) - 1) // self.sy + 1):
            for xx in range(max(0, x0) // self.sx, (min(self.PW, x1) - 1) // self.sx + 1):
                if dist < self.cover.get((yy, xx), 99.0):
                    self.cover[(yy, xx)] = dist

    # ---- walls ---------------------------------------------------------- #
    def front_face(self, px, a, z, tex, opened=0.0):
        zf = max(z - 0.5, -0.45)
        t = DECAY ** zf
        x0, x1 = self.half + (a - 0.5) * self.LW * t, self.half + (a + 0.5) * self.LW * t
        y0, y1 = self.yh - self.CH * t, self.yh + self.FS * t
        X0, X1 = max(0, int(math.ceil(x0 - 0.5))), min(self.PW, int(math.ceil(x1 - 0.5)))
        Y0, Y1 = max(0, int(math.ceil(y0 - 0.5))), min(self.PH, int(math.ceil(y1 - 0.5)))
        if opened:
            Y1 = min(Y1, int(y0 + (y1 - y0) * (1 - opened)))
        if X0 >= X1 or Y0 >= Y1:
            return
        fog = 0.18 + 0.82 * min(1.0, t) ** 0.75
        tw, th = x1 - x0, y1 - y0
        TH, TW = len(tex), len(tex[0])
        us = [min(TW - 1, int((x + 0.5 - x0) / tw * TW)) for x in range(X0, X1)]
        for y in range(Y0, Y1):
            v = (y + 0.5 - y0) / th + opened
            trow = tex[min(TH - 1, max(0, int(v * TH)))]
            row = px[y]
            for i, x in enumerate(range(X0, X1)):
                c = trow[us[i]]
                if c is not None:
                    row[x] = shade(c, fog)
        self._mark_cover(X0, X1, Y0, Y1, z - 0.5)
        return (x0 + x1) / 2, y0, y1, t

    def side_face(self, px, a, z, tex, opened=0.0):
        edge = a - 0.5 if a > 0 else a + 0.5          # the face turned towards the middle
        if abs(edge) < 1e-6:
            return
        zn, zf = max(z - 0.5, -0.45), z + 0.5
        if zn >= zf:
            return
        xa, xb = self.X(edge, zf), self.X(edge, zn)
        if z - 0.5 <= 0.0:
            # The face reaches the player: a wall beside him runs off the edge of the picture and hides
            # everything beyond it (a corridor's walls, a door's jambs), the texture going on behind him.
            xb = float(self.PW + 1) if edge > 0 else -1.0
        lo, hi = (xa, xb) if xa < xb else (xb, xa)
        X0, X1 = max(0, int(math.ceil(lo - 0.5))), min(self.PW, int(math.ceil(hi - 0.5)))
        span = edge * self.LW
        TH, TW = len(tex), len(tex[0])
        for x in range(X0, X1):
            t = (x + 0.5 - self.half) / span
            if t <= 0:
                continue
            zc = math.log(t) / LN
            v = zc - (z - 0.5)
            u = int(v * TW) % TW if v < 0 else min(TW - 1, int(v * TW))
            y0, y1 = self.yh - self.CH * t, self.yh + self.FS * t
            Y0, Y1 = max(0, int(math.ceil(y0 - 0.5))), min(self.PH, int(math.ceil(y1 - 0.5)))
            if opened:
                Y1 = min(Y1, int(y0 + (y1 - y0) * (1 - opened)))
            fog = (0.18 + 0.82 * min(1.0, t) ** 0.75) * 0.72
            th = y1 - y0
            for y in range(Y0, Y1):
                v = (y + 0.5 - y0) / th + opened
                c = tex[min(TH - 1, max(0, int(v * TH)))][u]
                if c is not None:
                    px[y][x] = shade(c, fog)
            self._mark_cover(x, x + 1, Y0, Y1, zc)

    # ---- one picture ---------------------------------------------------- #
    def render(self, lv, fx, phase=0):
        """Rows of cells ``(char, fg, bg)``; in the pixel style char None means two pixels."""
        W, PW, PH = self.W, self.PW, self.PH
        p = lv.player
        cx, cy = fx.cam if fx.cam is not None else (p.x, p.y)
        f = fx.face if fx.face is not None else p.facing
        fx_, fy_ = DIRS[f]
        rx, ry = DIRS[(f + 1) % 4]
        px = self.backdrop(lv, cx, cy, f, phase)
        self.cover = {}
        self.fireball = lv.sprites.get("fireball")
        labels, overlays = [], []

        def rel(x, y):
            dx, dy = x - cx, y - cy
            return dx * rx + dy * ry, dx * fx_ + dy * fy_

        items = []
        icx, icy = int(round(cx)), int(round(cy))
        for y in range(icy - FAR - 1, icy + FAR + 2):
            for x in range(icx - FAR - 1, icx + FAR + 2):
                cell = lv.cell(x, y)
                if cell is None or not cell.drawn_as_wall(fx.doors.get((x, y))):
                    continue
                a, z = rel(x, y)
                if z < -0.5 or z > FAR + 0.5:                 # a wall wholly behind the player is not seen
                    continue
                if abs(a) - 0.5 > (self.half / (self.LW * DECAY ** max(z - 0.5, -0.45))) + 0.5:
                    continue
                items.append((z, 0, -abs(a), "wall", (cell, a, x, y)))
        for x, y, pic in lv.decals:
            a, z = rel(x, y)
            if -0.3 < z <= FAR:
                items.append((z + 0.02, 1, 0, "decal", (a, pic)))
        for it in lv.items:
            if it.taken:
                continue
            a, z = rel(it.x, it.y)
            if -0.3 < z <= FAR:
                items.append((z, 2, 0, "item", (a, it)))
        for (x, y) in getattr(lv, "crate_cells", lambda: ())():
            cx_, cy_ = fx.crates.get((x, y), (x, y))
            a, z = rel(cx_, cy_)
            if -0.3 < z <= FAR + 0.5:
                items.append((z, 2, 0, "crate", a))
        for wx, wy, h, col, size in fx.parts:
            a, z = rel(wx, wy)
            if 0.12 < z <= FAR:
                items.append((z - 0.005, 6, 0, "part", (a, h, col, size)))
        for m in lv.monsters:
            if m.gone or (m.dead and m.id not in fx.dissolve):
                continue
            mx, my = fx.pos.get(m.id, (m.x, m.y))
            a, z = rel(mx, my)
            if -0.4 < z <= FAR + 0.5:
                items.append((z, 3, 0, "mob", (a, m)))
        shots = fx.shots if fx.shots is not None else [(s.x, s.y) for s in lv.shots]
        for sx_, sy_ in shots:
            a, z = rel(sx_, sy_)
            if -0.4 < z <= FAR:
                items.append((z, 4, 0, "shot", a))
        for bx, by, k in fx.booms:
            a, z = rel(bx, by)
            if -0.5 < z <= FAR:
                items.append((z - 0.01, 5, 0, "boom", (a, k)))
        items.sort(key=lambda it: (-it[0], it[1], it[2]))

        see_through = getattr(lv, "see_through", ())

        def solid(x, y):                                     # a face turned to this cell cannot be seen
            c = lv.cell(x, y)
            if c is None:
                return True
            if c.kind == "door":
                return fx.doors.get((x, y), c.open) <= 0.0 and c.texture() not in see_through
            return c.drawn_as_wall() and c.texture() not in see_through

        for z, _o, _a, kind, obj in items:
            if kind == "wall":
                cell, a, x, y = obj
                opened = fx.doors.get((x, y), cell.open if cell.kind == "door" else 0.0)
                tex = self.texture(lv, cell.texture(), phase)
                if cell.kind == "panel" and getattr(p, "goggles", 0):       # the goggles show what is hollow
                    tex = [[None if c is None else mix(c, (200, 110, 255), 0.55) for c in row] for row in tex]
                if abs(a) > 0.02:
                    k = 1 if a > 0 else -1
                    if not solid(x - k * rx, y - k * ry):
                        self.side_face(px, a, z, tex, opened)
                # the face towards the player, if it is in front of him and nothing stands before it
                if z - 0.5 > 0.0 and not solid(x - fx_, y - fy_):
                    hit = self.front_face(px, a, z, tex, opened)
                    if hit and cell.label and z <= 3.2 and not opened:
                        overlays.append((hit, cell.label, cell.label_role, z))
            elif kind == "decal":
                a, pic = obj
                t = DECAY ** z
                s = t * self.K * 0.9
                base = self.yh + self.FS * t
                fog = 0.4 + 0.6 * min(1.0, t * 1.6)
                pp = pic.pick(pic.h * s)
                s2 = pic.h * s / pp.h
                self.blit(px, pp.rows, int(round(self.X(a, z) - pp.w * s2 / 2)), int(round(base - pp.h * s2)), s2,
                          lambda c, i, j: shade(c, fog))
            elif kind == "item":
                a, it = obj
                self.draw_thing(px, lv.sprites.get(it.sprite), a, z, it.size, None, fx, labels=None,
                                lift=fx.lift_items.get(it, 0.0))
            elif kind == "crate":
                self.draw_thing(px, lv.sprites.get("crate") or CRATE, obj, z, 0.75, None, fx, labels=None)
            elif kind == "part":
                a, h, col, size = obj
                t = DECAY ** z
                r = max(1, int(round(size * t * self.K * 0.9)))
                x0 = int(self.X(a, z) - r / 2)
                y0 = int(self.yh + self.FS * t - h * REF_H * t * self.K - r / 2)
                for yy in range(max(0, y0), min(self.PH, y0 + r)):
                    row = px[yy]
                    for xx in range(max(0, x0), min(self.PW, x0 + r)):
                        row[xx] = col
            elif kind == "mob":
                a, m = obj
                self.draw_thing(px, lv.sprites.get(m.sprite), a, z, m.size, m, fx, labels)
            elif kind == "shot":
                t = DECAY ** z
                s = t * self.K * 0.9
                mid = self.yh + self.FS * t - REF_H * t * self.K * 0.55
                x = self.X(obj, z)
                fb = lv.sprites.get("fireball")
                self.glow(px, x, mid, 9 * s, (255, 120, 30), 0.45)
                if fb:
                    self.blit(px, fb.rows, int(round(x - fb.w * s / 2)), int(round(mid - fb.h * s / 2)), s)
            else:
                a, k = obj
                t = DECAY ** z
                self.boom(px, self.X(a, z), self.yh + self.FS * t - 7 * t * self.K, (4 + 19 * k) * t * self.K, k)
        self.weapon(px, lv, fx)
        if any(k < 0.2 for _x, _y, k in fx.booms):
            px = [[shade(c, 1.35) for c in row] for row in px]
        if lv.player.sudo:
            px = [[mix(c, (255 - int(lum(c)),) * 3, 0.85) for c in row] for row in px]
        if getattr(lv.player, "goggles", 0):
            px = [[c if c[2] > c[1] + 40 and c[0] > c[1] else (int(lum(c) * 0.35), min(255, int(lum(c) * 1.25) + 18),
                                                              int(lum(c) * 0.45)) for c in row] for row in px]
        if fx.hurt:
            self.vignette(px, fx.hurt, fx.hurt_dir)
        if fx.whiten:
            px = [[mix(c, (255, 255, 255), fx.whiten) for c in row] for row in px]
        if fx.fade:
            px = [[mix(c, (40, 0, 0), fx.fade) for c in row] for row in px]
        if fx.shake:
            s = fx.shake * self.sx
            black = (0, 0, 0)
            px = [([black] * s + row[:-s]) if s > 0 else (row[-s:] + [black] * -s) for row in px]
        over = self.place_labels(labels, overlays)
        return self.halves(px, over) if self.style == "pixel" else self.braille(px, over)

    def draw_thing(self, px, pic, a, z, size, m, fx, labels, lift=0.0):
        if pic is None:
            return
        t = DECAY ** z
        s = t * self.K * size * (fx.lunge.get(m.id, 1.0) if m is not None else 1.0)
        target_h = pic.h * s
        pp = pic.pick(target_h)
        s = target_h / pp.h
        sw, sh = int(round(pp.w * s)), int(round(pp.h * s))
        base = self.yh + self.FS * t
        lift = (m.float * REF_H * t * self.K) if m is not None else lift * REF_H * t * self.K
        if m is not None and fx.rise.get(m.id):
            lift += fx.rise[m.id] * self.PH
        x = self.X(a, z)
        x0, y0 = int(round(x - sw / 2)), int(round(base - sh - lift))
        for yy in range(int(base) - self.sy // 2, int(base) + 1):        # a shadow on the floor
            if 0 <= yy < self.PH:
                for xx in range(int(x - sw * 0.4), int(x + sw * 0.4) + 1):
                    if 0 <= xx < self.PW:
                        px[yy][xx] = shade(px[yy][xx], 0.6)
        fog = 0.5 + 0.5 * min(1.0, t * 1.6)
        if m is None:
            self.blit(px, pp.rows, x0, y0, s, lambda c, i, j: shade(c, fog), z)
            return
        flash = m.id in fx.flash
        tint = fx.tint.get(m.id)
        gone = fx.dissolve.get(m.id, 0.0)
        mid = m.id

        def fn(c, i, j):
            if gone and noise(int(i / max(s, 0.01)), int(j / max(s, 0.01)), mid) < gone:
                return None
            if flash:
                return (255, 255, 255)
            if tint:
                c = mix(c, tint, 0.6)
            return shade(c, fog)
        self.blit(px, pp.rows, x0, y0, s, fn, z)
        if m.intent == "windup" and not m.dead:                   # fire gathering in its hand
            fs = s * 0.8
            gx, gy = x0 + sw * 0.85, y0 - 2 * fs
            self.glow(px, gx, gy, 6 * fs + 1, (255, 140, 40), 0.55)
            if self.fireball is not None:
                fb = self.fireball
                self.blit(px, fb.rows, int(round(gx - fb.w * fs / 2)), int(round(gy - fb.h * fs / 2)), fs)
        if m.id in fx.emuzzle:
            self.glow(px, x0 + sw * 0.95, y0 + sh * 0.45, max(2.5 * self.sx, 4 * s), (255, 230, 120), 0.95)
        if labels is not None and not m.dead and m.seen:
            text, role = m.label()
            row = max(0, y0 // self.sy - 1)
            labels.append((row, int(round(x / self.sx - len(text) / 2)), text, role, z, m.targeted))
            for mm, txt, r, rise in fx.texts:
                if mm is m:
                    labels.append((max(0, row - 1 - rise // 2), int(round(x / self.sx - len(txt) / 2)), txt, r, z, False))

    def place_labels(self, labels, overlays):
        from .frame import ROLE
        over, taken = {}, set()
        for (cx, y0, y1, t), text, role, z in overlays:          # writing on doors and switches
            row = int((y0 + (y1 - y0) * 0.38) // self.sy)
            col = int(round(cx / self.sx - len(text) / 2))
            if any(self.cover.get((row, c), 99.0) < z - 0.6 for c in range(col, col + len(text))):
                continue
            for i, ch in enumerate(text):
                if 0 <= col + i < self.W and 0 <= row < self.VR:
                    over[(row, col + i)] = (ch, ROLE.get(role, role) if isinstance(role, str) else role, (20, 20, 22))
        for row, col, text, role, dist, sel in labels:
            while row > 0 and any((row, c) in taken for c in range(col - 1, col + len(text) + 1)):
                row -= 1
            if any(self.cover.get((row, c), 99.0) < dist - 0.3 for c in range(col, col + len(text))):
                continue
            colour = ROLE.get(role, role) if isinstance(role, str) else role
            for i, ch in enumerate(text):
                if 0 <= col + i < self.W and 0 <= row < self.VR:
                    over[(row, col + i)] = (ch, (12, 12, 12), colour) if sel else (ch, colour, None)
                    taken.add((row, col + i))
        return over

    def vignette(self, px, hurt, where):
        PW, PH = self.PW, self.PH
        for y in range(PH):
            row = px[y]
            ey = min(y, PH - 1 - y) / (PH * 0.25)
            if where == "back":
                ey = (PH - 1 - y) / (PH * 0.3)
            for x in range(PW):
                if where == "left":
                    e = min(1.0, x / (PW * 0.3))
                elif where == "right":
                    e = min(1.0, (PW - 1 - x) / (PW * 0.3))
                elif where == "back":
                    e = min(1.0, ey)
                else:
                    e = min(1.0, ey, min(x, PW - 1 - x) / (PW * 0.2))
                row[x] = mix(row[x], (190, 0, 0), min(1.0, hurt * (0.08 + 0.75 * (1 - e))))

    def boom(self, px, cx, cy, r, k):
        if k < 0.12:
            col = (255, 255, 225)
        elif k < 0.3:
            col = (255, 225, 100)
        elif k < 0.5:
            col = (255, 145, 40)
        elif k < 0.7:
            col = (200, 55, 20)
        else:
            col = (80, 70, 64)
        density = 1.0 if k < 0.5 else 0.95 - (k - 0.5) * 1.6
        seed = int(k * 100)
        for yy in range(int(cy - r), int(cy + r) + 1):
            if not 0 <= yy < self.PH:
                continue
            for xx in range(int(cx - r), int(cx + r) + 1):
                if not 0 <= xx < self.PW:
                    continue
                dd = math.hypot(xx - cx, yy - cy)
                if dd <= r and noise(xx // self.sx, yy // max(1, self.sy // 2), seed) < density * (1.25 - dd / r):
                    px[yy][xx] = col if dd < r * 0.55 else mix(col, (110, 35, 10), 0.45)

    def weapon(self, px, lv, fx):
        pic = lv.sprites.get(lv.weapon_sprite())
        if pic is None:
            return
        ws = max(1.0, self.PH * 0.32 / 11)
        sw, sh = pic.w * ws, pic.h * ws
        x0 = int(round(self.half - sw / 2)) + fx.shake * self.sx
        y0 = self.PH - int(round(sh)) + fx.recoil * self.sy
        if fx.muzzle:
            mb = lv.sprites.get("muzzle")
            self.glow(px, self.half, y0 - 2 * ws, 10 * ws, (255, 200, 90), 0.5)
            if mb:
                self.blit(px, mb.rows, int(round(self.half - mb.w * ws / 2)), y0 - int(round(mb.h * ws)) + 1, ws)
        if fx.casing:                          # a spent case, thrown up and to the right
            k = fx.casing
            cxp = self.half + sw * (0.25 + 0.9 * k)
            cyp = y0 + sh * 0.2 - (4.0 * k * (1 - k)) * sh * 0.9 + k * k * sh * 0.4
            colour = (200, 40, 30) if lv.weapons.get(lv.player.weapon, {}).get("ammo") == "shells" else (215, 170, 70)
            r = max(1, int(ws))
            for yy in range(int(cyp), int(cyp) + r + (r if colour[0] == 200 else 0)):
                for xx in range(int(cxp), int(cxp) + r):
                    if 0 <= yy < self.PH and 0 <= xx < self.PW:
                        px[yy][xx] = colour
        rows = pic.rows
        if y0 + sh < self.PH:                  # raised (a punch): the arm goes on below it, to the bottom
            rows = rows + [rows[-1]] * int(math.ceil((self.PH - y0 - sh) / ws))
        self.blit(px, rows, x0, y0, ws)

    # ---- pixels to characters ------------------------------------------ #
    def halves(self, px, over):
        cells = []
        for r in range(self.VR):
            top, bot = px[2 * r], px[2 * r + 1]
            out = []
            for x in range(self.W):
                o = over.get((r, x))
                if o:
                    out.append((o[0], o[1], o[2] or shade(mix(top[x], bot[x], 0.5), 0.45)))
                else:
                    out.append((None, top[x], bot[x]))
            cells.append(out)
        return cells

    def braille(self, px, over):
        fill = self.style == "dots-fill"
        cells = []
        for r in range(self.VR):
            four = px[4 * r: 4 * r + 4]
            out = []
            for c in range(self.W):
                x = 2 * c
                block = [(four[dy][x + dx], dy, dx) for dy in range(4) for dx in range(2)]
                o = over.get((r, c))
                if o:
                    bg = o[2] or (shade(_avg([b[0] for b in block]), 0.45) if fill else None)
                    out.append((o[0], o[1], bg))
                    continue
                if fill:
                    lums = [lum(b[0]) for b in block]
                    lo, hi = min(lums), max(lums)
                    if hi - lo < 9:
                        out.append((" ", None, _avg([b[0] for b in block])))
                        continue
                    mid = (lo + hi) / 2
                    bits, lit, dark = 0, [], []
                    for (colour, dy, dx), v in zip(block, lums):
                        if v > mid:
                            bits |= BRAILLE_BIT[dy][dx]
                            lit.append(colour)
                        else:
                            dark.append(colour)
                    out.append((chr(0x2800 + bits), _avg(lit), _avg(dark)))
                else:
                    bits, lit = 0, []
                    for colour, dy, dx in block:
                        v = min(1.0, (lum(colour) / 255.0) ** 1.15 * 2.1)
                        if v * 8 > BAYER_2X4[dy][dx] + 0.5:
                            bits |= BRAILLE_BIT[dy][dx]
                            lit.append(colour)
                    if not bits:
                        out.append((" ", None, None))
                        continue
                    mean = _avg(lit)
                    k = min(1.9, 215.0 / max(1, max(mean)))
                    out.append((chr(0x2800 + bits), shade(mean, k), None))
            cells.append(out)
        return cells


def slide(old, new, k, direction):
    """Cells of a turn half done: the new view comes in from the side turned to."""
    if not old or not new:
        return new
    W = len(new[0])
    n = max(0, min(W, int(round(W * k))))
    out = []
    for ro, rn in zip(old, new):
        if direction < 0:              # turning left: the new view enters from the left
            out.append(rn[W - n:] + ro[:W - n])
        else:
            out.append(ro[n:] + rn[:n])
    return out
