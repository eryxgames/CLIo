# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Pictures for the editor: grow a sprite as the game would, say what colour a palette entry
is, and draw a banner of game.json or a sprite in its style as the game draws it.

The game draws a character with ``"sprite": "auto"`` by growing a creature from
its name (``engine.sprite.generate``).  ``grow`` returns that same creature as
data that can be written into ``sprites.json`` and then drawn over by hand.
"""
import io
import json
import os
import re

from .. import sprite
from ..term import idx256_to_rgb


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
    """One line of terminal output (colours of any depth) as runs: ``[[text, fg, bg, bold], ...]`` (colours ``#rrggbb`` or None)."""
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
            elif p in (38, 48) and i + 2 < len(ps) and ps[i + 1] == 5:      # one of 256
                at["fg" if p == 38 else "bg"] = _hex(idx256_to_rgb(ps[i + 2]))
                i += 2
            elif 30 <= p <= 37 or 90 <= p <= 97:                           # one of 16
                at["fg"] = _hex(idx256_to_rgb(p - 30 if p < 90 else p - 82))
            elif 40 <= p <= 47 or 100 <= p <= 107:
                at["bg"] = _hex(idx256_to_rgb(p - 40 if p < 100 else p - 92))
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


# a terminal the editor can show a picture in: colour depth, unicode, symbol set
TERMINALS = {"full": (3, True, "full"), "256": (2, True, "full"), "16": (1, True, "full"),
             "none": (0, True, "full"), "console": (2, True, "console"), "ascii": (2, False, "ascii")}
LOOK_SIZES = ((40, 20), (60, 24), (80, 24))


def as_terminal(rows, terminal="full"):
    """Rows of cells ``(char or None, fg, bg)`` as a terminal of some kind shows them: painted by the
    frame's own painter at that depth and in that font, and read back as runs for the page."""
    from ..frame import Painter
    from ..term import Term
    depth, uni, glyphs = TERMINALS.get(terminal, TERMINALS["full"])
    term = Term(out=io.StringIO(), color=depth, unicode=uni, env={}, glyphs=glyphs)
    paint = Painter(depth, {"console": term.subst}.get(glyphs) if uni else None)
    return [cells(paint.cells(list(r), uni)) for r in rows]


def model_look(game_dir, name, pending=None, view=None, cols=60, rows=24, terminal="full", yaw=30.0, pitch=20.0,
               turns=0):
    """A model as the game draws it in a console or the viewer: its look (the game's ``"model_look"``
    with the model's own ``"look"`` over it), in a view, at a size, on a terminal of some kind.

    Returns ``{"rows", "frames" (``turns`` pictures going round, when asked), "cols", "lines", "view":
    the view drawn, "views", "look": what was used, "from": {key: "model" | "game"}, "groups": its
    parts' names, "palettes": names a palette may be, "terminals", "problems"}``."""
    from .. import banner as banners
    from .. import model as model_mod
    from .. import viewer
    from ..data import GameData
    from . import EditorError, workdir
    with workdir(game_dir, pending) as work:
        data = GameData(work)
    models = getattr(data, "models", None) or {}
    if name not in models:
        raise EditorError("There is no model called %s." % name)
    cfg = data.config or {}
    base = cfg.get("model_look") if isinstance(cfg.get("model_look"), dict) else {}
    own = models[name].get("look") if isinstance(models[name].get("look"), dict) else {}
    cols, rows = max(20, min(120, int(cols or 60))), max(8, min(40, int(rows or 24)))
    out = {"rows": [], "frames": [], "cols": cols, "lines": rows, "views": list(viewer.VIEWS), "view": None,
           "look": {}, "from": {k: ("model" if k in own else "game") for k in viewer.LOOK_KEYS if k in own or k in base},
           "groups": [], "terminals": list(TERMINALS),
           "palettes": sorted(cfg.get("palettes") or {}) + [p for p in sorted(banners.PALETTES)
                                                             if p not in (cfg.get("palettes") or {})]}
    wrong = model_mod.problems({name: models[name]})
    wrong += [w for w in viewer.look_problems(data) if w.startswith(("game.json: model_look", "model '%s': look" % name))]
    if wrong:
        return dict(out, problems=wrong)
    built = model_mod.load({name: models[name]})[name]
    look = viewer.looks(data)[name]
    subject = viewer.Subject(built, look=look)
    view = view if view in viewer.VIEWS else (look.get("view") if look.get("view") in viewer.VIEWS else "shaded")
    uni = TERMINALS.get(terminal, TERMINALS["full"])[1]
    ink = None if look.get("ink") else "green"

    def seen(turn):
        return as_terminal(viewer.draw(subject, view, cols, rows, yaw=turn, pitch=float(pitch), colour=ink,
                                       unicode=uni), terminal)
    turns = max(0, min(24, int(turns or 0)))
    return dict(out, problems=[], view=view, rows=seen(float(yaw)), groups=list(subject.groups),
                frames=[seen(float(yaw) + 360.0 * k / turns) for k in range(turns)],
                look={k: v for k, v in look.items() if k in viewer.LOOK_KEYS})


def console(game_dir, name, pending=None, moment=0.0, cols=112, rows=34, terminal="full"):
    """A simulator's screen as the game draws it, at a moment of the autopilot's run - from what is on
    the page, saved or not - with whether it can be done, what is wrong with it, where widgets can be
    put (each panel that holds widgets: its path in the layout and its title) and every widget there
    is with the JSON that makes it."""
    import json
    from .. import panels, shots
    from .. import sim as sims
    from ..data import GameData
    from . import EditorError, workdir
    with workdir(game_dir, pending) as work:
        data = GameData(work)
    if name not in (data.sims or {}):
        raise EditorError("There is no simulator called %s." % name)
    cols, rows = max(40, min(200, int(cols or 112))), max(14, min(70, int(rows or 34)))
    wrong = [w for w in sims.problems(data) if w.startswith("sim '%s'" % name)]
    places = []

    def walk(node, path, said):
        if not isinstance(node, dict):
            return
        title = str(node.get("title") or said)
        if isinstance(node.get("widgets"), list):
            places.append({"path": path, "title": title, "widgets": [next((k for k in panels.WIDGETS if k in w), "?")
                                                                     for w in node["widgets"] if isinstance(w, dict)]})
        for key in ("cols", "rows"):
            for i, child in enumerate(node.get(key) or []):
                walk(child, path + [key, i], "%s %s %d" % (title, key[:-1], i + 1))
    spec = data.sims[name]
    walk(spec.get("panels"), [], "the screen")
    out = {"rows": [], "cols": cols, "lines": rows, "verdict": "", "result": None, "problems": wrong, "places": places,
           "has_panels": isinstance(spec.get("panels"), dict),
           "widgets": [{"kind": k, "what": what, "spec": json.loads(js)} for k, what, js, _cells in panels.gallery(48)]}
    if wrong:
        return out
    try:
        out.update(shots.console(data, name, moment, (cols, rows), terminal))
    except Exception as err:                                # data the simulator cannot be made of is the person's to see
        out["problems"] = ["It cannot be drawn like this: %s" % err]
    return out


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


def sheet(game_dir, what="monsters", scale=4, labels=True, background="clear", fmt="png", pending=None):
    """A sheet of the game's pictures (see :mod:`engine.sheets`): the PNG's bytes, or its atlas."""
    from .. import sheets
    from ..data import GameData
    from . import EditorError, workdir
    if what not in sheets.WHAT:
        raise EditorError("A sheet is of %s." % ", ".join(sheets.WHAT))
    try:
        scale = max(1, min(16, int(scale)))
    except (TypeError, ValueError):
        raise EditorError("The scale is a whole number, 1 to 16.")
    with workdir(game_dir, pending) as work:
        data = GameData(work)
        if data.id == os.path.basename(work):                # no id of its own: the folder's name
            data.id = os.path.basename(os.path.abspath(game_dir))
    png, atlas = sheets.sheet(data, what, scale, bool(labels), sheets.DARK if background == "dark" else None)
    return atlas if fmt == "atlas" else png


def end_screen(game_dir, pending=None, width=100, height=34):
    """The end screen of game.json as the game draws it: ``{"frames": [rows per picture], "every": seconds,
    "size": [w, h]}``, with made-up numbers for the totals (the game counts the real ones)."""
    from .. import ending
    from ..data import GameData
    from . import workdir
    width, height = max(50, min(160, int(width or 100))), max(18, min(60, int(height or 34)))
    with workdir(game_dir, pending) as work:
        data = GameData(work)
        shown = ending.preview(data, width, height)
    return {"frames": [[cells(l) for l in lines] for lines in shown["lines"]], "every": shown["every"],
            "size": [width, height]}


def _pixels_of(body):
    """The picture a request carries: ``png`` (the file, base64) or ``rgba`` (base64) with ``w`` and ``h``."""
    import base64
    from .. import sheets
    from . import EditorError
    try:
        if body.get("png"):
            _w, _h, rows = sheets.read_png(base64.b64decode(body["png"]))
            return rows
        if body.get("rgba"):
            return sheets.from_rgba(base64.b64decode(body["rgba"]), body.get("w"), body.get("h"))
    except sheets.PictureError as err:
        raise EditorError(str(err))
    except (ValueError, TypeError):
        raise EditorError("The picture did not come through whole.")
    raise EditorError("No picture was sent.")


def from_image(body):
    """A picture made a sprite (see :func:`engine.sheets.to_sprite`)."""
    from .. import sheets
    from . import EditorError
    rows = _pixels_of(body)
    try:
        made = sheets.to_sprite(rows, height=body.get("height") or None, colours=body.get("colours") or 16,
                                clear=body.get("clear") or "alpha", base=body.get("base") or None,
                                outline=bool(body.get("outline")), clear_at=body.get("clear_at") or (),
                                specks=body.get("specks", True), limit=int(body.get("limit") or 64))
    except sheets.PictureError as err:
        raise EditorError(str(err))
    made["size"] = [len(made["pixels"][0]), len(made["pixels"])]
    made["source"] = [len(rows[0]), len(rows)]
    return made


def sheet_back(game_dir, body, pending=None):
    """An edited sheet taken back: ``{"files": {key: data that changed}, "report"}`` - nothing written."""
    from .. import sheets
    from . import EditorError, current
    rows = _pixels_of(body)
    atlas = body.get("atlas")
    if isinstance(atlas, str):
        try:
            atlas = json.loads(atlas)
        except ValueError:
            raise EditorError("The atlas is not JSON: take the .json written with the sheet.")
    if not isinstance(atlas, dict):
        raise EditorError("The atlas (the .json written with the sheet) is needed too.")
    files = current(game_dir, pending)
    try:
        return sheets.import_sheet(files, rows, atlas)
    except sheets.PictureError as err:
        raise EditorError(str(err))
