# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Pixel sprites drawn with half-block characters.

A sprite is a small grid of palette letters.  Two pixel rows share one text
row: the upper pixel is the foreground of ``▀`` and the lower pixel its
background, so pixels come out roughly square.  Without colour or Unicode the
sprite falls back to ASCII shading.

Sprites can also be *generated*: :func:`generate` grows a symmetric creature
from a seed, so every monster name gets its own consistent face.
"""
from __future__ import annotations

import random

from .term import PALETTE, RESET, idx256_to_rgb, luminance, parse_hex

_RAMP = " .:-=+*#%@"


def _rgb(spec):
    """Resolve a palette entry to an RGB tuple (None = transparent)."""
    if spec is None:
        return None
    if isinstance(spec, (list, tuple)) and len(spec) == 3:
        return tuple(int(v) for v in spec)
    s = str(spec).strip().lower()
    if s in ("", "none", "transparent", "clear"):
        return None
    if s.startswith("#"):
        try:
            return parse_hex(s)
        except (ValueError, IndexError):
            return None
    if s.isdigit():
        return idx256_to_rgb(int(s) % 256)
    return PALETTE.get(s)


class Sprite:
    def __init__(self, pixels, palette=None, name=""):
        self.name = name
        self.pixels = [str(r) for r in pixels]
        self.width = max((len(r) for r in self.pixels), default=0)
        self.pixels = [r.ljust(self.width, ".") for r in self.pixels]
        self.palette = {k: _rgb(v) for k, v in (palette or {}).items()}
        self.palette.setdefault(".", None)
        self.palette.setdefault(" ", None)

    @classmethod
    def from_data(cls, data, name=""):
        return cls(data.get("pixels", []), data.get("palette", {}), name)

    @property
    def height(self):
        return len(self.pixels)

    def _color(self, ch, tint=None):
        rgb = self.palette.get(ch)
        if rgb is None:
            return None
        if tint == "flash":
            return (255, 255, 255)
        if tint == "hurt":
            return (min(255, rgb[0] + 120), rgb[1] // 2, rgb[2] // 2)
        if tint == "dark":
            return (rgb[0] // 3, rgb[1] // 3, rgb[2] // 3)
        return rgb

    def render(self, term, tint=None, scale=1, flip=False):
        """Lines of text for this sprite on the given terminal."""
        rows = [r[::-1] for r in self.pixels] if flip else list(self.pixels)
        if len(rows) % 2:
            rows.append("." * self.width)
        out = []
        use_blocks = term.unicode and term.color_depth >= 1
        for y in range(0, len(rows), 2):
            top, bot = rows[y], rows[y + 1]
            parts = []
            for x in range(self.width):
                t = self._color(top[x], tint)
                b = self._color(bot[x], tint)
                if use_blocks:
                    if t is None and b is None:
                        cell = " "
                    elif t is not None and b is not None:
                        if t == b:
                            cell = "\x1b[%sm█" % term._fg(rgb=t)
                        else:
                            cell = "\x1b[%s;%sm▀" % (term._fg(rgb=t), term._fg(rgb=b, bg=True))
                    elif t is not None:
                        cell = "\x1b[%sm▀" % term._fg(rgb=t)
                    else:
                        cell = "\x1b[%sm▄" % term._fg(rgb=b)
                    parts.append((cell + RESET if cell != " " else cell) * scale)
                else:
                    if t is None and b is None:
                        parts.append(" " * scale)
                    else:
                        lum = sum(luminance(c) for c in (t, b) if c is not None) / 2.0
                        idx = 2 + int(lum * (len(_RAMP) - 3))
                        parts.append(_RAMP[min(len(_RAMP) - 1, idx)] * scale)
            out.append("".join(parts))
        return out


# --------------------------------------------------------------------------- #
# Procedural creatures
# --------------------------------------------------------------------------- #

_HUES = [
    ((200, 60, 60), (120, 30, 40)), ((90, 180, 90), (40, 100, 60)),
    ((90, 130, 220), (40, 60, 130)), ((200, 160, 60), (130, 90, 30)),
    ((170, 90, 200), (90, 40, 120)), ((80, 190, 190), (30, 100, 110)),
    ((210, 120, 60), (130, 60, 30)), ((170, 170, 180), (90, 90, 105)),
    ((220, 110, 160), (130, 50, 90)), ((140, 200, 80), (70, 110, 40)),
]


def generate(seed, size=12, kind="beast"):
    """Grow a symmetric creature sprite from any hashable seed."""
    rnd = random.Random("clio-sprite:%s" % (seed,))
    w = max(6, size + (size % 2))
    h = max(6, size)
    half = w // 2
    body, shade = _HUES[rnd.randrange(len(_HUES))]
    eye = (255, 255, 180) if rnd.random() < 0.7 else (255, 80, 80)
    grid = [[False] * half for _ in range(h)]
    # coarse random cells (invader style), doubled up, then one smoothing pass
    cw, chh = max(3, half // 2), max(3, h // 2)
    coarse = [[False] * cw for _ in range(chh)]
    for y in range(chh):
        for x in range(cw):
            cx = x / float(cw - 1)                        # 0 edge .. 1 centre
            cy = 1.0 - abs((y - chh * 0.45) / (chh * 0.6))
            p = 0.12 + 0.5 * cx + 0.3 * cy + (0.12 if kind == "tall" and x >= cw - 1 else 0)
            coarse[y][x] = rnd.random() < p
        coarse[y][cw - 1] = coarse[y][cw - 1] or (0 < y < chh - 1 and rnd.random() < 0.8)
    for y in range(h):
        for x in range(half):
            grid[y][x] = coarse[min(chh - 1, y // 2)][min(cw - 1, x // 2)]
    new = [[False] * half for _ in range(h)]
    for y in range(h):
        for x in range(half):
            n = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, min(half - 1, x + dx)
                    if 0 <= yy < h and xx >= 0:
                        n += grid[yy][xx]
            new[y][x] = n >= (4 if grid[y][x] else 6)
    grid = new
    # features: legs / tendrils below, horns or antennae above
    legs = rnd.choice((0, 2, 2, 3))
    rows_with = [y for y in range(h) if any(grid[y])]
    if rows_with:
        top_y, bot_y = rows_with[0], rows_with[-1]
        cols = [x for x in range(half) if grid[bot_y][x]] or [half - 1]
        if legs:
            for y in range(bot_y, min(h - 1, bot_y + 2)):
                for x in range(half):
                    grid[y][x] = False
            picks = sorted(rnd.sample(range(max(1, min(cols)), half), min(legs, half - max(1, min(cols)))))
            for x in picks:
                for y in range(max(0, bot_y - 1), min(h - 1, bot_y + 2)):
                    grid[y][x] = True
        if rnd.random() < 0.6 and top_y >= 2:
            hx = rnd.randrange(1, half - 1)
            for y in range(max(1, top_y - 2), top_y + 1):
                grid[y][hx] = True
    full = [row + row[::-1] for row in grid]
    for y in (0, h - 1):                                  # keep a margin for the outline
        full[y] = [False] * w
    for row in full:
        row[0] = row[-1] = False
    chars = [["."] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if full[y][x]:
                below = y + 1 < h and full[y + 1][x]
                chars[y][x] = "b" if below else "s"
            else:
                near = any(0 <= y + dy < h and 0 <= x + dx < w and full[y + dy][x + dx]
                           for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)))
                if near:
                    chars[y][x] = "o"
    # eyes: first body row in the upper half with room for a symmetric pair
    for y in range(2, h - 2):
        xs = [x for x in range(1, half - 1) if full[y][x] and full[y][x + 1]]
        if xs:
            x = xs[len(xs) // 2]
            chars[y][x] = "e"
            chars[y][w - 1 - x] = "e"
            if y + 1 < h and full[y + 1][x]:
                chars[y + 1][x] = "p"
                chars[y + 1][w - 1 - x] = "p"
            break
    palette = {"b": body, "s": shade, "o": (25, 22, 30), "e": eye, "p": (20, 20, 20)}
    return Sprite(["".join(r) for r in chars], palette, name=str(seed))


def hp_line(ui, name, hp, max_hp, width=12, spec="red"):
    """``Name  ██████░░  42/60`` - shared by battle screens."""
    return "%s %s %s" % (ui.c(name, "character"), ui.bar(hp, max_hp, width, spec),
                         ui.c("%d/%d" % (max(0, hp), max_hp), "system"))
