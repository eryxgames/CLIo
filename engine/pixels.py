# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Pixels to characters: the ways CLIo draws a picture made of coloured pixels.

A picture is a grid of palette letters - a sprite in ``sprites.json`` - and it
can be drawn in one of several styles::

    "torch": {"pixels": ["..y..", ".yry.", "..b.."], "palette": {"y": "#ffd23f", ...},
              "style": "dots", "effect": "twinkle",
              "frames": [["..r..", ".yry.", "..b.."]], "fps": 6}

==========  =========================================================  =================
style       how a pixel is drawn                                        pixels a cell
==========  =========================================================  =================
``pixel``   half blocks, two colours in a character (the default)      1 x 2
``blocks``  a pair of full blocks: big, crisp and square                2 cells a pixel
``dots``    braille dots: the finest detail, one colour in a character  2 x 4
``led``     a round dot and a space, like an LED panel                  2 cells a pixel
``ascii``   two letters by brightness, like classic ASCII art           2 cells a pixel
==========  =========================================================  =================

Pixels come out about square in every style.  ``frames`` are more drawings of
the same size, played in turn at ``fps`` (see :mod:`engine.fx`); ``effect`` is
any other animation.  :func:`picture` makes an :class:`~engine.art.Art` of a
sprite, so a sprite can be used wherever art is: scene pictures, portraits, the
title screen.  It carries a ``@small`` version in dots for narrow screens and an
``@ascii`` version in letters by brightness.
"""
from __future__ import annotations

from .term import PALETTE, idx256_to_rgb, luminance, parse_hex, to_ascii

STYLES = {
    "pixel": "half blocks: two pixels in a character, two colours (the default)",
    "blocks": "each pixel a pair of full blocks: big, crisp and square",
    "dots": "braille dots: eight in a character, the finest detail, one colour a character",
    "led": "each pixel a round dot, like an LED panel",
    "ascii": "letters by brightness, like classic ASCII art",
}
RAMP = " .:-=+*#%@"
CLEAR = ".", " "


# --------------------------------------------------------------------------- #
# colours
# --------------------------------------------------------------------------- #
def rgb_of(spec):
    """A palette entry - hex, a colour name, a 256-colour number or [r, g, b] - as RGB, or None."""
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


def _rgb(c):
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def hexc(t):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in t)


def mix(a, b, t):
    return hexc(tuple(x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b))))


def close(a, b, limit=120):
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b))) ** 0.5 <= limit


def image(pixels, palette, tint=None):
    """Rows of palette letters to rows of ``#rrggbb`` (None where nothing is drawn).
    ``tint``: ``"flash"`` (white), ``"hurt"`` (reddened) or ``"dark"``."""
    colours = {}
    for k, v in (palette or {}).items():
        rgb = rgb_of(v)
        if rgb is not None:
            if tint == "flash":
                rgb = (255, 255, 255)
            elif tint == "hurt":
                rgb = (min(255, rgb[0] + 120), rgb[1] // 2, rgb[2] // 2)
            elif tint == "dark":
                rgb = (rgb[0] // 3, rgb[1] // 3, rgb[2] // 3)
            colours[k] = hexc(rgb)
    rows = [str(r) for r in pixels]
    w = max((len(r) for r in rows), default=0)
    return [[(None if c in CLEAR else colours.get(c)) for c in r.ljust(w, ".")] for r in rows]


# --------------------------------------------------------------------------- #
# cells
# --------------------------------------------------------------------------- #
class Canvas:
    """Character cells: ``ch[y][x]`` and its colour spec ``col[y][x]`` (None: none)."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.ch = [[" "] * w for _ in range(h)]
        self.col = [[None] * w for _ in range(h)]

    def put(self, x, y, ch, spec=None):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.ch[y][x], self.col[y][x] = ch, spec

    def blit(self, other, ox, oy):
        for y in range(other.h):
            for x in range(other.w):
                if other.ch[y][x] != " " or other.col[y][x]:
                    self.put(ox + x, oy + y, other.ch[y][x], other.col[y][x])

    def lines(self, term):
        """The cells as terminal lines (colour runs painted, no trailing blanks)."""
        out = []
        for y in range(self.h):
            parts, run, spec = [], [], None
            end = len("".join(self.ch[y]).rstrip())
            for x in range(end):
                if self.col[y][x] != spec and run:
                    parts.append(term.paint("".join(run), spec) if spec else "".join(run))
                    run = []
                spec = self.col[y][x]
                run.append(self.ch[y][x])
            if run:
                parts.append(term.paint("".join(run), spec) if spec else "".join(run))
            out.append("".join(parts) + " " * (self.w - end))
        return out


def _even(img):
    w = max((len(r) for r in img), default=0)
    return [list(r) + [None] * (w - len(r)) for r in img], w


def halfblock(img, solid=False):
    """Two pixel rows in a text row with ``▀ ▄ █``.  ``solid``: never a background
    colour (for terminals without Unicode, where only the character is left)."""
    img, w = _even(img)
    if len(img) % 2:
        img.append([None] * w)
    cv = Canvas(w, len(img) // 2)
    for cy in range(cv.h):
        for x in range(w):
            t, b = img[2 * cy][x], img[2 * cy + 1][x]
            if t and b:
                if t == b or close(t, b) or solid:
                    cv.put(x, cy, "█", t if t == b or solid else mix(t, b, 0.5))
                else:
                    cv.put(x, cy, "▀", "%s on_%s" % (t, b))
            elif t:
                cv.put(x, cy, "▀", t)
            elif b:
                cv.put(x, cy, "▄", b)
    return cv


_DOTS = {(0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (1, 0): 0x08,
         (1, 1): 0x10, (1, 2): 0x20, (0, 3): 0x40, (1, 3): 0x80}


def braille(img):
    """Two by four pixels in a character with braille dots, in their most common colour."""
    img, w = _even(img)
    while len(img) % 4:
        img.append([None] * w)
    cv = Canvas((w + 1) // 2, len(img) // 4)
    for cy in range(cv.h):
        for cx in range(cv.w):
            bits, votes = 0, {}
            for (dx, dy), bit in _DOTS.items():
                x, y = 2 * cx + dx, 4 * cy + dy
                c = img[y][x] if x < w else None
                if c:
                    bits |= bit
                    votes[c] = votes.get(c, 0) + 1
            if bits:
                cv.put(cx, cy, chr(0x2800 + bits), max(votes, key=votes.get))
    return cv


def _pairs(img, draw):
    """Each pixel as two cells, ``draw(colour) -> (two characters)``."""
    img, w = _even(img)
    cv = Canvas(2 * w, len(img))
    for y, row in enumerate(img):
        for x, c in enumerate(row):
            if c:
                a, b = draw(c)
                cv.put(2 * x, y, a, c)
                if b != " ":
                    cv.put(2 * x + 1, y, b, c)
    return cv


def _letter(c):
    lum = luminance(_rgb(c))
    return RAMP[min(len(RAMP) - 1, 2 + int(lum * (len(RAMP) - 3)))]


def blocks(img):
    return _pairs(img, lambda c: ("█", "█"))


def led(img):
    return _pairs(img, lambda c: ("●", " "))


def letters(img):
    return _pairs(img, lambda c: (_letter(c), _letter(c)))


def ascii_cells(img):
    """The version for terminals without Unicode: half-block geometry, one letter by
    brightness for each pair of pixels, in their colour."""
    img, w = _even(img)
    if len(img) % 2:
        img.append([None] * w)
    cv = Canvas(w, len(img) // 2)
    for cy in range(cv.h):
        for x in range(w):
            pair = [c for c in (img[2 * cy][x], img[2 * cy + 1][x]) if c]
            if pair:
                c = pair[0] if len(pair) == 1 else mix(pair[0], pair[1], 0.5)
                lum = sum(luminance(_rgb(p)) for p in pair) / 2.0      # half-empty cells look lighter
                cv.put(x, cy, RAMP[min(len(RAMP) - 1, 1 + int(lum * (len(RAMP) - 2)))], c)
    return cv


DRAW = {"pixel": halfblock, "blocks": blocks, "dots": braille, "led": led, "ascii": letters}


def draw(img, style="pixel"):
    return DRAW.get(style, halfblock)(img)


def cols(width, style="pixel"):
    """How many columns a picture ``width`` pixels wide takes in a style."""
    if style == "dots":
        return (width + 1) // 2
    if style in ("blocks", "led", "ascii"):
        return 2 * width
    return width


# --------------------------------------------------------------------------- #
# art
# --------------------------------------------------------------------------- #
_KEYS = ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
         "!$%&*+-/<>?@^_~:;,()[]{}|'`\"\\")


def make_art(name, art, small=None, ascii=None, frames=(), effect=None, fps=None):
    """An :class:`~engine.art.Art` of Canvases: ``art`` and optionally ``small``,
    ``ascii`` (its characters are made ASCII one for one) and ``frames``, all under one palette."""
    from .art import Art
    specs = {}

    def key(spec):
        if spec not in specs:
            specs[spec] = _KEYS[len(specs)] if len(specs) < len(_KEYS) else chr(0xE100 + len(specs))
        return specs[spec]

    def variant(c, ascii_only=False, keep=None):
        lines, mask = [], []
        for y in range(c.h):
            row = "".join(c.ch[y]).rstrip()
            if ascii_only:                      # one character for one, so the mask still fits
                row = "".join((to_ascii(ch) or "?")[0] for ch in row)
            lines.append(row)
            mask.append("".join(key(c.col[y][x]) if c.col[y][x] else " " for x in range(len(row))))
        n = keep if keep is not None else len(lines)
        while len(lines) > n or (keep is None and lines and not lines[-1].strip()):
            lines.pop()
            mask.pop()
        return lines, mask

    out = Art(name)
    out.variants["art"] = variant(art)
    if small is not None:
        out.variants["small"] = variant(small)
    if ascii is not None:
        out.variants["ascii"] = variant(ascii, True)
    h = len(out.variants["art"][0])
    out.frames = [variant(f, keep=h) for f in frames]
    out.palette = {k: s for s, k in specs.items()}
    if fps:
        try:
            out.fps = max(0.5, min(60.0, float(fps)))
        except (TypeError, ValueError):
            pass
    if effect:
        from . import fx
        spec = fx.parse(effect)
        out.effect = spec if spec and spec["name"] != "none" else None
    return out


def style_of(data):
    style = str((data or {}).get("style") or "pixel").lower()
    return style if style in STYLES else "pixel"


def drawings(data):
    """The pixel rows of a sprite and of each of its frames."""
    main = [str(r) for r in (data.get("pixels") or [])]
    frames = [[str(r) for r in f] for f in (data.get("frames") or []) if isinstance(f, list) and f]
    return main, frames


def picture(data, name=""):
    """A sprite as :class:`~engine.art.Art`, in its style, with its animation."""
    style = style_of(data)
    main, frames = drawings(data)
    palette = data.get("palette") or {}
    img = image(main, palette)
    small = braille(img) if style != "dots" else None
    effect = data.get("effect")
    loops = data.get("loops")
    if frames and effect in (None, "", "frames") and loops:
        effect = {"name": "frames", "loops": loops}
    return make_art(name or "picture", draw(img, style), small, ascii_cells(img),
                    [draw(image(f, palette), style) for f in frames], effect, data.get("fps"))
