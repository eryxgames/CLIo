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
from array import array

from . import model as model_mod
from . import picture
from .picture import frame as picture_frame
from .frame import mix, shade, lum

DECAY = 0.64                 # apparent size falls to 64% with each cell of distance
FAR = 10                     # cells of walls drawn ahead (a wall further off is under a pixel high)
SIGHT = 7                    # cells of things drawn ahead - and seen, aimed at, shot at (the level's rules)
BACK = 4                     # cells behind the player whose walls still show at the edges of the picture
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


def recolour(px, fn):
    """Every pixel through ``fn`` - worked out once for each colour: a picture has a few hundred, not thousands."""
    done = {}
    out = []
    for row in px:
        new = []
        for c in row:
            v = done.get(c)
            if v is None:
                v = done[c] = fn(c)
            new.append(v)
        out.append(new)
    return out


def _goggled(c):
    """A colour through the TTY goggles: green, but for what is purple (the hollow walls)."""
    if c[2] > c[1] + 40 and c[0] > c[1]:
        return c
    v = lum(c)
    return int(v * 0.35), min(255, int(v * 1.25) + 18), int(v * 0.45)


# --------------------------------------------------------------------------- #
# the sky over open cells
# --------------------------------------------------------------------------- #
SKY = {"top": (14, 18, 36), "horizon": (150, 96, 80), "ridges": [{"color": (30, 30, 40), "height": 0.2, "seed": 3},
                                                                 {"color": (16, 17, 22), "height": 0.1, "seed": 9,
                                                                  "near": 1.0}]}


def _colour(v, default):
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return tuple(int(c) for c in v)
    if isinstance(v, str):
        from .sprite import _rgb
        try:
            return _rgb(v)
        except (ValueError, TypeError):
            return default
    return default


def _wave(t, n, seed):
    """Smooth noise round a circle: ``t`` in turns, ``n`` bumps a turn."""
    f = (t % 1.0) * n
    i = int(f)
    k = f - i
    k = k * k * (3 - 2 * k)
    a, b = noise(i % n, seed, 17), noise((i + 1) % n, seed, 17)
    return a + (b - a) * k


def sky_spec(spec):
    """A level's ``"sky"`` with its colours read and gaps filled."""
    spec = spec if isinstance(spec, dict) else {}
    out = {"top": _colour(spec.get("top"), SKY["top"]), "horizon": _colour(spec.get("horizon"), SKY["horizon"]),
           "stars": float(spec.get("stars", 0.0) or 0.0), "ridges": [], "sun": None, "clouds": None}
    for i, r in enumerate(spec.get("ridges", SKY["ridges"]) or []):
        if isinstance(r, dict):
            out["ridges"].append((_colour(r.get("color"), (24, 24, 30)), float(r.get("height", 0.15)),
                                  int(r.get("seed", i * 7 + 3)), float(r.get("near", 0.0)), float(r.get("rough", 0.5))))
    sun = spec.get("sun")
    if isinstance(sun, dict):
        out["sun"] = (float(sun.get("at", 0.0)), float(sun.get("height", 0.3)), float(sun.get("size", 0.1)),
                      _colour(sun.get("color"), (240, 220, 180)), float(sun.get("glow", 0.5)),
                      _colour(sun.get("bands"), None) if sun.get("bands") else None)
    cl = spec.get("clouds")
    if isinstance(cl, dict):
        out["clouds"] = (_colour(cl.get("color"), (60, 50, 70)), float(cl.get("amount", 0.4)))
    return out


def _sun_on(c, u, e, sun, PW, yh):
    """A sky pixel with the sun or planet on it (as in sky_picture's loop)."""
    at, sh, size, scol, glow, bands = sun
    du = ((u - at + 0.5) % 1.0 - 0.5) * 4 * PW
    dv = (e - sh) * yh
    r = size * yh
    d = math.hypot(du, dv)
    if d < r:
        lit = 0.55 + 0.45 * max(0.0, min(1.0, 0.5 + (du + dv) / (2.5 * r)))
        sc = scol
        if bands is not None and int((dv / r + 1) * 4.5 + 0.3 * math.sin(du / r * 3)) % 2:
            sc = mix(scol, bands, 0.6)
        return shade(sc, lit)
    if glow and d < r * 3.5:
        return mix(c, scol, glow * (1 - (d - r) / (2.5 * r)) ** 2)
    return c


def sky_picture(sky, PW, yh, f, lateral, phase):
    """The sky above the horizon, ``yh`` rows of ``PW`` pixels, looking ``f`` (a quarter turn is the picture's
    width): a gradient, a sun or a planet, clouds that drift, stars, and ridges - the near ones move a little
    as the player moves sideways."""
    rows = []
    top, hor = sky["top"], sky["horizon"]
    if picture.load() is not None:                     # in C with CLIo Picture; the sun's pixels finished here
        base = [mix(hor, top, min(1.0, ((yh - y - 0.5) / float(yh)) ** 0.55)) for y in range(yh)]
        tint = [mix(col, hor, 0.3 * (1 - near)) for col, height, seed, near, rough in sky["ridges"]]
        fast = picture.sky(sky, PW, yh, f, lateral, phase, base, tint)
        if fast is not None:
            rows, heights, spots = fast
            ridges = list(zip(tint, heights))
            sun = sky["sun"]
            for p in spots:
                y, x = divmod(p, PW)
                c = _sun_on(rows[y][x], (f + (x + 0.5) / PW - 0.5) / 4.0, (yh - y - 0.5) / float(yh), sun, PW, yh)
                for rc, hs in ridges:
                    if (yh - y - 0.5) < hs[x]:
                        c = rc
                rows[y][x] = c
            return rows
    sun, clouds, stars = sky["sun"], sky["clouds"], sky["stars"]
    ridges = []                                        # each ridge's height in rows, per column
    for col, height, seed, near, rough in sky["ridges"]:
        shift = -lateral * near * 0.006
        hs = []
        for x in range(PW):
            u = (f + (x + 0.5) / PW - 0.5) / 4.0 + shift
            h = 0.55 * _wave(u, 9, seed) + 0.3 * _wave(u, 23, seed + 1) + 0.15 * rough * _wave(u, 61, seed + 2)
            hs.append(h * height * yh)
        ridges.append((mix(col, hor, 0.3 * (1 - near)), hs))
    for y in range(yh):
        e = (yh - y - 0.5) / float(yh)                   # 0 at the horizon, 1 at the top
        base = mix(hor, top, min(1.0, e ** 0.55))
        row = []
        for x in range(PW):
            c = base
            u = (f + (x + 0.5) / PW - 0.5) / 4.0
            if stars and e > 0.3 and noise(int(u * 4 * PW), y, 41) < stars:
                c = mix(c, (230, 230, 255), 0.5 + 0.4 * noise(int(u * 4 * PW), y, phase + 5))
            if clouds and 0.18 < e < 0.85:
                k = _wave(u * 3 + phase * 0.004, 7, 31) * _wave(u * 5 - phase * 0.003 + e * 0.7, 13, 37)
                band = 1 - abs(e - 0.45) * 2.2
                if k * band > 1 - clouds[1]:
                    c = mix(c, clouds[0], min(0.8, (k * band - (1 - clouds[1])) * 3))
            if sun is not None:
                at, sh, size, scol, glow, bands = sun
                du = ((u - at + 0.5) % 1.0 - 0.5) * 4 * PW
                dv = (e - sh) * yh
                r = size * yh
                d = math.hypot(du, dv)
                if d < r:                                # the disc: lit from one side, banded if a planet
                    lit = 0.55 + 0.45 * max(0.0, min(1.0, 0.5 + (du + dv) / (2.5 * r)))
                    sc = scol
                    if bands is not None and int((dv / r + 1) * 4.5 + 0.3 * math.sin(du / r * 3)) % 2:
                        sc = mix(scol, bands, 0.6)
                    c = shade(sc, lit)
                elif glow and d < r * 3.5:
                    c = mix(c, scol, glow * (1 - (d - r) / (2.5 * r)) ** 2)
            for rc, hs in ridges:
                if (yh - y - 0.5) < hs[x]:
                    c = rc
            row.append(c)
        rows.append(row)
    return rows


def dot_level(l):
    """How lit a pixel of luminance ``l`` is in the dots style, 0..8: it shows where this is above its
    step of the 2 x 4 Bayer pattern (and a half)."""
    return min(1.0, (l / 255.0) ** 1.15 * 2.1) * 8


class _Tone:
    """How blit colours a picture's pixel: times ``fog`` indoors, into ``haze`` by ``k`` in open land; a monster's
    dissolving (``gone``), white ``flash`` and ``tint`` first. A function of (colour, i, j), and numbers the
    library can read."""
    __slots__ = ("fog", "haze", "k", "gone", "step", "mid", "flash", "tint")

    def __init__(self, fog, haze=None, k=0.0, gone=0.0, step=1.0, mid=0, flash=False, tint=None):
        self.fog, self.haze, self.k = fog, haze, k
        self.gone, self.step, self.mid, self.flash, self.tint = gone, step, mid, flash, tint

    def __call__(self, c, i, j):
        if self.gone and noise(int(i / self.step), int(j / self.step), self.mid) < self.gone:
            return None
        if self.flash:
            return (255, 255, 255)
        if self.tint:
            c = mix(c, self.tint, 0.6)
        return shade(c, self.fog) if self.haze is None else mix(c, self.haze, self.k)

    def struct(self):
        return picture_frame.tone(1 if self.haze is None else 2, self.fog, self.haze or (0, 0, 0), self.k, self.gone,
                                  self.step, self.mid, self.flash, self.tint)


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
        self.walk = []                # a monster's steps, shown while it moves
        self.attack = None            # shown while it takes aim and fires
        self.muzzle = None            # where its shots leave it, as fractions of its width and height

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


def _switch(on=False):
    """A control panel: a screen, two lamps and a lever - thrown, it is up and the lamps are green."""
    t = _steel()
    for y in range(4, 28):
        for x in range(6, 26):
            t[y][x] = (30, 32, 38) if (x in (6, 25) or y in (4, 27)) else (52, 56, 64)
    for y in range(6, 14):                              # the screen: bars of a readout
        for x in range(8, 24):
            lit = (x - 8) % 4 < 3 and (y - 6) > (6 - ((x * 5) % 7)) * (0.4 if on else 1.0)
            t[y][x] = ((60, 200, 120) if on else (210, 150, 40)) if lit else (12, 18, 16)
    for i, lx in enumerate((10, 20)):                   # the lamps
        c = (70, 230, 100) if on else ((230, 60, 40) if i == 0 else (90, 30, 26))
        for y in range(16, 19):
            for x in range(lx, lx + 3):
                t[y][x] = c
    top = 17 if on else 24                              # the lever: down is off
    for y in range(min(top, 21), max(top, 21) + 1):
        t[y][15] = t[y][16] = (170, 170, 180)
    for x in range(13, 19):
        t[top][x] = (230, 190, 60)
        t[min(26, top + 1)][x] = (150, 120, 40)
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


def _locker(stripe=None, opened=False):
    """A locker in the wall: a tall steel door with louvres and a handle - or, open, its dark inside and a shelf."""
    t = _steel()
    body, edge = (84, 92, 108), (40, 44, 52)
    for y in range(2, TS - 2):
        for x in range(5, TS - 5):
            t[y][x] = edge if (x in (5, TS - 6) or y in (2, TS - 3)) else body
    if opened:
        for y in range(3, TS - 3):
            for x in range(6, TS - 6):
                t[y][x] = (22, 22, 26) if y != 12 else (70, 74, 84)          # the inside, a shelf across it
        for y in range(3, TS - 3):                                            # the door, swung back against the frame
            t[y][6] = t[y][7] = (120, 128, 144)
        for x in (12, 20):
            t[5][x] = t[6][x] = (110, 112, 120)                               # hooks
        return t
    for y in (5, 7, 9, 11):                                                   # louvres
        for x in range(9, TS - 9):
            t[y][x] = (34, 38, 46)
            t[y + 1][x] = (112, 120, 136)
    for y in range(15, 20):                                                   # the handle
        t[y][TS - 9] = t[y][TS - 10] = (180, 184, 196)
    for y in range(22, 26):                                                   # a name plate
        for x in range(10, 20):
            t[y][x] = (150, 140, 110)
    if stripe:
        for y in range(13, 15):
            for x in range(6, TS - 6):
                t[y][x] = stripe
    return t


def _gate(stripe=None):
    """Bars: a door seen through (its gaps are clear)."""
    t = [[None] * TS for _ in range(TS)]
    bar, lit, dark = (112, 116, 128), (168, 172, 184), (50, 52, 60)
    for y in range(TS):
        for x in range(TS):
            if y < 2 or x < 2 or x > TS - 3:
                t[y][x] = dark                                                # the frame
            elif (x - 2) % 5 in (2, 3):
                t[y][x] = lit if (x - 2) % 5 == 2 else bar                    # a bar, lit on its left
            elif y in (6, 7, 24, 25):
                t[y][x] = stripe or bar                                       # the cross bars
    return t


def _field():
    """A force field: glowing lines between two posts, clear between them."""
    t = [[None] * TS for _ in range(TS)]
    for y in range(TS):
        for x in range(TS):
            if x < 2 or x > TS - 3:
                t[y][x] = (44, 48, 58) if y % 6 else (120, 210, 255)          # the emitter posts
            elif y % 5 == 0 and noise(x, y, 5) < 0.8:
                t[y][x] = (90, 200, 255) if noise(x, y, 9) < 0.7 else (200, 240, 255)
    return t


def _timed_door():
    """A door with a hazard band and a clock lamp: it shuts again on its own."""
    t = _door()
    for y in range(13, 18):
        for x in range(3, TS - 3):
            if x not in (15, 16):
                t[y][x] = (215, 175, 40) if ((x + y) // 3) % 2 else (34, 32, 30)
    for y in range(5, 9):
        for x in range(13, 19):
            t[y][x] = (40, 40, 44) if (x in (13, 18) or y in (5, 8)) else (230, 120, 40)
    return t


def _oneway_door():
    """A door with chevrons: it opens from one side only."""
    t = _door()
    for y in range(12, 20):
        for x in range(3, TS - 3):
            if x in (15, 16):
                continue
            if (x - 3 + abs(y - 15.5)) % 8 < 2:
                t[y][x] = (235, 235, 225)
    return t


def _make_textures():
    out = {"steel": _steel(), "screens": _screens(1), "screens2": _screens(2), "hazard": _hazard(),
           "door": _door(), "sealed": _door(sealed=True), "exit": _exit(False), "exit_on": _exit(True),
           "fist": _fist_panel(), "shoot": _shoot_panel(), "switch": _switch(False), "switch_on": _switch(True)}
    for k, c in KEY_COLOURS.items():
        out["door_" + k] = _door(stripe=c)
    out.update({"locker": _locker(), "locker_open": _locker(opened=True), "bars": _gate(), "field": _field(),
                "door_timed": _timed_door(), "door_oneway": _oneway_door()})
    for k, c in KEY_COLOURS.items():
        out["locker_" + k] = _locker(stripe=c)
        out["bars_" + k] = _gate(stripe=c)
    return out


CLEAR_TEXTURES = None            # the engine's tiles that are seen through (worked out once)


def clear_textures():
    global CLEAR_TEXTURES
    if CLEAR_TEXTURES is None:
        CLEAR_TEXTURES = frozenset(n for n, rows in TEXTURES.items() if any(c is None for r in rows for c in r))
    return CLEAR_TEXTURES


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
            if c is None:                                # clear: a letter the palette does not have
                line += "."
                continue
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
HAZE = (16, 16, 20)
AUTO_LOW = 40000             # pixels in a picture above which "auto" detail draws the floor and ceiling at half width


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
        self.missiles = ()       # things flying: (x, y, height, sprite name, glow colour or None) - a rocket, a grenade
        self.tick = 0.0          # how far into the beat the animation is (0..1): spinning parts turn by it
        self.eye = None          # how high the eye is (of a wall's height), in place of the player's: a lift-off
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


def _supply_picture(opened=False):
    """A supply crate: olive, a stencilled band, a lid - or, opened, the lid off and its dark inside showing."""
    olive, dark, band, stencil = (92, 102, 60), (58, 64, 38), (70, 74, 82), (220, 190, 70)
    rows = []
    for y in range(13):
        row = []
        for x in range(14):
            c = olive
            if y in (0, 12) or x in (0, 13):
                c = band
            elif y in (1, 11) or x in (1, 12):
                c = dark
            elif 5 <= y <= 7 and 3 <= x <= 10:
                c = stencil if (x + y) % 3 else dark
            row.append(c)
        rows.append(row)
    if opened:
        for y in range(0, 4):
            for x in range(1, 13):
                rows[y][x] = (24, 24, 20) if y > 0 else (40, 40, 34)
        rows[0] = [None] * 14                                    # the lid is off: the top edge is gone
    return Picture(rows)


SUPPLY, SUPPLY_OPEN = _supply_picture(), _supply_picture(True)


def _flames():
    """Three drawings of a flame, a frame a redraw: yellow at the root, orange, red at the tips."""
    out = []
    for f in range(3):
        rows = []
        H, W = 12, 9
        for y in range(H):
            row = []
            up = (H - 1 - y) / float(H - 1)                    # 0 at the root, 1 at the tip
            half = 4.2 * (1 - up) ** 0.8 + 0.6
            lean = 0.9 * math.sin(f * 2.1 + up * 3.0) * up
            for x in range(W):
                d = abs(x - 4 - lean)
                if d > half or (up > 0.75 and noise(x, y, f) < 0.45):
                    row.append(None)
                    continue
                core = d < half * 0.45 and up < 0.55
                c = (255, 244, 180) if core and up < 0.3 else (255, 206, 80) if core else \
                    (255, 128, 30) if up < 0.7 else (210, 52, 20)
                row.append(c)
            rows.append(row)
        out.append(Picture(rows))
    return out


FLAMES = _flames()


def _normal(p0, p1, p2):
    """A world triangle's outward normal (the model-to-world turn is a mirror, so the cross is turned round)."""
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
    return _unit3((-(uy * vz - uz * vy), -(uz * vx - ux * vz), -(ux * vy - uy * vx)))


def _unit3(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return v[0] / n, v[1] / n, v[2] / n


def _drawn(rows, palette):
    return Picture([[palette.get(ch) for ch in row] for row in rows])


MINE_SEEN = 3                # cells off a mine is seen from (twice that in the goggles)
UNDERWATER = (14, 58, 66)    # the colour things take under water, and how far they take it
UNDERWATER_K = 0.5

# a grenade on the floor or in the air, and a rocket seen flying away (a game's sprites "grenade" and "rocket"
# come before these)
GRENADE = _drawn([".kk..", ".kKg.", "gGggg", "gGgGg", "ggggg", ".ggg."],
                 {"k": (60, 62, 68), "K": (150, 154, 160), "g": (84, 96, 52), "G": (128, 140, 82)})
ROCKET = _drawn([".ww.", "wWWw", "wWWw", ".ff.", ".FF."],
                {"w": (120, 124, 130), "W": (190, 194, 200), "f": (255, 230, 140), "F": (255, 140, 40)})


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

    def __init__(self, W, VR, style="pixel", detail="high"):
        self.style = style if style in STYLES else "pixel"
        self.sx, self.sy = STYLES[self.style]
        self.W, self.VR = W, VR
        self.PW, self.PH = W * self.sx, VR * self.sy
        if detail == "auto":                                  # a big picture's floor at half width: half the work
            detail = "low" if self.PW * self.PH > AUTO_LOW else "high"
        self.detail = "low" if detail == "low" else "high"
        self.yh = round(self.PH * 0.40)                       # the horizon, in pixel rows
        self.FS = self.PH - self.yh                           # floor height on screen at distance 0
        self.CH = self.FS * 0.92                              # ceiling height
        self.TALL = self.FS + self.CH                         # a wall's height on screen at distance 0
        self.EYE0 = self.FS / self.TALL                       # the eye's height, standing (of a wall's height)
        self.LW = self.sx * max(W * 0.40, min(30.0, W * 0.6))  # a cell's width on screen at distance 0
        self.K = min(self.FS * 1.45 / REF_H, self.LW * 1.25 / REF_W)
        self.cache = {}
        self.skies = {}
        self.cover = {}
        self.persp = None                                     # open land: a true perspective from this far behind
        self.air = None                                       # open land: (haze colour, how far half is haze)
        self.cur_z = -1e9                                     # how far off what is being drawn now is (open land)
        self.half = self.PW / 2.0

    def set_eye(self, eye):
        """The eye ``eye`` high (of a wall's height): more floor below the horizon, less wall above it -
        a machine flying sees from higher up. None: standing."""
        eye = self.EYE0 if eye is None else max(0.2, min(0.95, float(eye)))
        self.set_eye_abs(eye)

    def set_eye_abs(self, eye):
        """The eye ``eye`` above the floor things stand on (in open land: above the pad, so any height)."""
        self.FS, self.CH = self.TALL * eye, self.TALL * (1 - eye)
        self.EYE = eye

    @staticmethod
    def eye_of(lv):
        """How high the player's eye is above the ground: a flying machine's ``"eye"`` (0.74) once it is up -
        in open land its ``"altitude"`` (the land's, 2.6) - with a little sway; on the jetpack the level's
        jet eye; swimming, just over the water (under it, diving). None: standing."""
        p = lv.player
        v = getattr(p, "vehicle", None)
        spec = getattr(v, "vehicle", None) or {}
        if getattr(p, "jet_on", False) and hasattr(lv, "jet_eye"):
            return lv.jet_eye() + 0.02 * math.sin(lv.beat * 2.3)
        if (v is None and getattr(p, "diving", False)) or (spec.get("swim") and getattr(v, "dived", False)):
            return 0.24 + 0.01 * math.sin(lv.beat * 1.3)
        if (v is None and hasattr(lv, "swimming") and lv.swimming()) or spec.get("swim"):
            return 0.31 + 0.015 * math.sin(lv.beat * 1.9)
        if v is None or not spec.get("fly") or not getattr(v, "started", False):
            return None
        land = getattr(lv, "land", None)
        up = float(spec.get("altitude", land.altitude)) if land is not None else float(spec.get("eye", 0.74))
        return up + 0.012 * math.sin(lv.beat * 1.7) * (4 if land is not None else 1)

    def tz(self, z):
        """How big a thing ``z`` cells ahead is, against one beside the player: the rooms' exponential distance,
        or in open land a true perspective from ``persp`` cells behind him."""
        if self.persp is None:
            return DECAY ** z
        return self.persp / max(0.05, z + self.persp)

    def zt(self, t):
        """The distance at which things are ``t`` as big (the other way round from ``tz``)."""
        if self.persp is None:
            return math.log(t) / LN
        return self.persp / t - self.persp

    # ---- projection ----------------------------------------------------- #
    def X(self, a, z):
        return self.half + a * self.LW * self.tz(z)

    @staticmethod
    def texture(lv, name, phase=0):
        """The drawing of a tile: the game's own (tiles.json, a frame a beat), else the engine's."""
        frames = (getattr(lv, "tiles", None) or {}).get(name)
        if not frames:
            return TEXTURES.get(name) or TEXTURES["steel"]
        return frames[phase % len(frames)]

    # ---- the room ------------------------------------------------------- #
    def backdrop(self, lv, cx, cy, f, phase):
        key = (id(lv), round(cx, 3), round(cy, 3), f, phase, lv.marks_version, round(self.FS, 2),
               getattr(getattr(lv, "player", None), "diving", False))
        rows = self.cache.get(key)
        if rows is None:
            if len(self.cache) > 40:
                self.cache.clear()
            rows = self.cache[key] = self._backdrop(lv, cx, cy, f, phase)
        return [r[:] for r in rows]

    def sky_rows(self, lv, cx, cy, f, phase):
        """The sky's rows for this facing and beat (None: the level has no sky)."""
        look = getattr(lv, "sky_look", None)
        if look is None:
            return None
        rx, ry = DIRS[(f + 1) % 4]
        lateral = round((cx * rx + cy * ry) * 4) / 4.0
        key = (f, lateral, phase, id(look))
        sky = self.skies.get(key)
        if sky is None:
            if len(self.skies) > 16:
                self.skies.clear()
            sky = self.skies[key] = sky_picture(look, self.PW, self.yh, f, lateral, phase)
        return sky

    def backdrop_frame(self, frame, lv, cx, cy, f, phase):
        """``backdrop`` into CLIo Picture's frame (0.4): its rows, or None when the library cannot draw it."""
        key = ("frame", id(lv), round(cx, 3), round(cy, 3), f, phase, lv.marks_version, round(self.FS, 2))
        px = frame.start(False)
        got = self.cache.get(key)
        if got is not None:
            frame.put_bytes(got)
        else:
            if not self._backdrop(lv, cx, cy, f, phase, frame):
                return None
            if len(self.cache) > 40:
                self.cache.clear()
            self.cache[key] = bytes(frame.rgb)
        self.cover = frame.cover_view
        return px

    def _backdrop(self, lv, cx, cy, f, phase, frame=None):
        """The floor and ceiling, per pixel.  The hot loop of a frame: what depends only on a cell is
        worked out once per cell, and a colour in a row's fog once per row."""
        fx, fy = DIRS[f]
        rx, ry = DIRS[(f + 1) % 4]
        PW, PH, half = self.PW, self.PH, self.half
        floor_tile, ceiling_tile = getattr(lv, "floor_tile", None), getattr(lv, "ceiling_tile", None)
        fires = getattr(lv, "fires", None) or ()
        marks, cell_at, fixture, floor_ = lv.marks, lv.cell, self.fixture, math.floor
        drawings, below, above = {}, {}, {}
        sky = self.sky_rows(lv, cx, cy, f, phase)
        step = 2 if self.detail == "low" else 1                # low: every other pixel, each drawn twice

        def drawing(name):                                   # a floor or ceiling tile, fixed to the world
            tex = drawings.get(name)
            if tex is None:
                tex = drawings[name] = self.texture(lv, name, phase)
            return tex

        tiles = getattr(lv, "tiles", None) or {}
        wet = getattr(getattr(lv, "player", None), "diving", False) and "seabed" in tiles   # under water

        def under(ix, iy):                                   # how a cell's floor is drawn
            cell = cell_at(ix, iy)
            if cell is None:
                return None, None, False, False, False, marks.get((ix, iy))
            tile = getattr(cell, "floor", None) or (None if cell.toxic else floor_tile)
            if wet and getattr(cell, "deep", False):         # under water: the bottom, not the surface
                tile = "seabed"
            fixed = bool(getattr(cell, "plate", None) or getattr(cell, "sunk", False) or getattr(cell, "teleport", None)
                         or getattr(cell, "lift", None) or getattr(cell, "conveyor", None) is not None
                         or getattr(cell, "oil", False) or getattr(cell, "slick", False)
                         or getattr(cell, "scorched", False))
            return (cell, drawing(tile) if tile else None, fixed, cell.toxic, (ix, iy) in fires,
                    marks.get((ix, iy)))

        if picture.load() is not None:                    # in C with CLIo Picture; teleporters' rings here
            fast = self._backdrop_c(lv, cx, cy, f, phase, sky, step, under, drawing, ceiling_tile, below, frame)
            if fast is not None or frame is not None:
                return fast
            below.clear()
        out = []
        for y in range(PH):
            if y >= self.yh:
                t, floor = (y - self.yh + 0.5) / self.FS, True
            else:
                t, floor = (self.yh - y - 0.5) / self.CH, False
            z = math.log(t) / LN
            if z > FAR + 0.5:                                # beyond the walls drawn: the dark far away
                out.append([HAZE] * PW)
                continue
            fog = 0.18 + 0.82 * min(1.0, t) ** 0.75
            span = self.LW * t
            bx, by = cx + fx * z, cy + fy * z
            fogged, acid = {}, {}                            # colours in this row's fog
            row = [None] * PW
            lx = ly = None                                   # the cell of the pixel before: most pixels share it
            for x in range(0, PW, step):
                a = (x + 0.5 * step - half) / span
                wx, wy = bx + rx * a, by + ry * a
                ix, iy = int(floor_(wx + 0.5)), int(floor_(wy + 0.5))
                ux, uy = wx - ix, wy - iy
                if floor:
                    if ix != lx or iy != ly:
                        lx, ly = ix, iy
                        info = below.get((ix, iy))
                        if info is None:
                            info = below[(ix, iy)] = under(ix, iy)
                        cell, tex, fixed, toxic, fire, mark = info
                    c = None
                    if tex is not None:
                        th, tw = len(tex), len(tex[0])
                        c = tex[min(th - 1, int((uy + 0.5) * th))][min(tw - 1, int((ux + 0.5) * tw))]
                    if c is None and fixed:
                        c = fixture(cell, ux, uy, phase)
                    if c is None and toxic:
                        c = TOXIC_HI if noise(int(ux * 8) + ix * 8, int(uy * 8) + iy * 8, phase) < 0.07 else TOXIC
                        v = acid.get(c)
                        if v is None:
                            v = acid[c] = shade(c, 0.45 + 0.55 * fog)
                        row[x] = v
                        continue
                    if c is None:
                        c = FLOOR_A if (ix + iy) & 1 else FLOOR_B
                        if abs(ux) > 0.46 or abs(uy) > 0.46:
                            c = FLOOR_LINE
                    if fire:
                        c = mix(c, (255, 120, 30), 0.3 + 0.25 * noise(int(ux * 6) + ix * 6, int(uy * 6) + iy * 6, phase))
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
                else:
                    if ix != lx or iy != ly:
                        lx, ly = ix, iy
                        tex = above.get((ix, iy), 0)
                        if tex == 0:
                            cell = cell_at(ix, iy)
                            if sky is not None and getattr(cell, "sky", False):
                                tex = above[(ix, iy)] = "sky"
                            else:
                                tile = ("surface" if wet and getattr(cell, "deep", False) and "surface" in tiles else
                                        (getattr(cell, "ceiling", None) if cell is not None else None)) or ceiling_tile
                                tex = above[(ix, iy)] = drawing(tile) if tile else None
                    if tex == "sky":
                        row[x] = sky[y][x]
                        continue
                    c = None
                    if tex is not None:
                        th, tw = len(tex), len(tex[0])
                        c = tex[min(th - 1, int((uy + 0.5) * th))][min(tw - 1, int((ux + 0.5) * tw))]
                    if c is None:
                        c = CEIL
                        if abs(ux) > 0.47 or abs(uy) > 0.47:
                            c = CEIL_LINE
                        elif (ix * 7 + iy * 3) % 4 == 0 and abs(ux) < 0.24 and abs(uy) < 0.24:
                            c = LIGHT
                v = fogged.get(c)
                if v is None:
                    v = fogged[c] = shade(c, fog)
                row[x] = v
            if step == 2:
                row[1::2] = row[0:PW - 1:2]
            out.append(row)
        return out

    def _rows(self):
        """For each pixel row of the backdrop: (0 floor, 1 ceiling, 2 too far), the distance, the fog, a cell's
        width - as _backdrop works them out."""
        key = (self.PH, self.yh, self.FS, self.CH, self.LW)
        got = self.__dict__.get("_rows_c")
        if got is None or got[0] != key:
            kinds, zs, fogs, spans = array("b"), array("d"), array("d"), array("d")
            for y in range(self.PH):
                if y >= self.yh:
                    t, kind = (y - self.yh + 0.5) / self.FS, 0
                else:
                    t, kind = (self.yh - y - 0.5) / self.CH, 1
                z = math.log(t) / LN
                if z > FAR + 0.5:
                    kind = 2
                kinds.append(kind)
                zs.append(z)
                fogs.append(0.18 + 0.82 * min(1.0, t) ** 0.75)
                spans.append(self.LW * t)
            got = self._rows_c = (key, (kinds, zs, fogs, spans))
        return got[1]

    def _backdrop_c(self, lv, cx, cy, f, phase, sky, step, under, drawing, ceiling_tile, below, frame=None):
        """_backdrop with CLIo Picture: the cells' floors and ceilings worked out here as there, in the same
        order; None when the library cannot draw it."""
        fx, fy = DIRS[f]
        rx, ry = DIRS[(f + 1) % 4]
        PW, PH = self.PW, self.PH
        cell_at = lv.cell
        tiles = getattr(lv, "tiles", None) or {}
        wet = getattr(getattr(lv, "player", None), "diving", False) and "seabed" in tiles
        held = []

        def info(what, ix, iy):
            if what == 0:
                got = below[(ix, iy)] = under(ix, iy)
                cell, tex, fixed, toxic, fire, mark = got
                kind = belt = 0
                if fixed:
                    if getattr(cell, "plate", None):
                        kind = 2 if cell.down else 1
                    elif getattr(cell, "sunk", False):
                        kind = 3
                    elif getattr(cell, "teleport", None):
                        kind = 4
                    elif getattr(cell, "lift", None):
                        kind = 5
                    elif getattr(cell, "conveyor", None) is not None:
                        kind, belt = 6, cell.conveyor
                        if not isinstance(belt, int) or not 0 <= belt < 4:
                            raise picture.Odd("a belt's way")
                    elif getattr(cell, "oil", False):
                        kind = 7
                    elif getattr(cell, "slick", False):
                        kind = 8
                    elif getattr(cell, "scorched", False):
                        kind = 9
                x, y = (cell.x, cell.y) if kind in (7, 9) else (ix, iy)
                return (tex, kind, belt, 1 if toxic else 0, 1 if fire else 0,
                        1 if mark == "warn" else 2 if mark == "burn" else 0, x, y)
            cell = cell_at(ix, iy)
            if sky is not None and getattr(cell, "sky", False):
                return None, 10, 0, 0, 0, 0, ix, iy
            tile = ("surface" if wet and getattr(cell, "deep", False) and "surface" in tiles else
                    (getattr(cell, "ceiling", None) if cell is not None else None)) or ceiling_tile
            return drawing(tile) if tile else None, 0, 0, 0, 0, 0, ix, iy

        rows = self._rows()
        got = picture.room(PW, PH, self.yh, step, self.half, (cx, cy, fx, fy, rx, ry), phase, rows, sky, info,
                           held, None if frame is None else frame.rgb)
        if got is None:
            return None
        out, later = got
        if frame is not None:
            out = frame.rows
        kinds, zs, fogs, spans = rows
        half = self.half
        for p in later:                                  # a teleporter's rings, as _backdrop draws them
            y, x = divmod(p, PW)
            z, fog = zs[y], fogs[y]
            a = (x + 0.5 * step - half) / spans[y]
            wx, wy = cx + fx * z + rx * a, cy + fy * z + ry * a
            ix, iy = int(math.floor(wx + 0.5)), int(math.floor(wy + 0.5))
            ux, uy = wx - ix, wy - iy
            cell, tex, fixed, toxic, fire, mark = below[(ix, iy)]
            c = self.fixture(cell, ux, uy, phase)
            if c is None and toxic:
                v = shade(TOXIC_HI if noise(int(ux * 8) + ix * 8, int(uy * 8) + iy * 8, phase) < 0.07 else TOXIC,
                          0.45 + 0.55 * fog)
            else:
                if c is None:
                    c = FLOOR_A if (ix + iy) & 1 else FLOOR_B
                    if abs(ux) > 0.46 or abs(uy) > 0.46:
                        c = FLOOR_LINE
                if fire:
                    c = mix(c, (255, 120, 30), 0.3 + 0.25 * noise(int(ux * 6) + ix * 6, int(uy * 6) + iy * 6, phase))
                if mark == "warn":
                    hatch = int((ux + uy + 1.0) * 6) % 2 == 0
                    v = shade(mix(c, (255, 90, 30) if hatch else (150, 30, 20), 0.55 + 0.2 * (phase % 2)),
                              0.6 + 0.4 * fog)
                elif mark == "burn":
                    k = noise(int(ux * 10) + ix * 10, int(uy * 10) + iy * 10, phase + 5)
                    v = (255, 230, 120) if k < 0.25 else (255, 140, 40) if k < 0.7 else (200, 50, 20)
                else:
                    v = shade(c, fog)
            out[y][x] = v
            if step == 2 and x + 1 < PW:
                out[y][x + 1] = v
        return out if frame is None else True

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
        belt = getattr(cell, "conveyor", None)
        if belt is not None:
            dx, dy = DIRS[belt]
            along, across = ux * dx + uy * dy, ux * -dy + uy * dx
            if abs(across) > 0.4:
                return (60, 62, 68)
            chevron = (along * 3.0 - abs(across) * 2.0 - phase * 0.34) % 1.0
            return (214, 170, 44) if chevron < 0.3 else (42, 42, 46)
        if getattr(cell, "oil", False):
            sheen = noise(int((ux + 0.5) * 10) + cell.x * 10, int((uy + 0.5) * 10) + cell.y * 10, phase // 2)
            return (70, 56, 96) if sheen < 0.06 else (24, 22, 20) if sheen < 0.5 else (32, 28, 24)
        if getattr(cell, "slick", False):
            streak = int((ux - uy + 2) * 7) % 5 == 0                    # a film of coolant on the steel
            return (128, 160, 176) if streak else (62, 84, 98)
        if getattr(cell, "scorched", False):
            return (26, 24, 22) if noise(int(ux * 9) + cell.x * 9, int(uy * 9) + cell.y * 9, 1) < 0.6 else (44, 38, 34)
        return None

    # ---- drawing helpers ------------------------------------------------ #
    def blit(self, px, rows, x0, y0, s, fn=None, dist=None):
        nh, nw = len(rows), len(rows[0]) if rows else 0
        if not nh or not nw:
            return 0, 0
        sw, sh = max(1, int(round(nw * s))), max(1, int(round(nh * s)))
        fr = getattr(px, "frame", None)
        if fr is not None and s > 0 and (fn is None or isinstance(fn, _Tone)) and self._fits(rows):
            fr.blit(rows, x0, y0, s, sw, sh, None if fn is None else fn.struct(), dist)
            return sw, sh
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
    def dents(self, px, spots, fog, x_lo, x_hi):
        """Bullet holes: ``spots`` are (x, y, size) in pixels; only within the columns just drawn."""
        core = shade((20, 18, 17), max(0.5, fog))
        rim = shade((92, 90, 86), fog)
        for x, y, r in spots:
            x0, y0 = int(x - r / 2.0), int(y - r / 2.0)
            for yy in range(max(0, y0), min(self.PH, y0 + r)):
                row = px[yy]
                for xx in range(max(x_lo, x0), min(x_hi, x0 + r)):
                    row[xx] = core
            if r >= 2 and 0 <= y0 + r < self.PH and x_lo <= x0 + r - 1 < x_hi:
                px[y0 + r][x0 + r - 1] = rim             # the light catches the lower lip

    def front_face(self, px, a, z, tex, opened=0.0, holes=()):
        zf = max(z - 0.5, -0.45)
        t = self.tz(zf)
        self.cur_z = z - 0.5
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
        fr = getattr(px, "frame", None)
        if fr is not None and self._fits(tex):                # in CLIo Picture's frame
            fr.front(tex, X0, X1, Y0, Y1, x0, tw, y0, th, opened, fog, z - 0.5)
            if holes and not opened:
                r = max(1, int(round(th * 0.05)))
                self.dents(px, [(x0 + u * tw, y0 + h * th, r) for u, h in holes], fog, X0, X1)
            return (x0 + x1) / 2, y0, y1, t
        TH, TW = len(tex), len(tex[0])
        us = [min(TW - 1, int((x + 0.5 - x0) / tw * TW)) for x in range(X0, X1)]
        fogged = {}                                    # a texture's few colours, each in this face's fog once
        for y in range(Y0, Y1):
            v = (y + 0.5 - y0) / th + opened
            trow = tex[min(TH - 1, max(0, int(v * TH)))]
            row = px[y]
            for i, x in enumerate(range(X0, X1)):
                c = trow[us[i]]
                if c is not None:
                    s = fogged.get(c)
                    if s is None:
                        s = fogged[c] = shade(c, fog)
                    row[x] = s
        if holes and not opened:
            r = max(1, int(round(th * 0.05)))
            self.dents(px, [(x0 + u * tw, y0 + h * th, r) for u, h in holes], fog, X0, X1)
        self._mark_cover(X0, X1, Y0, Y1, z - 0.5)
        return (x0 + x1) / 2, y0, y1, t

    @staticmethod
    def _fits(rows):
        """A tile or picture the library takes: rows of one length, of (r, g, b) or None."""
        try:
            picture.texture(rows)
            return True
        except (picture.Odd, TypeError, ValueError, OverflowError, IndexError):
            return False

    def side_face(self, px, a, z, tex, opened=0.0, to_edge=False, holes=()):
        edge = a - 0.5 if a > 0 else a + 0.5          # the face turned towards the middle
        if abs(edge) < 1e-6:
            return
        # The face runs from z - 0.5 to z + 0.5. Beside and behind the player it is still drawn - this
        # picture widens with nearness, so walls behind him show at the edges, each with its own tile.
        # With ``to_edge`` it is the last of a wall that goes on past the player: it runs to the picture's
        # edge (its tile repeating), so that the room behind him does not show through at the side.
        zn, zf = z - 0.5, z + 0.5
        xa, xb = self.X(edge, zf), self.X(edge, zn)
        if to_edge:
            xb = float(self.PW + 1) if edge > 0 else -1.0
        lo, hi = (xa, xb) if xa < xb else (xb, xa)
        X0, X1 = max(0, int(math.ceil(lo - 0.5))), min(self.PW, int(math.ceil(hi - 0.5)))
        span = edge * self.LW
        fr = getattr(px, "frame", None)
        if fr is not None and self._fits(tex):                # in CLIo Picture's frame: the distances here
            xs, zcs, fogs = array("i"), array("d"), array("d")
            for x in range(X0, X1):
                t = (x + 0.5 - self.half) / span
                if t <= 0:
                    continue
                xs.append(x)
                zcs.append(self.zt(t))
                fogs.append((0.18 + 0.82 * min(1.0, t) ** 0.75) * 0.72)
            if xs:
                fr.side(tex, xs, zcs, fogs, self.half, span, self.yh, self.CH, self.FS, opened, z)
                self.cur_z = zcs[-1]
        else:
            fr = None
        TH, TW = len(tex), len(tex[0])
        for x in range(X0, X1) if fr is None else ():
            t = (x + 0.5 - self.half) / span
            if t <= 0:
                continue
            zc = self.zt(t)
            self.cur_z = zc
            v = zc - (z - 0.5)
            u = int(v * TW) % TW if v < 0 else min(TW - 1, int(v * TW))
            y0, y1 = self.yh - self.CH * t, self.yh + self.FS * t
            Y0, Y1 = max(0, int(math.ceil(y0 - 0.5))), min(self.PH, int(math.ceil(y1 - 0.5)))
            if opened:
                Y1 = min(Y1, int(y0 + (y1 - y0) * (1 - opened)))
            fog = (0.18 + 0.82 * min(1.0, t) ** 0.75) * 0.72
            th = y1 - y0
            fogged = {}
            for y in range(Y0, Y1):
                v = (y + 0.5 - y0) / th + opened
                c = tex[min(TH - 1, max(0, int(v * TH)))][u]
                if c is not None:
                    s = fogged.get(c)
                    if s is None:
                        s = fogged[c] = shade(c, fog)
                    px[y][x] = s
            self._mark_cover(x, x + 1, Y0, Y1, zc)
        if holes and not opened and X1 > X0:
            spots = []
            for v, h in holes:
                t = self.tz(z - 0.5 + v)
                y0, y1 = self.yh - self.CH * t, self.yh + self.FS * t
                spots.append((self.half + span * t, y0 + h * (y1 - y0), max(1, int(round((y1 - y0) * 0.05)))))
            self.dents(px, spots, (0.18 + 0.82 * min(1.0, self.tz(z)) ** 0.75) * 0.72, X0, X1)

    # ---- one picture ---------------------------------------------------- #
    def render(self, lv, fx, phase=0):
        """Rows of cells ``(char, fg, bg)``; in the pixel style char None means two pixels."""
        W, PW, PH = self.W, self.PW, self.PH
        p = lv.player
        cx, cy = fx.cam if fx.cam is not None else (p.x, p.y)
        f = fx.face if fx.face is not None else p.facing
        fx_, fy_ = DIRS[f]
        rx, ry = DIRS[(f + 1) % 4]
        cam = (cx, cy, fx_, fy_, rx, ry)
        land = getattr(lv, "land", None)
        self.cover = {}
        self.cur_z = -1e9
        frame = picture_frame.frame_for(self) if self.use_frame else None     # CLIo Picture 0.4: kept in C
        px = None
        if land is not None:                                  # open land: a true perspective, the ground drawn first
            self.persp = land.Z0 if hasattr(land, "Z0") else 1.6
            g = lv.ground(cx, cy)
            eye = fx.eye if fx.eye is not None else self.eye_of(lv)
            self.set_eye_abs(g + (self.EYE0 if eye is None else eye))
            land.look(getattr(lv, "sky_look", None))
            self.air = (land.haze, land.vis)                  # far things fade into the haze, as the land does
            sky = self.sky_rows(lv, cx, cy, f, phase) or []
            if frame is not None:
                px = land.draw_frame(self, frame, cam, self.EYE, phase, sky)
            if px is None:
                self.cover = {}
                px = land.draw(self, cam, self.EYE, phase, sky, (getattr(lv, "map_w", 0), getattr(lv, "map_h", 0)))
            sight, far = land.see, 40
        else:
            self.persp = self.air = None
            self.set_eye(fx.eye if fx.eye is not None else self.eye_of(lv))
            if frame is not None:
                px = self.backdrop_frame(frame, lv, cx, cy, f, phase)
            if px is None:
                self.cover = {}
                px = self.backdrop(lv, cx, cy, f, phase)
            sight, far = SIGHT, FAR

        def gnd(a, z):                                       # the ground under a point ahead (0 in rooms)
            if land is None:
                return 0.0
            return lv.ground(cx + rx * a + fx_ * z, cy + ry * a + fy_ * z)

        def foot(a, z, t):
            return self.yh + (self.FS - gnd(a, z) * self.TALL) * t
        self.fireball = lv.sprites.get("fireball")
        labels, overlays = [], []

        def rel(x, y):
            dx, dy = x - cx, y - cy
            return dx * rx + dy * ry, dx * fx_ + dy * fy_

        holes = {}
        for hx, hy, n, along, down in getattr(lv, "holes", ()):
            holes.setdefault((hx, hy), []).append((n, along, down))
        items = []
        icx, icy = int(round(cx)), int(round(cy))
        sub_a, sub_z = rel(icx, icy)                          # the camera between cells, while it moves
        if land is not None:                                  # open land: the walls are the map's, few and known
            near = [(x, y) for x, y in getattr(lv, "land_walls", ())]
        else:
            near = []
            for dz in range(-BACK, FAR + 2):                  # every cell that can show: the picture widens with distance
                reach = int(self.half / (self.LW * DECAY ** (dz + 0.5))) + 2
                near += [(icx + fx_ * dz + rx * da, icy + fy_ * dz + ry * da) for da in range(-reach, reach + 1)]
        for x, y in near:
            cell = lv.cell(x, y)
            if cell is None or not cell.drawn_as_wall(fx.doors.get((x, y))):
                continue
            a, z = rel(x, y)
            if z < -BACK - 0.5 or z > far + 0.5:
                continue
            edge = abs(a) - 0.5                               # its nearest side to the middle of the picture
            if edge > 0 and self.half + edge * self.LW * self.tz(z + 0.5) > self.PW + 1:
                continue                                      # wholly off the side of the picture
            if z < -0.5 and edge <= 0:                        # behind the player, with no side turned to him
                continue
            items.append((z, 0, -abs(a), "wall", (cell, a, x, y)))
        if land is not None:                                  # what grows on the land, and what stands far off
            for x, y, prop in land.props_near(cx, cy, land.props_view):
                a, z = rel(x, y)
                if 0.25 < z <= land.props_view and abs(a) < z * 1.6 + 1:
                    items.append((z, 2, 0, "prop", (a, x, y, prop)))
            for mark in land.marks:
                a, z = rel(*mark["at"][:2])
                if z > 0.3:
                    items.append((z, 2, 0, "landmark", (a, mark)))
        for x, y, pic in lv.decals:
            a, z = rel(x, y)
            if -0.3 < z <= sight:
                items.append((z + 0.02, 1, 0, "decal", (a, pic)))
        pl = getattr(lv, "player", None)
        for it in lv.items:
            if it.taken:
                continue
            if getattr(it, "mine", False) and pl is not None and \
                    max(abs(it.x - pl.x), abs(it.y - pl.y)) > (MINE_SEEN * 2 if getattr(pl, "nightvision", False) else MINE_SEEN):
                continue                                     # a mine is only seen close to (further in the goggles)
            a, z = rel(it.x, it.y)
            if -0.3 < z <= sight:
                items.append((z, 2, 0, "itemmodel" if it.model and it.model in getattr(lv, "models", {}) else "item",
                              (a, it)))
        for (x, y) in getattr(lv, "crate_cells", lambda: ())():
            cx_, cy_ = fx.crates.get((x, y), (x, y))
            a, z = rel(cx_, cy_)
            if -0.3 < z <= sight + 0.5:
                items.append((z, 2, 0, "crate", (a, lv.cell(x, y))))
        for (x, y), left in (getattr(lv, "fires", None) or {}).items():
            a, z = rel(x, y)
            if 0.1 < z <= sight + 0.5:
                items.append((z - 0.01, 3, 0, "flame", (a, x, y, left)))
                for k in range(3):                           # embers going up, in the redraw's own time
                    h = ((phase * 0.29 + k * 0.37 + x * 0.13 + y * 0.07) % 1.0) * 1.1
                    ea, ez = rel(x + (noise(x, y, k) - 0.5) * 0.6, y + (noise(y, x, k + 3) - 0.5) * 0.6)
                    if 0.12 < ez <= sight:
                        items.append((ez - 0.02, 6, 0, "part", (ea, h, (255, 190, 80) if k % 2 else (255, 120, 40), 0.5)))
        for wx, wy, h, col, size in fx.parts:
            a, z = rel(wx, wy)
            if 0.12 < z <= sight:
                items.append((z - 0.005, 6, 0, "part", (a, h, col, size)))
        for m in lv.monsters:
            if m.gone or (m.dead and m.id not in fx.dissolve):
                continue
            mx, my = fx.pos.get(m.id, (m.x, m.y))
            a, z = rel(mx, my)
            if -0.4 < z <= sight + 0.5:
                if m.model and m.model in getattr(lv, "models", {}):
                    items.append((z, 3, 0, "model", (a, m, mx, my)))
                else:
                    items.append((z, 3, 0, "mob", (a, m)))
        shots = fx.shots if fx.shots is not None else [(s.x, s.y) for s in lv.shots]
        for sx_, sy_ in shots:
            a, z = rel(sx_, sy_)
            if -0.4 < z <= sight:
                items.append((z, 4, 0, "shot", a))
        for bx, by, k in fx.booms:
            a, z = rel(bx, by)
            if -0.5 < z <= sight:
                items.append((z - 0.01, 5, 0, "boom", (a, k)))
        for mx, my, h, name, glow in fx.missiles:
            a, z = rel(mx, my)
            if 0.15 < z <= sight + 4:
                items.append((z, 4, 0, "missile", (a, h, name, glow)))
        for g in getattr(lv, "grenades", ()):
            a, z = rel(g.x, g.y)
            if -0.3 < z <= sight:
                items.append((z, 2, 0, "grenade", (a, g)))
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
            if land is not None:
                self.cur_z = z                                # the ground nearer than this hides it
            if kind == "wall":
                cell, a, x, y = obj
                opened = fx.doors.get((x, y), cell.open if cell.kind == "door" else 0.0)
                tex = self.texture(lv, cell.texture(), phase)
                if cell.kind == "panel" and getattr(p, "nightvision", False):       # the goggles show what is hollow
                    tex = [[None if c is None else mix(c, (200, 110, 255), 0.55) for c in row] for row in tex]
                if abs(a) > 0.02:
                    k = 1 if a > 0 else -1
                    if not solid(x - k * rx, y - k * ry):
                        last = False
                        if z - 0.5 <= 0.0:                      # it reaches the player: does the wall go on behind?
                            bx, by = x - fx_, y - fy_
                            behind = lv.cell(bx, by)
                            last = (z - 1 < -BACK or behind is None or not behind.drawn_as_wall(fx.doors.get((bx, by)))
                                    or solid(bx - k * rx, by - k * ry))
                        side = (f + 3) % 4 if k > 0 else (f + 1) % 4     # the way that face is turned
                        dot = DIRS[(side + 1) % 4][0] * fx_ + DIRS[(side + 1) % 4][1] * fy_
                        self.side_face(px, a, z, tex, opened, last,
                                       [(0.5 + along * dot, down) for n, along, down in holes.get((x, y), ()) if n == side])
                # the face towards the player, if it is in front of him and nothing stands before it
                if z - 0.5 > 0.0 and not solid(x - fx_, y - fy_):
                    front = (f + 2) % 4
                    dot = DIRS[(front + 1) % 4][0] * rx + DIRS[(front + 1) % 4][1] * ry
                    hit = self.front_face(px, a, z, tex, opened,
                                          [(0.5 + along * dot, down) for n, along, down in holes.get((x, y), ()) if n == front])
                    if hit and cell.label and z <= 3.2 and not opened:
                        overlays.append((hit, cell.label, cell.label_role, z))
            elif kind == "decal":
                a, pic = obj
                t = self.tz(z)
                s = t * self.K * 0.9
                base = foot(a, z, t)
                tone = self.toner(z, 0.4 + 0.6 * min(1.0, t * 1.6))
                pp = pic.pick(pic.h * s)
                s2 = pic.h * s / pp.h
                self.blit(px, pp.rows, int(round(self.X(a, z) - pp.w * s2 / 2)), int(round(base - pp.h * s2)), s2,
                          tone)
            elif kind == "model":
                a, m, mx, my = obj
                self.draw_monster_model(px, lv, m, a, z, mx, my, fx, labels, cam, phase)
            elif kind == "itemmodel":
                a, it = obj
                mdl = lv.models[it.model]
                t = phase + fx.tick
                self.draw_model(px, mdl, it.x, it.y, math.radians(mdl.turning * t), "idle", t, cam,
                                lift=fx.lift_items.get(it, 0.0) * 0.3 + gnd(a, z))
            elif kind == "item":
                a, it = obj
                self.draw_thing(px, lv.sprites.get(it.sprite), a, z, it.size, None, fx, labels=None,
                                lift=fx.lift_items.get(it, 0.0), ground=gnd(a, z))
                if getattr(it, "mine", False) and phase % 2 == 0:     # its light blinks
                    t = self.tz(z)
                    self.glow(px, self.X(a, z), foot(a, z, t) - 0.5 * REF_H * t * self.K * it.size,
                              max(1.2, 2.4 * t * self.K), (255, 40, 30), 0.8)
            elif kind == "prop":
                a, x, y, prop = obj
                mdl = (getattr(lv, "models", None) or {}).get(prop.get("model"))
                if mdl is not None:
                    self.draw_model(px, mdl, x, y, (x * 7 + y * 13) % 6.283, "idle", phase + fx.tick, cam,
                                    lift=gnd(a, z), size=float(prop.get("size", 1.0)))
                else:
                    pic = lv.sprites.get(prop.get("sprite"))
                    self.draw_thing(px, pic, a, z, float(prop.get("size", 0.8)), None, fx, labels=None, ground=gnd(a, z))
            elif kind == "landmark":
                a, mark = obj
                mx_, my_ = mark["at"][:2]
                mdl = (getattr(lv, "models", None) or {}).get(mark.get("model"))
                if mdl is not None:
                    self.draw_model(px, mdl, mx_, my_, math.radians(float(mark.get("turn", 0))), "idle", phase + fx.tick,
                                    cam, lift=lv.ground(mx_, my_) + float(mark.get("lift", 0)),
                                    size=float(mark.get("size", 1.0)))
                elif lv.sprites.get(mark.get("sprite")) is not None:
                    self.draw_thing(px, lv.sprites.get(mark.get("sprite")), a, z, float(mark.get("size", 2.0)), None, fx,
                                    labels=None, ground=lv.ground(mx_, my_) + float(mark.get("lift", 0)))
            elif kind == "crate":
                a, cc = obj
                heavy = getattr(cc, "heavy", False)
                if getattr(cc, "supply", None) is not None:                # a supply crate, shut or opened
                    pic = lv.sprites.get("supply_open" if cc.opened else "supply") or (SUPPLY_OPEN if cc.opened
                                                                                         else SUPPLY)
                else:
                    pic = (lv.sprites.get("container") if heavy else None) or lv.sprites.get("crate") or CRATE
                self.draw_thing(px, pic, a, z, 0.98 if heavy else 0.75, None, fx, labels=None, ground=gnd(a, z))
            elif kind == "grenade":
                a, g = obj
                self.draw_thing(px, lv.sprites.get("grenade") or GRENADE, a, z, 0.26, None, fx, labels=None,
                                ground=gnd(a, z))
                if (phase + g.fuse) % 2 == 0 or g.fuse <= 1:          # its light blinks; on the last beat, steady
                    t = self.tz(z)
                    self.glow(px, self.X(a, z), foot(a, z, t) - 0.2 * REF_H * t * self.K * 0.26 * 3,
                              max(1.5, 3.0 * t * self.K), (255, 40, 30), 0.85)
            elif kind == "missile":
                a, h, name, glow = obj
                t = self.tz(z)
                s = t * self.K * 0.9
                x = self.X(a, z)
                y = foot(a, z, t) - h * REF_H * t * self.K
                if glow:
                    self.glow(px, x, y, 7 * s + 1, glow, 0.6)
                pic = lv.sprites.get(name) or (GRENADE if name == "grenade" else ROCKET)
                self.blit(px, pic.rows, int(round(x - pic.w * s / 2)), int(round(y - pic.h * s / 2)), s)
            elif kind == "flame":
                a, x, y, left = obj
                pic = FLAMES[(phase + x * 7 + y * 3) % len(FLAMES)]
                self.draw_thing(px, lv.sprites.get("flame") or pic, a, z, 0.45 + min(0.3, 0.07 * left), None, fx, labels=None,
                                ground=gnd(a, z))
            elif kind == "part":
                a, h, col, size = obj
                t = self.tz(z)
                r = max(1, int(round(size * t * self.K * 0.9)))
                x0 = int(self.X(a, z) - r / 2)
                y0 = int(foot(a, z, t) - h * REF_H * t * self.K - r / 2)
                for yy in range(max(0, y0), min(self.PH, y0 + r)):
                    row = px[yy]
                    for xx in range(max(0, x0), min(self.PW, x0 + r)):
                        row[xx] = col
            elif kind == "mob":
                a, m = obj
                self.draw_thing(px, lv.sprites.get(m.sprite), a, z, m.size, m, fx, labels, ground=gnd(a, z))
            elif kind == "shot":
                t = self.tz(z)
                s = t * self.K * 0.9
                mid = foot(obj, z, t) - REF_H * t * self.K * 0.55
                x = self.X(obj, z)
                fb = lv.sprites.get("fireball")
                self.glow(px, x, mid, 9 * s, (255, 120, 30), 0.45)
                if fb:
                    self.blit(px, fb.rows, int(round(x - fb.w * s / 2)), int(round(mid - fb.h * s / 2)), s)
            else:
                a, k = obj
                t = self.tz(z)
                self.boom(px, self.X(a, z), foot(a, z, t) - 7 * t * self.K, (4 + 19 * k) * t * self.K, k)
        self.cur_z = -1e9                                     # what is in the hands is nearer than anything
        self.weapon(px, lv, fx)
        if any(k < 0.2 for _x, _y, k in fx.booms):
            px = self.recolour(px, 1, 1.35, None, lambda c: shade(c, 1.35))
        if lv.player.sudo:
            px = self.recolour(px, 2, 0.0, None, lambda c: mix(c, (255 - int(lum(c)),) * 3, 0.85))
        if getattr(lv.player, "nightvision", False):
            px = self.recolour(px, 3, 0.0, None, _goggled)
        if getattr(lv.player, "diving", False):            # under water: all of it through the water's green
            px = self.recolour(px, 4, UNDERWATER_K, UNDERWATER, lambda c: mix(c, UNDERWATER, UNDERWATER_K))
        if fx.hurt:
            fr = getattr(px, "frame", None)
            if fr is not None:
                fr.vignette(fx.hurt, fx.hurt_dir)
            else:
                self.vignette(px, fx.hurt, fx.hurt_dir)
        if fx.whiten:
            px = self.recolour(px, 4, fx.whiten, (255, 255, 255), lambda c: mix(c, (255, 255, 255), fx.whiten))
        if fx.fade:
            px = self.recolour(px, 4, fx.fade, (40, 0, 0), lambda c: mix(c, (40, 0, 0), fx.fade))
        if fx.shake:
            s = fx.shake * self.sx
            fr = getattr(px, "frame", None)
            if fr is not None and abs(s) < self.PW:
                fr.shake(s)
            else:
                if fr is not None:
                    px = fr.lists()
                black = (0, 0, 0)
                px = [([black] * s + row[:-s]) if s > 0 else (row[-s:] + [black] * -s) for row in px]
        over = self.place_labels(labels, overlays)
        fr = getattr(px, "frame", None)
        if fr is not None and self.style == "pixel":
            return fr.halves(over, shade, mix)
        return self.halves(px, over) if self.style == "pixel" else self.braille(px, over)

    use_frame = True                                          # CLIo Picture's frame when it has one (tests turn it off)

    def recolour(self, px, how, k, colour, fn):
        """The whole picture through ``fn``: in the library's frame by its number ``how`` (1 times k, 2 sudo,
        3 the goggles, 4 towards colour by k), else in Python."""
        fr = getattr(px, "frame", None)
        if fr is not None:
            fr.recolour(how, k, colour or (0, 0, 0))
            return px
        return recolour(px, fn)

    # ---- 3D models (engine/model.py) ---------------------------------------- #
    LIGHT = (-0.2, -0.72, 0.66)         # from the viewer's left and above (a little behind): back, left, up
    EYE = 0.52                          # the eye's height: the horizon's (the room is 1 high)

    def project(self, cam, x, y, h):
        """A point of the world (cells; h up from the floor) on the picture: (x, y, depth), or None behind."""
        cx, cy, fx_, fy_, rx, ry = cam
        dx, dy = x - cx, y - cy
        a, z = dx * rx + dy * ry, dx * fx_ + dy * fy_
        if z < 0.12:
            return None
        t = self.tz(z)
        return self.half + a * self.LW * t, self.yh + self.FS * t - h * (self.FS + self.CH) * t, z

    def draw_model(self, px, mdl, wx, wy, heading, clip, t, cam, lift=0.0, size=1.0, gone=0.0, seed=0,
                   flash=False, tint=None, roll=0.0):
        """A model standing at (wx, wy) facing ``heading`` (radians: 0 east, pi/2 south), posed for
        ``clip`` at time ``t``; ``gone`` (0..1): blown apart that far; ``roll``: turned forward about its
        middle that far (radians: a ball rolling). Returns its top and middle on the picture (y, x), or None
        if none of it showed."""
        verts = mdl.pose(clip, t)
        if roll:
            c, s, zc = math.cos(roll), math.sin(roll), mdl.height / 2.0
            verts = [(x, y * c + (z - zc) * s, zc - y * s + (z - zc) * c) for x, y, z in verts]
        if size != 1.0:
            verts = [(x * size, y * size, z * size) for x, y, z in verts]
        fxw, fyw = math.cos(heading), math.sin(heading)
        rxw, ryw = -fyw, fxw
        zc = (wx - cam[0]) * cam[2] + (wy - cam[1]) * cam[3]     # how far off it stands
        flat = max(0.0, min(1.0, 1.3 - zc))                      # close by, depth is the middle's: no bulging
        fr = getattr(px, "frame", None)
        if fr is not None and gone <= 0:                  # CLIo Picture 0.6: the mesh is kept there; only this
            lb, ll, lu = self.LIGHT
            got = picture.mesh_draw(fr, mdl, verts, wx, wy, fxw, fyw, lift, cam, self, flat, max(0.3, zc),
                                    _unit3((cam[2] * lb + cam[4] * ll, cam[3] * lb + cam[5] * ll, lu)), flash, tint,
                                    mdl.smooth)
            if got is not False:
                return got
        world = [(wx + x * rxw + y * fxw, wy + x * ryw + y * fyw, z + lift) for x, y, z in verts]
        if flat > 0 and gone <= 0:
            cx_, cy_, fx_, fy_, rx_, ry_ = cam
            zm = max(0.3, zc)

            def project(x, y, h):
                dx, dy = x - cx_, y - cy_
                a, z = dx * rx_ + dy * ry_, dx * fx_ + dy * fy_
                t = self.tz(zm + (max(z, 0.0) - zm) * (1 - flat))
                return self.half + a * self.LW * t, self.yh + self.FS * t - h * (self.FS + self.CH) * t, max(z, 0.05)
        else:
            project = lambda x, y, h: self.project(cam, x, y, h)   # noqa: E731
        if gone > 0:
            tris = model_mod.shards(mdl, world, gone, seed, by=mdl.breaks)
            cull = False
        else:
            tris = [((world[f[0]], world[f[1]], world[f[2]]), f) for f in mdl.faces]
            cull = True
        W, H = self.PW, self.PH
        zbuf = {}
        lb, ll, lu = self.LIGHT                           # the light comes with the viewer: what he sees is lit
        light = _unit3((cam[2] * lb + cam[4] * ll, cam[3] * lb + cam[5] * ll, lu))
        ex, ey = cam[0], cam[1]
        smooth = mdl.smooth and gone <= 0
        fr = getattr(px, "frame", None)
        if fr is not None:                                # CLIo Picture 0.5: all of it in C
            got = picture.model_draw(fr, mdl, tris, cull, smooth, len(world), cam, self,
                                     flat if flat > 0 and gone <= 0 else 0.0, max(0.3, zc), light, flash, tint)
            if got is not False:
                return got
        normals = {}
        if smooth:                                        # a corner's normal: its triangles' together
            for (p0, p1, p2), f in tris:
                n = _normal(p0, p1, p2)
                for i in f[:3]:
                    s = normals.setdefault(i, [0.0, 0.0, 0.0])
                    s[0] += n[0]
                    s[1] += n[1]
                    s[2] += n[2]
        top, xs, shown = self.PH, [], False
        fr = getattr(px, "frame", None)
        drawn = [] if fr is not None else None               # CLIo Picture's frame: the triangles together
        for (p0, p1, p2), f in tris:
            pts = [project(p[0], p[1], p[2]) for p in (p0, p1, p2)]
            if None in pts:
                continue
            area = (pts[1][0] - pts[0][0]) * (pts[2][1] - pts[0][1]) - (pts[1][1] - pts[0][1]) * (pts[2][0] - pts[0][0])
            if cull and area <= 0:                        # turned away (the model's x-y-z to the world's is a mirror)
                continue
            mat = mdl.materials[f[3]]
            rgb = f[4] or mat.rgb
            depth = (pts[0][2] + pts[1][2] + pts[2][2]) / 3
            fog = (0.5 + 0.5 * min(1.0, self.tz(depth) * 1.6)) if not mat.glow else 1.0    # as sprites
            haze = None
            if self.air is not None:                      # open land: into the haze instead (a lamp keeps more)
                fog, haze = 1.0, self.air[0]
                hk = (1.0 - math.exp(-depth / self.air[1])) * (0.35 if mat.glow else 1.0)
            if smooth:
                cols = []
                for i, p in zip(f[:3], (p0, p1, p2)):
                    n = _unit3(normals[i])
                    v = _unit3((ex - p[0], ey - p[1], self.EYE - p[2]))
                    c = model_mod.pbr(mat, rgb, (n[0], n[1], n[2]), light, v)
                    cols.append(list(mix(c, haze, hk)) if haze else [c[0] * fog, c[1] * fog, c[2] * fog])
            else:
                n = _normal(p0, p1, p2)
                if not cull and n[0] * (ex - p0[0]) + n[1] * (ey - p0[1]) + n[2] * (self.EYE - p0[2]) < 0:
                    n = (-n[0], -n[1], -n[2])             # a shard's back: lit as its front
                mx_ = (p0[0] + p1[0] + p2[0]) / 3
                my_ = (p0[1] + p1[1] + p2[1]) / 3
                mz_ = (p0[2] + p1[2] + p2[2]) / 3
                v = _unit3((ex - mx_, ey - my_, self.EYE - mz_))
                c = model_mod.pbr(mat, rgb, n, light, v)
                cols = mix(c, haze, hk) if haze else (int(c[0] * fog), int(c[1] * fog), int(c[2] * fog))
                if flash:
                    cols = (255, 255, 255)
                elif tint:
                    cols = mix(cols, tint, 0.6)
            if drawn is not None:
                drawn.append((pts, cols))
            else:
                model_mod.raster(px, zbuf, W, H, pts, cols)
            shown = True
            top = min(top, pts[0][1], pts[1][1], pts[2][1])
            xs += [pts[0][0], pts[1][0], pts[2][0]]
        if drawn:
            fr.triangles(drawn)
        if not shown:
            return None
        return top, (min(xs) + max(xs)) / 2

    def toner(self, z, fog):
        """How a thing this far off is coloured, for blit: darker with the distance indoors, into the haze in
        open land."""
        if self.air is None:
            return _Tone(fog)
        return _Tone(fog, self.air[0], 1.0 - math.exp(-max(0.0, z) / self.air[1]))

    def shadow(self, px, x, base, w):
        fr = getattr(px, "frame", None)
        if fr is not None:
            fr.darken(int(x - w * 0.4), int(x + w * 0.4), int(base) - self.sy // 2, int(base), 0.6)
            return
        for yy in range(int(base) - self.sy // 2, int(base) + 1):
            if 0 <= yy < self.PH:
                for xx in range(int(x - w * 0.4), int(x + w * 0.4) + 1):
                    if 0 <= xx < self.PW:
                        px[yy][xx] = shade(px[yy][xx], 0.6)

    def draw_monster_model(self, px, lv, m, a, z, mx, my, fx, labels, cam, phase):
        mdl = lv.models[m.model]
        t = phase + fx.tick
        if m.intent in ("aim", "windup", "spin", "charge") or m.id in fx.emuzzle or m.heading is None:
            heading = math.atan2(cam[1] - my, cam[0] - mx)            # at the player
        elif m.id in fx.pos and (m.x, m.y) != (mx, my):
            heading = math.atan2(m.y - my, m.x - mx)                  # the way it is going
        else:
            heading = m.heading
        if m.dead and m.id not in fx.dissolve:
            return
        clip = ("attack" if m.intent in ("aim", "windup", "spin") or m.id in fx.emuzzle else
                "walk" if m.id in fx.pos else "idle")
        lift = m.float * 0.6 + (fx.rise.get(m.id, 0.0) if fx.rise else 0.0)
        g = lv.ground(mx, my) if getattr(lv, "land", None) is not None else 0.0
        lift += g
        tz = self.tz(z)
        foot = self.yh + (self.FS - g * self.TALL) * tz
        self.shadow(px, self.X(a, z), foot, mdl.radius * (1.4 if m.float else 2) * m.size * self.LW * tz)
        roll = 0.0
        if getattr(m, "ball", False):                  # a ball turns as far as it has rolled
            heading = m.heading or 0.0
            gap = math.hypot(m.x - mx, m.y - my)
            roll = (m.rolled - gap) / max(0.05, mdl.height / 2.0 * m.size)
        got = self.draw_model(px, mdl, mx, my, heading, clip, t, cam, lift=lift, size=m.size,
                              gone=fx.dissolve.get(m.id, 0.0) if m.dead or m.id in fx.dissolve else 0.0, seed=m.id,
                              flash=m.id in fx.flash, tint=fx.tint.get(m.id), roll=roll)
        if got and labels is not None and not m.dead and m.seen:
            top, x = got
            text, role = m.label()
            row = max(0, int(top) // self.sy - 1)
            labels.append((row, int(round(x / self.sx - len(text) / 2)), text, role, z, m.targeted))
            for mm, txt, r, rise in fx.texts:
                if mm is m:
                    labels.append((max(0, row - 1 - rise // 2), int(round(x / self.sx - len(txt) / 2)), txt, r, z, False))

    def draw_thing(self, px, pic, a, z, size, m, fx, labels, lift=0.0, ground=0.0):
        if pic is None:
            return
        t = self.tz(z)
        s = t * self.K * size * (fx.lunge.get(m.id, 1.0) if m is not None else 1.0)
        target_h = pic.h * s
        pp = pic.pick(target_h)
        s = target_h / pp.h
        sw, sh = int(round(pp.w * s)), int(round(pp.h * s))
        base = self.yh + (self.FS - ground * self.TALL) * t      # its feet: on the ground where it stands
        lift = (m.float * REF_H * t * self.K) if m is not None else lift * REF_H * t * self.K
        if m is not None and fx.rise.get(m.id):
            lift += fx.rise[m.id] * self.PH
        x = self.X(a, z)
        x0, y0 = int(round(x - sw / 2)), int(round(base - sh - lift))
        self.shadow(px, x, base, sw)                          # a shadow on the floor
        fog = 0.5 + 0.5 * min(1.0, t * 1.6)
        tone = self.toner(z, fog)
        haze = self.air[0] if self.air is not None else None
        hk = 1.0 - math.exp(-max(0.0, z) / self.air[1]) if haze else 0.0
        muzzle = pic.muzzle
        if m is not None and not m.dead:              # the frame for what it is doing
            if pic.attack is not None and (m.intent in ("aim", "windup", "spin") or m.id in fx.emuzzle):
                pp = pic.attack.pick(target_h)
            elif pic.walk and m.id in fx.pos and not m.float:
                pp = pic.walk[getattr(m, "stride", 0) % len(pic.walk)].pick(target_h)
        if m is None:
            self.blit(px, pp.rows, x0, y0, s, tone, z)
            return
        fn = _Tone(fog, haze, hk, gone=fx.dissolve.get(m.id, 0.0), step=max(s, 0.01), mid=m.id,
                   flash=m.id in fx.flash, tint=fx.tint.get(m.id))
        self.blit(px, pp.rows, x0, y0, s, fn, z)
        if m.intent == "windup" and not m.dead:                   # fire gathering in its hand
            fs = s * 0.8
            gx, gy = (x0 + sw * muzzle[0], y0 + sh * muzzle[1]) if muzzle else (x0 + sw * 0.85, y0 - 2 * fs)
            self.glow(px, gx, gy, 6 * fs + 1, (255, 140, 40), 0.55)
            if self.fireball is not None:
                fb = self.fireball
                self.blit(px, fb.rows, int(round(gx - fb.w * fs / 2)), int(round(gy - fb.h * fs / 2)), fs)
        if m.id in fx.emuzzle:
            mx, my = muzzle or (0.95, 0.45)
            self.glow(px, x0 + sw * mx, y0 + sh * my, max(2.5 * self.sx, 4 * s), (255, 230, 120), 0.95)
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

    def canopy(self, px, colour):
        """A cockpit's canopy: a frame across the top, two posts slanting in from the bottom corners."""
        fr = getattr(px, "frame", None)
        if fr is not None:
            fr.canopy(colour)
            return
        dark, lite = shade(colour, 0.55), mix(colour, (255, 255, 255), 0.25)
        bh = max(2, self.PH // 14)
        bw = max(2, self.PW // 40)
        for y in range(bh):
            for x in range(self.PW):
                px[y][x] = lite if y == bh - 1 else colour if y else dark
        for y in range(bh, self.PH):
            k = (y - bh) / float(max(1, self.PH - bh))
            inset = int(self.PW * 0.16 * (1 - k))         # the posts lean in towards the top
            for x0 in (inset, self.PW - inset - bw):
                for x in range(max(0, x0), min(self.PW, x0 + bw)):
                    px[y][x] = lite if x == x0 + bw - 1 or x == x0 else colour
            for x in range(0, max(0, inset)):             # the hull beside the posts, out to the edges
                px[y][x] = shade(px[y][x], 0.35)
            for x in range(min(self.PW, self.PW - inset), self.PW):
                px[y][x] = shade(px[y][x], 0.35)

    def dashboard(self, px, v, colour):
        """Under the canopy: the console, its two screens and the fuel gauge (amber, red when low)."""
        h = max(3, self.PH // 9)
        y0 = self.PH - h
        x0, x1 = int(self.PW * 0.2), int(self.PW * 0.8)
        fr = getattr(px, "frame", None)
        if fr is not None:
            w = x1 - x0
            fuel = getattr(v, "fuel", 0)
            full = max(fuel, getattr(v, "fuel_max", 0) or 1)
            v.fuel_max = full
            gx0, gx1 = x0 + w * 3 // 10, x1 - w * 3 // 10
            fr.dashboard(colour, h, y0, x0, x1, gx0, gx1, y0 + h // 2, gx0 + int((gx1 - gx0) * fuel / float(full)),
                         fuel <= 5)
            return
        dark = shade(colour, 0.4)
        for y in range(y0, self.PH):
            for x in range(x0, x1):
                px[y][x] = dark if y > y0 else mix(colour, (255, 255, 255), 0.2)
        w = x1 - x0
        for sx in (x0 + w // 12, x1 - w // 12 - w // 6):        # two screens, a line of readout each
            for y in range(y0 + 1, self.PH - 1):
                for x in range(sx, sx + w // 6):
                    lit = (x + y * 3) % 5 < 3 and y == y0 + 1 + (x // 3) % max(1, h - 2)
                    px[y][x] = (90, 230, 140) if lit else (10, 26, 18)
        fuel = getattr(v, "fuel", 0)
        full = max(fuel, getattr(v, "fuel_max", 0) or 1)
        v.fuel_max = full
        gx0, gx1 = x0 + w * 3 // 10, x1 - w * 3 // 10
        gy = y0 + h // 2
        lit = gx0 + int((gx1 - gx0) * fuel / float(full))
        for y in range(gy - max(0, h // 4), gy + max(1, h // 4)):
            if 0 <= y < self.PH:
                for x in range(gx0, gx1):
                    px[y][x] = ((230, 70, 40) if fuel <= 5 else (240, 170, 50)) if x < lit else (30, 24, 16)

    def cockpit(self, px, lv, fx):
        """Riding a machine: its cage at the edges of the picture and its claws at the bottom (the sprite named
        by the vehicle's ``cockpit``, as wide as the picture allows) - or, for a vehicle with a ``canopy``
        (a colour), the canopy's frame."""
        v = lv.player.vehicle
        frame = (getattr(v, "vehicle", None) or {}).get("canopy")
        if frame:
            from .sprite import _rgb
            try:
                col = _rgb(frame) if isinstance(frame, str) else (70, 76, 60)
            except (ValueError, TypeError):
                col = (70, 76, 60)
            self.canopy(px, col)
            self.dashboard(px, v, col)
            pic = lv.sprites.get(lv.weapon_sprite())
            if pic is not None:
                s = min(self.PW * 0.92 / pic.w, self.PH * 0.34 / pic.h)
                x0 = int(round(self.half - pic.w * s / 2)) + fx.shake * self.sx
                y0 = self.PH - int(round(pic.h * s)) + fx.recoil * self.sy
                self.blit(px, pic.rows, x0, y0, s)
            if fx.muzzle:                                  # the guns under the nose
                for gx in (self.PW * 0.3, self.PW * 0.7):
                    self.glow(px, gx, self.PH * 0.72, max(2.0, self.PH * 0.06), (255, 200, 90), 0.8)
            return
        bw, bh = max(1, self.PW // 70), max(1, self.PH // 26)
        fr = getattr(px, "frame", None)
        if fr is not None:
            fr.cage()
        else:
            for y in range(self.PH):
                c = (214, 168, 48) if (y // max(2, bh * 2)) % 2 else (34, 32, 30)
                for x in list(range(bw)) + list(range(self.PW - bw, self.PW)):
                    px[y][x] = c
            for y in range(bh):
                for x in range(self.PW):
                    px[y][x] = (214, 168, 48) if (x // max(3, bw * 3)) % 2 else (34, 32, 30)
        pic = lv.sprites.get(lv.weapon_sprite())
        if pic is None:
            return
        s = min(self.PW * 0.92 / pic.w, self.PH * 0.48 / pic.h)
        x0 = int(round(self.half - pic.w * s / 2)) + fx.shake * self.sx
        y0 = self.PH - int(round(pic.h * s)) + fx.recoil * self.sy
        self.blit(px, pic.rows, x0, y0, s)

    def weapon(self, px, lv, fx):
        if getattr(lv.player, "vehicle", None) is not None:
            return self.cockpit(px, lv, fx)
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
        fr = getattr(px, "frame", None)
        if fr is not None:
            fast = fr.dots(fill, dot_level)
        else:
            fast = picture.dots(px, self.W, self.VR, fill, dot_level)     # in C, when CLIo Picture is here
        if fast is not None:
            for (r, c), o in over.items():
                if o and 0 <= r < self.VR and 0 <= c < self.W:
                    block = [px[4 * r + dy][2 * c + dx] for dy in range(4) for dx in range(2)]
                    fast[r][c] = (o[0], o[1], o[2] or (shade(_avg(block), 0.45) if fill else None))
            return fast
        cells = []
        level, bright, lums_of = {}, {}, {}                  # per colour, once: how lit, its dot colour, luminance
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
                    lums = []
                    for b in block:
                        v = lums_of.get(b[0])
                        if v is None:
                            v = lums_of[b[0]] = lum(b[0])
                        lums.append(v)
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
                        v8 = level.get(colour)
                        if v8 is None:
                            v8 = level[colour] = dot_level(lum(colour))
                        if v8 > BAYER_2X4[dy][dx] + 0.5:
                            bits |= BRAILLE_BIT[dy][dx]
                            lit.append(colour)
                    if not bits:
                        out.append((" ", None, None))
                        continue
                    mean = lit[0] if lit.count(lit[0]) == len(lit) else _avg(lit)
                    fg = bright.get(mean)
                    if fg is None:
                        fg = bright[mean] = shade(mean, min(1.9, 215.0 / max(1, max(mean))))
                    out.append((chr(0x2800 + bits), fg, None))
            cells.append(out)
        return cells


def tilt(cells, degrees, dark=(10, 10, 14)):
    """A pixel-style picture (rows of cells; char None = two pixels) turned ``degrees`` about its middle, as
    the world tips when magboots walk up a wall. Each cell is two pixels high, so the pixels are about
    square and the turn keeps its shape."""
    if not cells:
        return cells
    H, W = len(cells), len(cells[0])
    px = []
    for row in cells:
        top, bot = [], []
        for ch, fg, bg in row:
            if ch is None:
                top.append(fg or dark)
                bot.append(bg or dark)
            else:
                c = bg or fg or dark
                top.append(c)
                bot.append(c)
        px += [top, bot]
    a = math.radians(degrees)
    ca, sa = math.cos(a), math.sin(a)
    cx, cy = (W - 1) / 2.0, (2 * H - 1) / 2.0
    out = []
    for y in range(H):
        row = []
        for yy in (2 * y, 2 * y + 1):
            line = []
            dy = yy - cy
            for x in range(W):
                dx = x - cx
                sx, sy = int(round(cx + dx * ca + dy * sa)), int(round(cy - dx * sa + dy * ca))
                line.append(px[sy][sx] if 0 <= sx < W and 0 <= sy < 2 * H else dark)
            row.append(line)
        out.append([(None, t, b) for t, b in zip(row[0], row[1])])
    return out


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


def model_still(mdl, size=24, heading=1.0):
    """A 3D model alone, three-quarters on, as rows of colours (None: clear) about ``size`` pixels square -
    for a list of things or an editor's preview."""
    v = View(150, 30, "pixel")                            # drawn as a level draws it, then shrunk
    d = 1.2
    cam = (0.0, d, 0, -1, 1, 0)                           # standing south of it, looking north
    px = [[None] * v.PW for _ in range(v.PH)]
    v.draw_model(px, mdl, 0.0, 0.0, heading, "idle", 0.0, cam)
    ys = [y for y, row in enumerate(px) if any(c is not None for c in row)]
    xs = [x for row in px for x, c in enumerate(row) if c is not None]
    if not ys:
        return []
    y0, y1, x0, x1 = min(ys), max(ys) + 1, min(xs), max(xs) + 1
    rows = [row[x0:x1] for row in px[y0:y1]]
    k = max(1.0, max(len(rows), x1 - x0) / float(size))   # shrunk to fit: the pixel nearest each
    return [[rows[int(y * k)][int(x * k)] for x in range(int((x1 - x0) / k))] for y in range(int(len(rows) / k))]
