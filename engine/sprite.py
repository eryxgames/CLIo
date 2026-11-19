# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Pixel sprites drawn with half-block characters.

A sprite is a small grid of palette letters.  Two pixel rows share one text
row: the upper pixel is the foreground of ``▀`` and the lower pixel its
background, so pixels come out roughly square.  Without colour or Unicode the
sprite falls back to ASCII shading.

Sprites can also be *generated*: :func:`generate` grows a symmetric creature
from a seed, so every monster name gets its own consistent face, and
:func:`monster` builds a whole figure from a body plan (biped, beast, floater,
crawler, brute) for a first-person level.

Far away a sprite is drawn small.  :func:`far_versions` makes the smaller
drawings for that ahead of time (``"lod"`` in sprites.json), keeping the few
pixels that matter - eyes, mouths - instead of losing them as plain scaling
would; a game may also draw them by hand.
"""
from __future__ import annotations

import math
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
    def __init__(self, pixels, palette=None, name="", style="pixel"):
        self.name = name
        self.style = style if style in ("pixel", "blocks", "dots", "led", "ascii") else "pixel"
        self.pixels = [str(r) for r in pixels]
        self.width = max((len(r) for r in self.pixels), default=0)
        self.pixels = [r.ljust(self.width, ".") for r in self.pixels]
        self.source = dict(palette or {})
        self.palette = {k: _rgb(v) for k, v in (palette or {}).items()}
        self.palette.setdefault(".", None)
        self.palette.setdefault(" ", None)

    @classmethod
    def from_data(cls, data, name=""):
        return cls(data.get("pixels", []), data.get("palette", {}), name, data.get("style") or "pixel")

    @property
    def cols(self):
        """Columns the sprite takes on screen, in its style."""
        from .pixels import cols
        return cols(self.width, self.style) if self.style != "pixel" else self.width

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
        if self.style != "pixel" and term.unicode:
            from . import pixels
            return pixels.draw(pixels.image(rows, self.source, tint), self.style).lines(term)
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

# --------------------------------------------------------------------------- #
# Far versions
# --------------------------------------------------------------------------- #
CLEAR_LETTERS = ".", " "


def shrink(pixels, factor=2, keep=""):
    """A drawing ``factor`` times smaller.  Each block of pixels becomes the letter
    that matters most there: a letter in ``keep`` first, then letters that are rare
    in the whole drawing (eyes, mouths) over common ones (skin, cloth).  A block is
    clear only when most of it is clear."""
    rows = [str(r) for r in pixels]
    w = max((len(r) for r in rows), default=0)
    rows = [r.ljust(w, ".") for r in rows]
    h = len(rows)
    counts = {}
    for r in rows:
        for ch in r:
            if ch not in CLEAR_LETTERS:
                counts[ch] = counts.get(ch, 0) + 1
    total = float(sum(counts.values()) or 1)
    out = []
    for y in range(0, h, factor):
        line = []
        for x in range(0, w, factor):
            block = [rows[yy][xx] for yy in range(y, min(h, y + factor)) for xx in range(x, min(w, x + factor))]
            solid = [c for c in block if c not in CLEAR_LETTERS]
            if len(solid) * 2 < len(block) or not solid:
                line.append(".")
                continue
            kept = [c for c in solid if c in keep]
            if kept:
                line.append(max(set(kept), key=kept.count))
                continue
            line.append(max(sorted(set(solid)),
                            key=lambda c: solid.count(c) * (1.0 + 6.0 * (1.0 - counts[c] / total) ** 3)))
        out.append("".join(line))
    return out


def far_versions(pixels, keep="", smallest=4):
    """Smaller drawings of a sprite for distance: half and a third or a quarter
    of its size, as long as they stay at least ``smallest`` pixels high."""
    h = len(pixels)
    out = []
    for factor in (2, 3, 4):
        if h // factor >= smallest:
            rows = shrink(pixels, factor, keep)
            if rows and rows not in out:
                out.append(rows)
    return out


# --------------------------------------------------------------------------- #
# Monsters from a body plan
# --------------------------------------------------------------------------- #
BODIES = {
    "biped": "upright, two arms and two legs; may hold a weapon",
    "beast": "hunched, a big head with a mouth full of teeth, short thick limbs",
    "floater": "a round body that hovers, one or two eyes, tentacles or spikes",
    "crawler": "low and wide, many legs, mandibles",
    "brute": "a big upright body with horns, long arms and heavy legs",
}
_SCHEMES = [
    {"b": (150, 150, 140), "B": (100, 100, 96), "s": (138, 154, 124), "S": (86, 96, 78), "a": (138, 26, 26)},   # pale, bloody
    {"b": (200, 106, 110), "B": (140, 58, 66), "s": (200, 106, 110), "S": (140, 58, 66), "a": (216, 203, 176)},  # flesh
    {"b": (138, 90, 52), "B": (90, 56, 32), "s": (138, 90, 52), "S": (90, 56, 32), "a": (216, 203, 176)},       # brown hide
    {"b": (70, 74, 96), "B": (44, 46, 64), "s": (150, 140, 120), "S": (100, 92, 80), "a": (200, 40, 40)},       # dark uniform
    {"b": (120, 160, 70), "B": (70, 100, 40), "s": (120, 160, 70), "S": (70, 100, 40), "a": (230, 220, 120)},   # sickly green
    {"b": (110, 80, 150), "B": (70, 46, 100), "s": (110, 80, 150), "S": (70, 46, 100), "a": (240, 200, 90)},    # violet
    {"b": (70, 150, 160), "B": (36, 92, 100), "s": (70, 150, 160), "S": (36, 92, 100), "a": (255, 120, 80)},    # teal
    {"b": (170, 170, 180), "B": (100, 100, 112), "s": (170, 170, 180), "S": (100, 100, 112), "a": (90, 220, 255)},  # chrome
]
_EYES = [(255, 59, 47), (255, 210, 63), (255, 154, 31), (140, 255, 120), (120, 220, 255)]


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(v) for v in rgb)


def monster(seed, body="biped", size=18, scheme=None):
    """A figure grown from ``seed`` on a body plan (see ``BODIES``), as sprite data:
    ``{"pixels", "palette", "keep", "lod"}`` - ready for sprites.json and for
    drawing over by hand.  The same seed and plan always give the same figure."""
    body = body if body in BODIES else "biped"
    rnd = random.Random("clio-monster:%s:%s:%s" % (body, seed, size))
    size = max(10, min(48, int(size)))
    tall = body in ("biped", "brute")
    h = size
    w = max(8, int(round(size * (0.68 if tall else 1.0 if body != "crawler" else 1.4))))
    w += w % 2
    if body == "crawler":
        h = max(8, int(size * 0.6))
    grid = [["."] * w for _ in range(h)]
    cx = w / 2.0

    def put(x, y, ch, mirror=True):
        x, y = int(x), int(y)
        if 0 <= y < h:
            if 0 <= x < w:
                grid[y][x] = ch
            if mirror and 0 <= w - 1 - x < w:
                grid[y][w - 1 - x] = ch

    def ellipse(ex, ey, rx, ry, ch):
        for y in range(int(ey - ry) - 1, int(ey + ry) + 2):
            for x in range(int(ex - rx) - 1, int(ex + rx) + 2):
                if ((x + 0.5 - ex) / max(rx, 0.5)) ** 2 + ((y + 0.5 - ey) / max(ry, 0.5)) ** 2 <= 1.0:
                    put(x, y, ch)

    def rect(x0, y0, x1, y1, ch, mirror=True):
        for y in range(int(y0), int(y1)):
            for x in range(int(x0), int(x1)):
                put(x, y, ch, mirror)

    u = h / 18.0                                         # one "unit" of a person-sized figure
    if body in ("biped", "brute"):
        big = body == "brute"
        head_r = (1.6 + rnd.random() * 0.7) * u * (1.15 if big else 1.0)
        head_y = head_r + 0.5 * u
        sh = (3.2 + rnd.random() * 1.6) * u * (1.35 if big else 1.0)       # half the shoulders
        torso_top = head_y + head_r - 0.2 * u
        torso_bot = torso_top + (5.0 + rnd.random() * 1.5) * u * (1.1 if big else 1.0)
        hip = sh * (0.55 + rnd.random() * 0.2)
        for y in range(int(torso_top), int(torso_bot)):
            k = (y - torso_top) / max(1.0, torso_bot - torso_top)
            half = sh + (hip - sh) * k
            rect(cx - half, y, cx, y + 1, "b")
        ellipse(cx, head_y, head_r * 0.85, head_r, "s")
        ey = int(head_y - head_r * 0.15)
        put(cx - max(1, head_r * 0.45), ey, "e")
        put(cx - 0.5, int(head_y + head_r * 0.5), "m")
        arm = max(1, int(u * (1.4 if big else 1.0)))
        pose = rnd.choice(("down", "down", "out", "raised")) if big else rnd.choice(("down", "weapon", "weapon", "out"))
        ax = cx - sh - arm + 0.5
        arm_end = torso_bot + (2.5 * u if big else 0.8 * u)
        if pose == "raised":
            rect(ax, torso_top - 2.5 * u, ax + arm, torso_top + 2 * u, "s")
        elif pose == "out":
            rect(ax - 1.5 * u, torso_top + 1 * u, ax + arm, torso_top + 1 * u + arm, "s")
            rect(ax - 1.5 * u, torso_top + 1 * u, ax - 1.5 * u + arm, arm_end - 1 * u, "s")
        else:
            rect(ax, torso_top + 0.5, ax + arm, arm_end, "s")
        if body == "brute" or rnd.random() < 0.35:                                  # horns
            hx = cx - head_r * 0.7
            for i in range(int(2 + u * 1.5)):
                put(hx - i * 0.5, head_y - head_r - i + 0.5, "a")
        leg = max(1, int(u * (1.6 if big else 1.2)))
        gap = max(1, int(hip * 0.35))
        rect(cx - gap - leg, torso_bot, cx - gap, h - 1, "B")
        rect(cx - gap - leg - (1 if big else 0), h - 2, cx - gap + 1, h - 1, "S")       # feet
        if pose == "weapon":                                                          # a gun across the right side
            gy = int(torso_top + 2.5 * u)
            rect(cx + sh - 1, gy, min(w, cx + sh + 3 * u), gy + max(1, int(u)), "g", mirror=False)
            put(cx + sh + 2.5 * u, gy - 1, "g", mirror=False)
        if rnd.random() < 0.5:
            put(cx - sh * 0.5, torso_top + 2 * u, "a")                                 # a stain or a badge
    elif body == "beast":
        head_r = (4.2 + rnd.random() * 1.6) * u
        head_y = head_r + 1.0 * u
        ellipse(cx, head_y, head_r * 1.1, head_r, "s")
        ellipse(cx, head_y + head_r * 1.05, head_r * 0.8, head_r * 0.55, "b")
        mouth_y = int(head_y + head_r * 0.15)
        for y in range(mouth_y, mouth_y + max(2, int(head_r * 0.45))):
            rect(cx - head_r * 0.75, y, cx, y + 1, "m")
        for x in range(int(cx - head_r * 0.75), int(cx), 2):
            put(x, mouth_y, "t")
            put(x + 1, mouth_y + max(2, int(head_r * 0.45)) - 1, "t")
        ey = int(head_y - head_r * 0.45)
        put(cx - head_r * 0.45, ey, "e")
        if rnd.random() < 0.8:
            for i in range(int(1 + u * 2)):
                put(cx - head_r * 0.85 - i * 0.4, head_y - head_r - i + 1, "a")
        leg = max(1, int(1.6 * u))
        rect(cx - head_r * 0.8, h - 3 * u, cx - head_r * 0.8 + leg, h - 1, "B")
        rect(cx - head_r * 1.15, head_y + head_r * 0.6, cx - head_r * 1.15 + leg, head_y + head_r * 1.4, "B")
        put(cx - head_r * 0.8, h - 2, "a")
    elif body == "floater":
        r = (5.0 + rnd.random() * 1.8) * u
        oy = r + 1.0 * u
        ellipse(cx, oy, r, r * 0.95, "b")
        ellipse(cx + r * 0.25, oy + r * 0.25, r * 0.55, r * 0.5, "B")
        one = rnd.random() < 0.55
        if one:
            ellipse(cx, oy - r * 0.15, r * 0.36, r * 0.32, "E")
            put(cx - 0.5, oy - r * 0.15, "e")
        else:
            put(cx - r * 0.4, oy - r * 0.25, "e")
        mouth_y = int(oy + r * 0.45)
        rect(cx - r * 0.45, mouth_y, cx, mouth_y + max(1, int(u)), "m")
        put(cx - r * 0.3, mouth_y, "t")
        if rnd.random() < 0.6:                                         # tentacles
            for i, x in enumerate(range(int(cx - r * 0.8), int(cx), 2)):
                rect(x, oy + r * 0.8, x + 1, min(h - 1, oy + r * 0.8 + (2 + (i % 2) * 2) * u), "B")
        else:                                                          # spikes all round
            for ang in range(0, 180, 30):
                rad = math.radians(ang + 90)
                for k in range(int(1.5 * u) + 1):
                    put(cx + math.cos(rad) * (r + k) - 0.5, oy - math.sin(rad) * (r + k), "a")
    elif body == "crawler":
        r = w * 0.32
        oy = h * 0.45
        ellipse(cx, oy, r, h * 0.3, "b")
        ellipse(cx, oy - h * 0.12, r * 0.55, h * 0.18, "s")
        for i in range(3):
            put(cx - r * 0.25 - i, oy - h * 0.15, "e")
        legs = rnd.choice((3, 4))
        for i in range(legs):
            x0 = cx - r * 0.3 - i * (r * 0.8 / legs)
            for k in range(int(r * 0.9)):
                put(x0 - k, oy + k * 0.55, "B")
        put(cx - 0.5, oy + h * 0.2, "a")
        put(cx - 1.5, oy + h * 0.25, "a")
    # an outline round everything, for reading it at a distance
    solid = [[grid[y][x] != "." for x in range(w)] for y in range(h)]
    for y in range(h):
        for x in range(w):
            if not solid[y][x] and any(0 <= y + dy < h and 0 <= x + dx < w and solid[y + dy][x + dx]
                                       for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                grid[y][x] = "o"
    colours = dict(_SCHEMES[rnd.randrange(len(_SCHEMES))])
    colours.update({"o": (22, 20, 26), "e": _EYES[rnd.randrange(len(_EYES))], "E": (236, 230, 214),
                    "m": (52, 8, 12), "t": (238, 230, 207), "g": (58, 60, 66)})
    if scheme:
        colours.update({k: (_rgb(v) or colours.get(k)) for k, v in scheme.items()})
    pixels = ["".join(r) for r in grid]
    while len(pixels) > 4 and set(pixels[-1]) == {"."} and set(pixels[-2]) == {"."}:
        pixels.pop()                                     # no empty rows below the feet
    used = set("".join(pixels)) - {"."}
    data = {"pixels": pixels, "palette": {k: _hex(v) for k, v in sorted(colours.items()) if k in used},
            "keep": "".join(k for k in "eEmt" if k in used)}
    data["lod"] = [{"pixels": rows} for rows in far_versions(pixels, data["keep"])]
    return data


def hp_line(ui, name, hp, max_hp, width=12, spec="red"):
    """``Name  ██████░░  42/60`` - shared by battle screens."""
    return "%s %s %s" % (ui.c(name, "character"), ui.bar(hp, max_hp, width, spec),
                         ui.c("%d/%d" % (max(0, hp), max_hp), "system"))
