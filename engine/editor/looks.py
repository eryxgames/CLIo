# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Pictures for the editor: grow a sprite as the game would, say what colour a palette entry
is, and draw a banner of game.json or a sprite in its style as the game draws it.

The game draws a character with ``"sprite": "auto"`` by growing a creature from
its name (``engine.sprite.generate``).  ``grow`` returns that same creature as
data that can be written into ``sprites.json`` and then drawn over by hand.
"""
import io
import re

from .. import sprite


def _hex(rgb):
    return None if rgb is None else "#%02x%02x%02x" % tuple(int(v) for v in rgb)


def grow(seed, size=12):
    """The sprite the game would grow from ``seed``, as ``{"palette": {letter: "#rrggbb"}, "pixels": [rows]}``."""
    size = max(6, min(32, int(size or 12)))
    made = sprite.generate(str(seed), size)
    used = set("".join(made.pixels))
    return {"palette": {k: _hex(v) for k, v in made.palette.items() if v is not None and k in used},
            "pixels": list(made.pixels)}


def monster(seed, body="biped", size=18):
    """A figure grown from words on a body plan (``engine.sprite.BODIES``), as sprites.json data with far versions."""
    made = sprite.monster(str(seed), body if body in sprite.BODIES else "biped", max(10, min(48, int(size or 18))))
    made["bodies"] = dict(sprite.BODIES)
    return made


def far(pixels, keep=""):
    """The smaller drawings a level shows from far away, made from ``pixels`` (``keep``: letters that must stay)."""
    rows = [str(r) for r in pixels or [] if isinstance(r, str)]
    return {"lod": [{"pixels": r} for r in sprite.far_versions(rows, str(keep or ""))] if rows else []}


def distances(data, size=1.0, steps=6):
    """How a sprite looks in a first-person level at 1..``steps`` cells: for each, the drawing used
    (0 the sprite itself, 1.. its far versions) and the pixels as the level scales them, as colours."""
    from ..firstperson import DECAY, Picture, View
    data = data or {}
    pal = {k: sprite._rgb(v) for k, v in (data.get("palette") or {}).items()}
    pixels = [str(r) for r in data.get("pixels") or [] if isinstance(r, str)]
    if not pixels:
        return {"distances": []}
    lod = data.get("lod") if isinstance(data.get("lod"), list) else None
    drawings = [d.get("pixels") if isinstance(d, dict) else d for d in lod] if lod else \
        sprite.far_versions(pixels, str(data.get("keep") or ""))
    smaller = [Picture([[pal.get(ch) for ch in str(r)] for r in rows]) for rows in drawings if rows]
    pic = Picture([[pal.get(ch) for ch in r] for r in pixels], [p for p in smaller if p.h and p.w])
    view = View(80, 17, "pixel")
    out = []
    for d in range(1, steps + 1):
        target = pic.h * DECAY ** d * view.K * float(size or 1.0)
        pp = pic.pick(target)
        s = target / pp.h
        w, h = max(1, int(round(pp.w * s))), max(1, int(round(pp.h * s)))
        rows = [[_hex(pp.rows[min(pp.h - 1, int(j / s))][min(pp.w - 1, int(i / s))]) for i in range(w)] for j in range(h)]
        out.append({"cells": d, "drawing": 0 if pp is pic else 1 + smaller.index(pp), "made": not lod, "pixels": rows})
    return {"distances": out}


def colours(palette):
    """``{letter: "#rrggbb" or None}`` for a palette written in any way the engine accepts (names, numbers, hex)."""
    return {str(k): _hex(sprite._rgb(v)) for k, v in (palette or {}).items()}


# ------------------------------------------------------------------------- banners
BANNERS = ("title_banner", "win_banner", "lose_banner", "banner_defaults")
_SGR = re.compile(r"\x1b\[([0-9;]*)m")
_INK, _SCREEN = "#c8cfdb", "#0b0e14"


def cells(line):
    """One line of truecolour terminal output as runs: ``[[text, fg, bg, bold], ...]`` (colours ``#rrggbb`` or None)."""
    runs, at = [], {"fg": None, "bg": None, "b": False, "d": False, "v": False}

    def add(text):
        if not text:
            return
        fg, bg = at["fg"], at["bg"]
        if at["v"]:
            fg, bg = bg or _SCREEN, fg or _INK
        if at["d"]:
            a, b = sprite._rgb(fg or _INK), sprite._rgb(bg or _SCREEN)
            fg = _hex(tuple(x + (y - x) * 0.45 for x, y in zip(a, b)))
        run = [text, fg, bg, at["b"]]
        if runs and runs[-1][1:] == run[1:]:
            runs[-1][0] += text
        else:
            runs.append(run)

    pos = 0
    for m in _SGR.finditer(line):
        add(line[pos:m.start()])
        pos = m.end()
        ps = [int(p) if p else 0 for p in m.group(1).split(";")]
        i = 0
        while i < len(ps):
            p = ps[i]
            if p == 0:
                at.update(fg=None, bg=None, b=False, d=False, v=False)
            elif p in (1, 2, 7):
                at[{1: "b", 2: "d", 7: "v"}[p]] = True
            elif p == 22:
                at.update(b=False, d=False)
            elif p == 27:
                at["v"] = False
            elif p in (39, 49):
                at["fg" if p == 39 else "bg"] = None
            elif p in (38, 48) and i + 4 < len(ps) and ps[i + 1] == 2:
                at["fg" if p == 38 else "bg"] = _hex(ps[i + 2:i + 5])
                i += 4
            i += 1
    add(line[pos:])
    return runs


def banner(game_dir, key, width=78, pending=None):
    """A banner of game.json drawn as the game would draw it on a screen ``width`` columns wide.

    Returns ``{"rows": [runs per line], "frames": [[rows, seconds], ...], "reveals",
    "style": the style it is drawn in (a banner too wide for the screen falls back to
    plain), "chosen": the style asked for, "effect", "size": [w, h]}``."""
    from .. import banner as banners
    from ..data import GameData
    from ..term import Term
    from ..theme import load_theme
    from . import EditorError, workdir
    if key not in BANNERS:
        raise EditorError("There is no banner called %s." % key)
    width = max(24, min(160, int(width or 78)))
    with workdir(game_dir, pending) as work:
        data = GameData(work)
        cfg = dict(data.config)
        theme = load_theme(data.theme, game_dir)
    spec = cfg.get(key) or {}
    text = {"win_banner": "The End", "lose_banner": "Game Over"}.get(key, cfg.get("title") or data.title)
    defaults = None if key == "banner_defaults" else cfg.get("banner_defaults")
    art = banners.make(spec, width - 4, None, text=text, theme=theme, palettes=cfg.get("palettes"), defaults=defaults)
    if art is None:
        return {"rows": [], "frames": [], "reveals": False, "style": None, "chosen": None, "effect": None, "size": [0, 0]}
    term = Term(out=io.StringIO(), width=width, height=40, color=3, unicode=True, env={})
    frames, reveals = art.animation(term, width - 4, None, None, seed=data.id)
    chosen = banners.normalise(spec, text, theme, defaults)
    return {"rows": [cells(l) for l in art.render(term)],
            "frames": [[[cells(l) for l in fr], round(secs, 3)] for fr, secs in frames],
            "reveals": reveals, "style": getattr(art, "style", chosen["style"]), "chosen": chosen["style"],
            "effect": (art.effect or {}).get("name"), "size": list(art.size("art"))}


def picture(game_dir, name, pending=None):
    """A sprite drawn in its style, as scenes, portraits and the title screen show it.

    Returns ``{"rows", "frames", "reveals", "style", "effect", "size": [w, h],
    "small": [w, h] of the version for narrow screens or None}``."""
    from ..data import GameData
    from ..pixels import picture as make_picture
    from ..term import Term
    from . import EditorError, workdir
    with workdir(game_dir, pending) as work:
        data = GameData(work)
        sprites = dict(data.sprites or {})
    sp = sprites.get(name)
    if not isinstance(sp, dict) or not sp.get("pixels"):
        raise EditorError("There is no sprite called %s, or it has no pixels." % name)
    art = make_picture(sp, name)
    term = Term(out=io.StringIO(), width=160, height=60, color=3, unicode=True, env={})
    frames, reveals = art.animation(term, None, None, None, seed=name)
    return {"rows": [cells(l) for l in art.render(term)],
            "frames": [[[cells(l) for l in fr], round(secs, 3)] for fr, secs in frames],
            "reveals": reveals, "style": sp.get("style") or "pixel",
            "effect": (art.effect or {}).get("name") or ("frames" if art.frames else None),
            "size": list(art.size("art")), "small": list(art.size("small")) if "small" in art.variants else None}
