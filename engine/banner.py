# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Banners: any text drawn in one of CLIo's graphic styles.

A game can show its own title this way (``"title_banner"`` in game.json), put
up a banner in the middle of the story (the ``banner`` effect), or export one
as an ``.art`` file to draw over by hand (``clio.py --banner ... --export``)::

    "title_banner": {"text": "The Hollow", "style": "reflect", "palette": "ice",
                     "effect": "shine", "scale": 1}

Capitals and digits are 5x7 pixels; lower-case letters are drawn as small
capitals, so ``"CLIo"`` keeps its small o.  Pixels are drawn two to a
character cell with half blocks, so they come out square.  A banner that is
too wide for the screen is wrapped at spaces, drawn at a smaller scale, and in
the end falls back to the ``plain`` style, which fits almost anything.  Every
banner also carries a version for terminals without Unicode.
"""
from __future__ import annotations

import unicodedata

from .pixels import Canvas, braille, halfblock, make_art, mix

STYLES = {
    "pixel": "half-block pixel letters in a gradient",
    "shadow": "pixel letters with a drop shadow",
    "chrome": "extruded 3D letters with a chrome face",
    "glitch": "white letters with red and cyan ghosts",
    "reflect": "letters above their reflection in shading characters",
    "synthwave": "sunset letters standing on a perspective grid",
    "led": "a dot-matrix LED display, unlit dots and all",
    "dots": "fine letters in braille dots",
    "plain": "spaced capitals in a gradient - fits anywhere",
}
STYLE_DEFAULTS = {        # palette, effect
    "pixel": ("clio", None), "shadow": ("clio", None), "chrome": ("steel", "shine"),
    "glitch": ("mono", "glitch"), "reflect": ("ice", "shine"), "synthwave": ("sunset", "cycle"),
    "led": ("amber", "flicker"), "dots": ("clio", None), "plain": ("clio", None),
}
# name: (colours top to bottom, accent colours for lower case or None)
PALETTES = {
    "clio": (["#b8f4ff", "#5fd7ff", "#2fa8ff", "#2f6bff"], ["#fff2a8", "#ffd23f", "#ffa51a", "#d9700a"]),
    "sunset": (["#fff07a", "#ffb84d", "#ff6f91", "#e34fd1", "#9b5cff"], None),
    "ice": (["#ffffff", "#d6f3ff", "#9fd8ff", "#5fa8ff"], None),
    "fire": (["#fff3a0", "#ffc23d", "#ff7a1a", "#e0301e", "#8a1010"], None),
    "toxic": (["#eaff9a", "#a8ff3c", "#3cdc5a", "#14905a"], None),
    "gold": (["#fffbe0", "#ffe07a", "#f5b52e", "#b8740a"], None),
    "steel": (["#ffffff", "#c3d3ea", "#56698a"], ["#fffbe0", "#ffd25e", "#8a5a10"]),
    "amber": (["#ffd27a", "#ffb000", "#e08a00"], None),
    "phosphor": (["#c8ffc8", "#5aff7a", "#22c84a"], None),
    "blood": (["#ff9a9a", "#e0303a", "#a01020", "#5a0810"], None),
    "royal": (["#f3e0ff", "#c58bff", "#8a4cff", "#4a2ab8"], ["#ffe9a0", "#ffd25e", "#f0b83a"]),
    "forest": (["#e2f7c8", "#9fd86a", "#4fa84a", "#2a6b3a"], ["#ffe7a0", "#e0b050", "#a87028"]),
    "mono": (["#ffffff", "#d0d0d0", "#9a9a9a"], None),
}

# --------------------------------------------------------------------------- #
# the font: capitals, digits and signs 5x7; lower case as 5x5 small capitals
# --------------------------------------------------------------------------- #
_CAPS = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#", "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".###.|#...#|#....|#....|#....|#...#|.###.", "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####", "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".###.|#...#|#....|#.###|#...#|#...#|.####", "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": "###|.#.|.#.|.#.|.#.|.#.|###", "J": "..###|...#.|...#.|...#.|#..#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#", "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#", "N": "#...#|##..#|##..#|#.#.#|#..##|#..##|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.", "P": "####.|#...#|#...#|####.|#....|#....|#....",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#", "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.", "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.", "V": "#...#|#...#|#...#|#...#|.#.#.|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|##.##|#...#", "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..", "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.", "1": "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####", "3": "####.|....#|....#|.###.|....#|....#|####.",
    "4": "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.", "5": "#####|#....|####.|....#|....#|#...#|.###.",
    "6": ".###.|#....|#....|####.|#...#|#...#|.###.", "7": "#####|....#|...#.|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.", "9": ".###.|#...#|#...#|.####|....#|....#|.###.",
    ".": ".|.|.|.|.|.|#", ",": "..|..|..|..|..|.#|#.", "!": "#|#|#|#|#|.|#", "'": "#|#|.|.|.|.|.",
    "?": ".###.|#...#|....#|...#.|..#..|.....|..#..", '"': "#.#|#.#|...|...|...|...|...",
    ":": ".|#|.|.|.|#|.", ";": "..|.#|..|..|..|.#|#.", "-": "...|...|...|###|...|...|...",
    "+": ".....|..#..|..#..|#####|..#..|..#..|.....", "=": "....|....|####|....|####|....|....",
    "_": "....|....|....|....|....|....|####", "/": "....#|...#.|...#.|..#..|.#...|.#...|#....",
    "(": ".#|#.|#.|#.|#.|#.|.#", ")": "#.|.#|.#|.#|.#|.#|#.", "[": "##|#.|#.|#.|#.|#.|##",
    "]": "##|.#|.#|.#|.#|.#|##", "&": ".##..|#..#.|#.#..|.#...|#.#.#|#..#.|.##.#",
    "#": ".#.#.|.#.#.|#####|.#.#.|#####|.#.#.|.#.#.", "*": ".....|#.#.#|.###.|#####|.###.|#.#.#|.....",
    "<": "...#|..#.|.#..|#...|.#..|..#.|...#", ">": "#...|.#..|..#.|...#|..#.|.#..|#...",
    "%": "##..#|##..#|...#.|..#..|.#...|#..##|#..##", "$": "..#..|.####|#.#..|.###.|..#.#|####.|..#..",
    "@": ".###.|#...#|#.###|#.#.#|#.###|#....|.###.",
}
_SMALL = {
    "a": ".###.|#...#|#####|#...#|#...#", "b": "####.|#...#|####.|#...#|####.", "c": ".###.|#...#|#....|#...#|.###.",
    "d": "####.|#...#|#...#|#...#|####.", "e": "#####|#....|####.|#....|#####", "f": "#####|#....|####.|#....|#....",
    "g": ".####|#....|#..##|#...#|.###.", "h": "#...#|#...#|#####|#...#|#...#", "i": "###|.#.|.#.|.#.|###",
    "j": "..###|...#.|...#.|#..#.|.##..", "k": "#..#.|#.#..|##...|#.#..|#..#.", "l": "#....|#....|#....|#....|#####",
    "m": "#...#|##.##|#.#.#|#...#|#...#", "n": "#...#|##..#|#.#.#|#..##|#...#", "o": ".###.|#...#|#...#|#...#|.###.",
    "p": "####.|#...#|####.|#....|#....", "q": ".###.|#...#|#.#.#|#..#.|.##.#", "r": "####.|#...#|####.|#..#.|#...#",
    "s": ".####|#....|.###.|....#|####.", "t": "#####|..#..|..#..|..#..|..#..", "u": "#...#|#...#|#...#|#...#|.###.",
    "v": "#...#|#...#|.#.#.|.#.#.|..#..", "w": "#...#|#...#|#.#.#|##.##|#...#", "x": "#...#|.#.#.|..#..|.#.#.|#...#",
    "y": "#...#|.#.#.|..#..|..#..|..#..", "z": "#####|...#.|..#..|.#...|#####",
}
H = 7                      # pixel rows of a line of text
SPACE = 3                  # pixels for a space


def glyph(ch):
    """``(rows, kind)``: 7 rows of '#'/'.', kind 'u' (capitals, digits, signs) or 'l' (lower case)."""
    if ch in _CAPS:
        return _CAPS[ch].split("|"), "u"
    if ch in _SMALL:
        rows = _SMALL[ch].split("|")
        return ["." * len(rows[0])] * (H - len(rows)) + rows, "l"
    plain = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode("ascii")
    if plain and plain != ch:
        return glyph(plain[0])
    return _CAPS["?"].split("|"), "u"


def line_bitmap(text, gap=1):
    """One line of text as 7 rows of pixels: None, 'u' or 'l'."""
    rows = [[] for _ in range(H)]
    first = True
    for ch in text:
        if ch == " ":
            for r in rows:
                r.extend([None] * SPACE)
            first = True
            continue
        g, kind = glyph(ch)
        if not first:
            for r in rows:
                r.extend([None] * gap)
        for y in range(H):
            rows[y].extend(kind if c == "#" else None for c in g[y])
        first = False
    return rows


def text_width(text, gap=1):
    return len(line_bitmap(text, gap)[0])


# --------------------------------------------------------------------------- #
# colours
# --------------------------------------------------------------------------- #
def ramp(stops, n):
    """n colours spread evenly over a list of hex stops."""
    if n <= 1 or len(stops) == 1:
        return [stops[0]] * max(1, n)
    out = []
    for i in range(n):
        p = i / (n - 1) * (len(stops) - 1)
        k = min(int(p), len(stops) - 2)
        out.append(mix(stops[k], stops[k + 1], p - k))
    return out


def _colours(value):
    if isinstance(value, str):
        value = [v.strip() for v in value.split(",")]
    return [c for c in (value or []) if isinstance(c, str) and c.startswith("#")]


def own_palette(value):
    """A palette a game defines: a list of colours, or ``{"colors": [...], "accent": [...]}``.
    Returns ``(main, accent)``, or None when it holds no colours."""
    if isinstance(value, dict):
        main, accent = _colours(value.get("colors")), _colours(value.get("accent"))
    else:
        main, accent = _colours(value), []
    return (main, accent or None) if main else None


def palette_of(spec, style, palettes=None):
    """``(main stops, accent stops)`` from a spec's ``palette`` / ``colors`` / ``accent``.
    ``palettes``: the game's own named palettes, found before the built-in ones."""
    default = PALETTES[STYLE_DEFAULTS.get(style, ("clio", None))[0]]
    main, accent = default
    pal = spec.get("palette")
    if isinstance(pal, str):
        found = own_palette((palettes or {}).get(pal)) if pal in (palettes or {}) else None
        main, accent = found or PALETTES.get(pal, default)
    elif pal:
        main, accent = own_palette(pal) or default
    if spec.get("colors"):
        main, accent = _colours(spec["colors"]) or main, None
    if "accent" in spec:
        accent = _colours(spec["accent"]) or None
    return list(main) or list(default[0]), (list(accent) if accent else None)


# --------------------------------------------------------------------------- #
# styles
# --------------------------------------------------------------------------- #
def _paint(bits, main, accent, scale=1):
    """A line bitmap to an image in the gradient, ``scale`` pixels per font pixel."""
    rows = [[c for c in row for _ in range(scale)] for row in bits for _ in range(scale)]
    h = len(rows)
    a, b = ramp(main, h), ramp(accent or main, h)
    return [[(b[y] if c == "l" else a[y]) if c else None for c in row] for y, row in enumerate(rows)]


def _stack(images, gap=2):
    """Images one under another, centred, ``gap`` pixel rows apart."""
    w = max(len(i[0]) for i in images)
    out = []
    for n, img in enumerate(images):
        left = (w - len(img[0])) // 2
        out.extend([None] * left + list(r) + [None] * (w - len(r) - left) for r in img)
        if n < len(images) - 1:
            out.extend([None] * w for _ in range(gap))
    return out


def _shift(img, dx, dy):
    h, w = len(img), len(img[0])
    out = [[None] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if img[y][x] and 0 <= x + dx < w and 0 <= y + dy < h:
                out[y + dy][x + dx] = img[y][x]
    return out


def _pad(img, left=0, right=0, top=0, bottom=0):
    w = len(img[0]) + left + right
    return ([[None] * w for _ in range(top)] + [[None] * left + list(r) + [None] * right for r in img]
            + [[None] * w for _ in range(bottom)])


def _over(*layers):
    h, w = len(layers[0]), len(layers[0][0])
    return [[next((L[y][x] for L in layers if L[y][x]), None) for x in range(w)] for y in range(h)]


def _recolour(img, fn):
    return [[fn(c, x, y) if c else None for x, c in enumerate(row)] for y, row in enumerate(img)]


def _image(lines, style, main, accent, scale):
    """The pixel image of a pixel-family style (before reflections and grids)."""
    gap = 3 if style == "glitch" else 1
    bits = [line_bitmap(t, gap) for t in lines]
    if style == "chrome":
        light, mid, dark = main[0], main[len(main) // 2], main[-1]
        alight = (accent or main)[0]
        amid, adark = (accent or main)[len(accent or main) // 2], (accent or main)[-1]

        def chrome(c, x, y, h):
            f = y / max(1, h - 1)
            l, m, d = (alight, amid, adark) if c == "l" else (light, mid, dark)
            if f < 0.45:
                return mix(l, m, f / 0.45)
            if f < 0.6:
                return d
            return mix(m, l, (f - 0.6) / 0.4)
        imgs = []
        for b in bits:
            rows = [[c for c in row for _ in range(scale)] for row in b for _ in range(scale)]
            imgs.append([[chrome(c, x, y, len(rows)) if c else None for x, c in enumerate(row)]
                         for y, row in enumerate(rows)])
        face = _pad(_stack(imgs), 0, 2, 0, 2)
        deep = [mix(dark, "#101828", 0.35), mix(dark, "#101828", 0.65)]
        layers = [face] + [_recolour(_shift(face, d, d), lambda c, x, y, d=d: deep[d - 1]) for d in (1, 2)]
        return _over(*layers)
    img = _stack([_paint(b, main, accent, scale) for b in bits])
    if style == "shadow":
        img = _pad(img, 0, 1, 0, 1)
        shade = mix(main[-1], "#000000", 0.6)
        return _over(img, _recolour(_shift(img, 1, 1), lambda c, x, y: shade))
    if style == "glitch":
        img = _pad(img, 1, 1)
        red = _recolour(_shift(img, -1, 0), lambda c, x, y: "#ff2a6d")
        cyan = _recolour(_shift(img, 1, 0), lambda c, x, y: "#05d9e8")
        return _over(img, red, cyan)
    return img


def _cells(lines, style, main, accent, scale, solid=False):
    """A finished drawing (Canvas) of the lines in the style."""
    if style in ("plain", "tight"):
        step = 2 if style == "plain" else 1
        w = max(step * len(t) - (step - 1) for t in lines)
        cv = Canvas(w, len(lines))
        for y, text in enumerate(lines):
            left = (w - (step * len(text) - (step - 1))) // 2
            cols = ramp(main, len(text))
            for i, ch in enumerate(text):
                accented = ch.islower() and accent
                cv.put(left + step * i, y, ch, "%s b" % ((accent or main)[0] if accented else cols[i]))
        return cv
    if style == "led":
        bits = _stack([[[(1 if c else 0) for c in row] for row in line_bitmap(t)] for t in lines], gap=1)
        bits = [[c or None for c in row] for row in bits]
        bits = _pad(bits, 1, 1, 0, 0)
        cols = ramp(main, len(bits))
        unlit = mix(main[-1], "#000000", 0.78)
        kinds = _stack([line_bitmap(t) for t in lines], gap=1)
        kinds = _pad(kinds, 1, 1, 0, 0)
        cv = Canvas(len(bits[0]), len(bits))
        for y, row in enumerate(bits):
            for x, on in enumerate(row):
                if on:
                    lower = kinds[y][x] == "l" and accent
                    cv.put(x, y, "●", ramp(accent, len(bits))[y] if lower else cols[y])
                else:
                    cv.put(x, y, "·", unlit)
        return cv
    if style == "dots":
        # each font pixel is 2x2 dots, with the inside corners of diagonal steps filled
        imgs = [_smooth(_paint(line_bitmap(t), main, accent, 2)) for t in lines]
        return braille(_stack(imgs, gap=4))
    img = _image(lines, style, main, accent, scale)
    cv = halfblock(img, solid)
    if style == "reflect":
        cv = _reflect(cv, img)
    elif style == "synthwave":
        cv = _grid(cv)
    return cv


def _smooth(img):
    """Fill the inside corner of each diagonal step of a doubled bitmap."""
    h, w = len(img), len(img[0])
    out = [list(r) for r in img]
    for y in range(0, h - 2, 2):
        for x in range(0, w - 2, 2):
            a, b = img[y][x], img[y][x + 2]
            c, d = img[y + 2][x], img[y + 2][x + 2]
            if a and d and not b and not c:
                out[y + 1][x + 2] = out[y + 2][x + 1] = a
            if b and c and not a and not d:
                out[y + 1][x + 1] = out[y + 2][x + 2] = b
    return out


def _reflect(cv, img):
    bottom = [row for row in reversed(img) if any(row)][:6]
    out = Canvas(cv.w, cv.h + 3)
    out.blit(cv, 0, 0)
    for r, (ch, amount) in enumerate((("▓", 0.55), ("▒", 0.7), ("░", 0.8))):
        pair = bottom[2 * r:2 * r + 2]
        for x in range(cv.w):
            c = next((row[x] for row in pair if x < len(row) and row[x]), None)
            if c and not (r == 2 and x % 2):
                out.put(x, cv.h + r, ch, mix(c, "#000000", amount))
    return out


def _grid(cv):
    out = Canvas(cv.w, cv.h + 4)
    out.blit(cv, 0, 0)
    hy, w = cv.h, cv.w
    for x in range(w):
        out.put(x, hy, "▁", "#ff3fa4")
        out.put(x, hy + 2, "─", "#8f3ac0")
    tint = ["#5a2a8f", "#8f3ac0", "#d24fe0"]
    cx = w // 2
    for r in range(1, 4):
        for k in range(-12, 13):
            x = cx + int(round(k * (1.4 + 2.2 * r)))
            out.put(x, hy + r, "│" if k == 0 else ("╱" if k < 0 else "╲"), tint[r - 1])
    return out


# --------------------------------------------------------------------------- #
# laying out and making the art
# --------------------------------------------------------------------------- #
def _wrap(text, width_of, max_px):
    """Words in as few lines as fit ``max_px``; None when one word is too long."""
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word) if cur else word
        if width_of(trial) <= max_px:
            cur = trial
        elif width_of(word) > max_px:
            return None
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or None


def _to_art(cv, ascii_cv, name, effect):
    return make_art(name, cv, None, ascii_cv, (), effect)


COLOUR_KEYS = ("palette", "colors", "accent")


def normalise(spec, text=None, theme=None, defaults=None):
    """A banner spec as a dict with every field filled in.

    What the spec leaves out comes from ``defaults`` (the game's ``"banner_defaults"``,
    its house style), then from the theme (``"banner"`` in its ``ui``), then from the
    style itself.  A game's colours apply to every style; the theme's only to its own."""
    if isinstance(spec, str):
        spec = {"text": spec}
    spec = dict(spec or {})
    game = dict(defaults or {}) if isinstance(defaults, dict) else {}
    themed = dict((theme.ui.get("banner") or {}) if theme is not None else {})
    style = str(spec.get("style") or game.get("style") or themed.get("style") or "pixel").lower()
    if style not in STYLES:
        style = "pixel"
    if not any(k in spec for k in COLOUR_KEYS):
        if any(k in game for k in COLOUR_KEYS):
            spec.update({k: game[k] for k in COLOUR_KEYS if k in game})
        elif themed.get("palette") and not spec.get("style") and not game.get("style"):
            spec["palette"] = themed["palette"]
    for key in ("effect", "scale"):
        if key not in spec and key in game:
            spec[key] = game[key]
    spec["style"] = style
    spec["text"] = str(spec.get("text") or text or "CLIo").strip() or "CLIo"
    if "effect" not in spec:
        spec["effect"] = STYLE_DEFAULTS[style][1]
    try:
        spec["scale"] = 2 if int(spec.get("scale", 1)) >= 2 else 1
    except (TypeError, ValueError):
        spec["scale"] = 1
    return spec


def make(spec, max_width=78, max_height=None, text=None, theme=None, palettes=None, defaults=None):
    """The banner as an :class:`~engine.art.Art` that fits ``max_width`` columns.

    Tries the style at its scale on one line, then wrapped, then at scale 1,
    then the ``plain`` style; returns None if not even that fits."""
    spec = normalise(spec, text, theme, defaults)
    style, words = spec["style"], spec["text"]
    main, accent = palette_of(spec, style, palettes)
    tries = [(style, s) for s in ((2, 1) if spec["scale"] == 2 else (1,))] + [("plain", 1), ("tight", 1)]
    for st, sc in tries:
        if st == "plain":
            layouts = [[words], _wrap(words, lambda t: 2 * len(t) - 1, max_width)]
        elif st == "tight":
            layouts = [[words], _wrap(words, len, max_width),
                       [w[:max_width] for w in words.split()]]
        else:
            per = 1 if st in ("led", "dots") else sc
            gap = 3 if st == "glitch" else 1
            extra = {"glitch": 2, "shadow": 1, "chrome": 2, "led": 2}.get(st, 0)
            layouts = [[words], _wrap(words, lambda t: text_width(t, gap) * per + extra, max_width)]
        for lines in layouts:
            if not lines:
                continue
            cv = _cells(lines, st, main, accent, sc)
            if cv.w <= max_width and (max_height is None or cv.h <= max_height):
                ascii_cv = _cells(lines, st, main, accent, sc, solid=True)
                art = _to_art(cv, ascii_cv, "banner", spec["effect"] if st == style else None)
                art.style = "plain" if st == "tight" else st
                return art
    return None


def export(spec, text=None, theme=None, widths=(74, 36), palettes=None, defaults=None):
    """A banner as one :class:`~engine.art.Art` to save as a file: the desktop size as
    ``@art``, a phone-sized ``@small`` when that is different, and ``@ascii``."""
    big = make(spec, widths[0], None, text, theme, palettes, defaults)
    if big is None:
        return None
    small = make(spec, widths[1], None, text, theme, palettes, defaults)
    if small is not None and small.size("art")[0] < big.size("art")[0]:
        rekey = {}
        for k, s in small.palette.items():
            found = next((bk for bk, bs in big.palette.items() if bs == s), None)
            if found is None:
                used = set(big.palette)
                found = next(c for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                             "!$%&*+-/<>?@^_~:;,()[]{}|'`\"\\" + "".join(chr(0xE100 + i) for i in range(400))
                             if c not in used)
                big.palette[found] = s
            rekey[k] = found
        lines, mask = small.variants["art"]
        big.variants["small"] = (lines, ["".join(rekey.get(c, c) if c not in " ." else c for c in m) for m in mask])
    big.name = "banner"
    return big
