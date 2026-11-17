# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Animations for art: effects that play over any drawing, once, when it is shown.

An effect is named in an ``.art`` file (``@effect glitch``), in game.json
(``"title_effect": "shine"``) or in an effect (``{"art": "door", "effect":
"flicker"}``).  It may carry options: ``"glitch loops=2 speed=0.5"`` or
``{"name": "glitch", "loops": 2, "speed": 0.5}``.  ``speed`` scales the timing
(2 is twice as fast), ``loops`` repeats it.

Every effect ends on the drawing itself and keeps its size, so it can be
played in place.  Nothing here sleeps or prints: :meth:`engine.art.Art.animation`
asks for the frames and the UI plays them, only on a real terminal and never
with ``--fast``.  Effects that are made of colour (shine, pulse, cycle) do not
play on a terminal without colour; the others work everywhere.
"""
from __future__ import annotations

import colorsys
import random

from .term import PALETTE, idx256_to_rgb, parse_hex

EFFECTS = {
    "glitch": "rows slip sideways, colours split into red and cyan, noise flickers, then it settles",
    "flicker": "it lights up part by part like a neon sign switched on, with a stutter or two",
    "shine": "a bright glint sweeps across, left to right",
    "twinkle": "stars and dots twinkle (or, in art without them, a few cells sparkle)",
    "pulse": "the colours swell towards white and back",
    "cycle": "the colours run once round the colour wheel",
    "type": "it is typed in from the left behind a block cursor",
    "frames": "plays the @frame drawings of the .art file (reveal=1: they build it up from nothing)",
    "none": "no animation",
}
NAMES = tuple(EFFECTS)
COLOUR_ONLY = {"shine", "pulse", "cycle"}
REVEALS = {"type", "flicker"}           # these start from nothing / from dark

_STAR_SWAP = {"★": "☆", "☆": "★", "•": "·", "·": "•", "●": "○", "○": "●", "◆": "◇", "◇": "◆",
              "*": "+", "+": "*", "o": "°"}
_NOISE = "▓▒░"


# --------------------------------------------------------------------------- #
# specs
# --------------------------------------------------------------------------- #
def parse(spec):
    """``"glitch loops=2"`` / ``{"name": "glitch", ...}`` -> ``{"name": "glitch", "loops": 2}``.

    ``None`` stays None (nothing asked); False, ``""``, ``"off"`` and ``"none"``
    mean no animation.  An unknown name is kept, so it can be reported."""
    if spec is None or spec is True:
        return None
    if spec is False:
        return {"name": "none"}
    if isinstance(spec, dict):
        out = dict(spec)
        out["name"] = str(out.get("name") or out.get("effect") or "none").strip().lower()
        out.pop("effect", None)
    else:
        words = str(spec).split()
        out = {"name": words[0].lower() if words else "none"}
        for w in words[1:]:
            if "=" in w:
                k, v = w.split("=", 1)
                try:
                    out[k.strip()] = float(v) if "." in v else int(v)
                except ValueError:
                    out[k.strip()] = v
    if out["name"] in ("off", "false", "no", ""):
        out["name"] = "none"
    return out


def describe(spec):
    """The ``@effect`` line for a spec."""
    spec = parse(spec) or {"name": "none"}
    return " ".join([spec["name"]] + ["%s=%s" % (k, v) for k, v in spec.items() if k != "name"])


def known(spec):
    spec = parse(spec)
    return spec is None or spec["name"] in EFFECTS


def seconds(base, spec):
    try:
        speed = float((spec or {}).get("speed", 1) or 1)
    except (TypeError, ValueError):
        speed = 1.0
    return base / max(0.1, min(10.0, speed))


# --------------------------------------------------------------------------- #
# colours
# --------------------------------------------------------------------------- #
def _rgb(token):
    t = token.lower()
    if t.startswith("#"):
        try:
            return parse_hex(t)
        except (ValueError, IndexError):
            return None
    if t in PALETTE:
        return PALETTE[t]
    if t.isdigit() and int(t) < 256:
        return idx256_to_rgb(int(t))
    return None


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def tint(spec, fn):
    """A colour spec with every colour in it (foreground and on_background) passed through ``fn(rgb)``."""
    out = []
    for tok in (spec or "").split():
        bg = tok.lower().startswith("on_")
        core = tok[3:] if bg else tok
        rgb = _rgb(core)
        out.append((("on_" if bg else "") + _hex(fn(rgb))) if rgb else tok)
    return " ".join(out)


def toward(target, amount):
    return lambda rgb: tuple(a + (b - a) * amount for a, b in zip(rgb, target))


def hue_shift(degrees):
    def fn(rgb):
        h, l, s = colorsys.rgb_to_hls(*[v / 255.0 for v in rgb])
        r, g, b = colorsys.hls_to_rgb((h + degrees / 360.0) % 1.0, l, s)
        return (r * 255, g * 255, b * 255)
    return fn


# --------------------------------------------------------------------------- #
# a drawing as a grid of cells
# --------------------------------------------------------------------------- #
class _Grid:
    def __init__(self, lines, mask):
        self.h = len(lines)
        self.w = max((len(l) for l in lines), default=0)
        self.ch = [list(l.ljust(self.w)) for l in lines]
        self.key = []
        for y in range(self.h):
            row = mask[y] if mask and y < len(mask) else ""
            self.key.append([(row[x] if x < len(row) and row[x] not in " ." else None) for x in range(self.w)])

    def copy(self):
        g = _Grid.__new__(_Grid)
        g.h, g.w = self.h, self.w
        g.ch = [list(r) for r in self.ch]
        g.key = [list(r) for r in self.key]
        return g

    def cells(self):
        return [(x, y) for y in range(self.h) for x in range(self.w) if self.ch[y][x] != " "]

    def shift(self, y, d):
        if d > 0:
            self.ch[y] = [" "] * d + self.ch[y][:-d]
            self.key[y] = [None] * d + self.key[y][:-d]
        elif d < 0:
            self.ch[y] = self.ch[y][-d:] + [" "] * -d
            self.key[y] = self.key[y][-d:] + [None] * -d

    def out(self):
        return (["".join(r).rstrip() or " " for r in self.ch],
                ["".join(k or " " for k in row) for row in self.key])


class _Keys:
    """Palette entries an effect adds, under private-use characters no file uses."""

    def __init__(self, palette, default):
        self.palette = dict(palette)
        self.default = default or ""
        self._made = {}
        self._next = 0xE000

    def spec_of(self, key):
        return self.palette.get(key, self.default) if key else self.default

    def add(self, spec):
        if spec not in self._made:
            k = chr(self._next)
            self._next += 1
            self.palette[k] = spec
            self._made[spec] = k
        return self._made[spec]

    def tinted(self, key, fn, extra=""):
        base = self.spec_of(key) or "#c8c8c8"
        return self.add((tint(base, fn) + (" " + extra if extra else "")).strip())


# --------------------------------------------------------------------------- #
# the effects
# --------------------------------------------------------------------------- #
def frames(spec, lines, mask, palette, default, term, seed, render):
    """Frames of an effect: ``([(lines, seconds), ...], reveals)``, not yet ending on the art.

    ``render(lines, mask, palette)`` turns a drawing into terminal lines."""
    spec = parse(spec)
    if not spec or spec["name"] not in EFFECTS or spec["name"] in ("none", "frames"):
        return [], False
    if not lines or (mask is None and any("{" in l for l in lines)):
        return [], False                # inline markup: leave it alone
    name = spec["name"]
    colour = term.color_depth > 0
    if name in COLOUR_ONLY and not colour:
        return [], False
    base = _Grid(lines, mask)
    keys = _Keys(palette, default)
    rnd = random.Random("%s:%s" % (seed, name))
    seq = _MAKERS[name](base, keys, rnd, colour, spec)
    out = []
    loops = 1 if name in REVEALS else max(1, min(5, int(spec.get("loops", 1) or 1)))
    for _ in range(loops):
        for grid, secs in seq:
            l, m = grid.out()
            out.append((render(l, m, keys.palette), seconds(secs, spec)))
    return out, name in REVEALS


def _glitch(base, keys, rnd, colour, spec):
    red, cyan = keys.add("#ff2a6d"), keys.add("#05d9e8")
    cells = base.cells()
    if not cells:
        return []

    def frame(level):
        g = base.copy()
        for _ in range(1 + int(2.5 * level)):
            y = rnd.randrange(g.h)
            g.shift(y, rnd.choice((-1, 1)) * rnd.randint(1, max(1, int(3 * level))))
        if colour:
            y0 = rnd.randrange(g.h)
            for y in range(y0, min(g.h, y0 + 1 + int(g.h * 0.6 * level))):
                row = list(g.ch[y])
                for x, c in enumerate(row):
                    if c == " ":
                        continue
                    if x > 0 and row[x - 1] == " " and g.ch[y][x - 1] == " ":
                        g.ch[y][x - 1], g.key[y][x - 1] = c, red
                    if x + 1 < g.w and row[x + 1] == " " and g.ch[y][x + 1] == " ":
                        g.ch[y][x + 1], g.key[y][x + 1] = c, cyan
        for _ in range(2 + int(6 * level)):
            x, y = cells[rnd.randrange(len(cells))]
            x = max(0, min(g.w - 1, x + rnd.randint(-2, 2)))
            g.ch[y][x] = _NOISE[rnd.randrange(len(_NOISE))]
            g.key[y][x] = rnd.choice((red, cyan)) if colour else None
        return g
    return [(frame(1.0), 0.07), (base, 0.05), (frame(0.8), 0.06), (frame(0.6), 0.07),
            (base, 0.12), (frame(0.35), 0.06), (frame(0.15), 0.05)]


def _groups(base):
    """Column runs separated by empty columns (the letters, usually)."""
    used = [any(base.ch[y][x] != " " for y in range(base.h)) for x in range(base.w)]
    groups, start = [], None
    for x, u in enumerate(used + [False]):
        if u and start is None:
            start = x
        elif not u and start is not None:
            groups.append((start, x))
            start = None
    if len(groups) < 3 and base.w >= 8:         # one solid block (a frame, a board): cut it in four
        step = -(-base.w // 4)
        groups = [(x, min(base.w, x + step)) for x in range(0, base.w, step)]
    return groups


def _flicker(base, keys, rnd, colour, spec):
    groups = _groups(base)
    dark = {}

    def frame(lit):
        g = base.copy()
        for i, (a, b) in enumerate(groups):
            if i in lit:
                continue
            for y in range(g.h):
                for x in range(a, b):
                    if g.ch[y][x] == " ":
                        continue
                    if colour:
                        k = g.key[y][x]
                        if k not in dark:
                            dark[k] = keys.tinted(k, toward((16, 16, 22), 0.78))
                        g.key[y][x] = dark[k]
                    else:
                        g.ch[y][x] = " "
        return g
    order = list(range(len(groups)))
    rnd.shuffle(order)
    lit = set()
    seq = [(frame(lit), 0.18)]
    for i in order:
        lit.add(i)
        seq.append((frame(lit), 0.07))
        if rnd.random() < 0.45:
            seq.append((frame(lit - {i}), 0.05))
            seq.append((frame(lit), 0.06))
    everything = set(range(len(groups)))
    seq += [(frame(set()), 0.04), (frame(everything), 0.08), (frame(set(order[:1])), 0.03)]
    return seq


def _shine(base, keys, rnd, colour, spec):
    bright = {}
    bw = 3
    seq = []
    for p in range(-bw, base.w + 2 * base.h, 2):
        g = base.copy()
        for y in range(g.h):
            for x in range(g.w):
                if g.ch[y][x] != " " and p <= x + 2 * y < p + bw:
                    k = g.key[y][x]
                    if k not in bright:
                        bright[k] = keys.tinted(k, toward((255, 255, 255), 0.8), "b")
                    g.key[y][x] = bright[k]
        seq.append((g, 0.022))
    return seq


def _twinkle(base, keys, rnd, colour, spec):
    stars = [(x, y) for x, y in base.cells() if base.ch[y][x] in _STAR_SWAP]
    if len(stars) < 3:
        stars = base.cells()
    if not stars:
        return []
    bright, dim = {}, {}
    seq = []
    for _ in range(9):
        g = base.copy()
        for x, y in stars:
            r = rnd.random()
            k = g.key[y][x]
            if r < 0.22:
                if colour:
                    if k not in bright:
                        bright[k] = keys.tinted(k, toward((255, 255, 255), 0.85), "b")
                    g.key[y][x] = bright[k]
            elif r < 0.4:
                g.ch[y][x] = _STAR_SWAP.get(g.ch[y][x], g.ch[y][x])
                if colour:
                    if k not in dim:
                        dim[k] = keys.tinted(k, toward((20, 20, 26), 0.6))
                    g.key[y][x] = dim[k]
        seq.append((g, 0.11))
    return seq


def _recolour(base, keys, fn):
    """The whole drawing with every colour passed through ``fn``."""
    g = base.copy()
    made = {}
    for y in range(g.h):
        for x in range(g.w):
            if g.ch[y][x] == " " and not g.key[y][x]:
                continue
            k = g.key[y][x]
            if k not in made:
                made[k] = keys.tinted(k, fn)
            g.key[y][x] = made[k]
    return g


def _pulse(base, keys, rnd, colour, spec):
    white = (255, 255, 255)
    return [(_recolour(base, keys, toward(white, a)), 0.06) for a in (0.2, 0.42, 0.65, 0.42, 0.2)]


def _cycle(base, keys, rnd, colour, spec):
    return [(_recolour(base, keys, hue_shift(d)), 0.07) for d in range(30, 360, 30)]


def _type(base, keys, rnd, colour, spec):
    cursor = keys.add("#f0f0f0 b") if colour else None
    used = [x for x in range(base.w) if any(base.ch[y][x] != " " for y in range(base.h))]
    if not used:
        return []
    left, right = used[0], used[-1] + 1
    step = max(1, (right - left) // 18)
    row = max(range(base.h), key=lambda y: sum(1 for c in base.ch[y] if c != " "))
    seq = []
    for edge in range(left, right + step, step):
        g = base.copy()
        for y in range(g.h):
            for x in range(min(edge, g.w), g.w):
                g.ch[y][x], g.key[y][x] = " ", None
        if edge < g.w:
            g.ch[row][edge], g.key[row][edge] = "█", cursor
        seq.append((g, 0.035))
    return seq


_MAKERS = {"glitch": _glitch, "flicker": _flicker, "shine": _shine, "twinkle": _twinkle,
           "pulse": _pulse, "cycle": _cycle, "type": _type}
