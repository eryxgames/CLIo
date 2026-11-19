# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""First-person levels in the editor: what a map's characters mean, the tiles and their small
pictures, the level seen from any cell, a tile on the walls of a room, a weapon in the hands,
and the level bot's verdict.

Pictures are the engine's own (``engine.firstperson.View``), sent as runs of terminal cells
(``[[text, fg, bg, bold], ...]`` a row), which the page paints as a terminal does.
"""
from .. import firstperson, levelbot, sprite
from ..data import GameData
from ..level import FACING, LEGEND, Level
from . import EditorError, workdir

# a small room for trying tiles and weapons in: a corridor opening into it, the player in the corridor
DEMO = ["#########",
        "#.......#",
        "#.......#",
        "###...###",
        "###...###",
        "###.@.###",
        "#########"]


def _hex(rgb):
    return None if rgb is None else "#%02x%02x%02x" % tuple(int(v) for v in rgb)


def runs(cells):
    """The cells of a picture (``(char or None, fg, bg)``; None is a pair of pixels) as runs of text."""
    rows = []
    for row in cells:
        out = []
        for ch, fg, bg in row:
            run = ["▀" if ch is None else ch, _hex(fg), _hex(bg), False]
            if out and out[-1][1:] == run[1:]:
                out[-1][0] += run[0]
            else:
                out.append(run)
        rows.append(out)
    return rows


def _thumb(rows, size=8):
    """A drawing of colours shrunk to ``size`` x ``size`` (nearest pixel), as hex; None is clear."""
    h, w = len(rows), len(rows[0]) if rows else 0
    if not h or not w:
        return []
    return [[_hex(rows[min(h - 1, int((y + 0.5) * h / size))][min(w - 1, int((x + 0.5) * w / size))])
             for x in range(size)] for y in range(size)]


def _game(game_dir, pending):
    with workdir(game_dir, pending) as work:
        return GameData(work)


def info(game_dir, pending=None):
    """What the map painter needs: the engine's legend, every tile's name and small picture, and the
    pictures of the monsters and items a map can hold."""
    data = _game(game_dir, pending)
    tiles = {}
    for name, rows in firstperson.TEXTURES.items():
        tiles[name] = {"own": False, "thumb": _thumb(rows)}
    for name, t in (data.tiles or {}).items():
        frames = firstperson.tile_frames(t) if isinstance(t, dict) else []
        if frames:
            tiles[name] = {"own": True, "thumb": _thumb(frames[0]), "engine": name in firstperson.TEXTURES}

    def picture(name):
        sp = (data.sprites or {}).get(name)
        if not isinstance(sp, dict) or not sp.get("pixels"):
            return None
        pal = {k: _hex(sprite._rgb(v)) for k, v in (sp.get("palette") or {}).items()}
        return [[pal.get(ch) for ch in r] for r in sp["pixels"]]

    things = {}
    for mid, spec in (data.monsters or {}).items():
        if isinstance(spec, dict):
            things[mid] = {"kind": "monster", "name": spec.get("name") or mid, "tag": spec.get("tag") or mid[0],
                           "boss": bool(spec.get("boss")), "picture": picture(spec.get("sprite") or mid)}
    for iid, spec in (data.items or {}).items():
        pk = spec.get("pickup") if isinstance(spec, dict) else None
        if isinstance(pk, dict) and iid not in things:
            things[iid] = {"kind": "item", "name": spec.get("name") or iid, "picture": picture(pk.get("sprite") or iid)}
    crate = picture("crate") or [[_hex(c) for c in row] for row in firstperson.CRATE.rows]
    things.setdefault("crate", {"kind": "fixture", "name": "crate", "picture": crate})
    return {"legend": LEGEND, "tiles": tiles, "things": things, "facing": ["n", "e", "s", "w"]}


def engine_tile(name):
    """One of the engine's tiles as tiles.json data, to start a game's own tile from."""
    made = firstperson.tile_data(str(name))
    if made is None:
        raise EditorError("The engine has no tile called %s." % name)
    return made


def _picture(lv, style="pixel", W=80, VR=17, fx=None, phase=0):
    return runs(firstperson.View(W, VR, style).render(lv, fx or firstperson.FX(), phase))


def view(game_dir, level_id, x, y, facing, style="pixel", pending=None, width=80):
    """The level as the player sees it from cell ``(x, y)``, facing n, e, s or w, before anything moves."""
    data = _game(game_dir, pending)
    if level_id not in (data.levels or {}):
        raise EditorError("There is no level called %s." % level_id)
    try:
        lv = Level(data, level_id, seed=1)
    except Exception as err:                                 # a map too broken to build is the person's to see
        raise EditorError("The level cannot be built like this: %s" % err)
    p = lv.player
    if x is not None and y is not None:
        p.x, p.y = int(x), int(y)
    if facing is not None:
        p.facing = FACING.get(str(facing).lower(), p.facing) if not isinstance(facing, int) else facing % 4
    lv.update_seen()
    W = max(40, min(160, int(width or 80)))
    VR = max(11, round(W * 17 / 80))
    here = lv.cell(p.x, p.y)
    return {"rows": _picture(lv, style if style in firstperson.STYLES else "pixel", W, VR), "cols": W, "lines": VR,
            "at": [p.x, p.y], "facing": "nesw"[p.facing], "inside": bool(here.solid),
            "seen": sorted("%s %s" % (m.tag, m.name) for m in lv.visible())}


def _demo(data, legend, weapon=None):
    """The demo room as a level of ``data``: a tile on its walls, floor or ceiling; a weapon in the hands."""
    data.levels = dict(data.levels or {})
    data.levels["__demo__"] = {"name": "demo", "map": list(DEMO), "legend": legend, "facing": "n"}
    lv = Level(data, "__demo__", seed=1)
    if weapon is None:
        lv.weapons = {}
    else:
        lv.player.weapons = [weapon]
        lv.player.weapon = weapon
        for w in lv.weapons.values():                       # plenty to fire with
            if w.get("ammo"):
                lv.player.ammo[w["ammo"]] = 99
    return lv


def tile_view(game_dir, name, where="wall", pending=None, phase=0):
    """A tile on the walls of the demo room - or under it, or over it - as a level draws it."""
    data = _game(game_dir, pending)
    if where == "floor":
        legend = {".": {"floor": name}, "@": {"start": True, "floor": name}}
    elif where == "ceiling":
        legend = {".": {"ceiling": name}, "@": {"start": True, "ceiling": name}}
    else:
        legend = {"#": {"wall": name}}
    lv = _demo(data, legend)
    frames = len(lv.tiles.get(name) or [None])
    return {"rows": _picture(lv, phase=phase), "cols": 80, "lines": 17,
            "frames": [_picture(lv, phase=k) for k in range(1, min(frames, 8))] if frames > 1 else []}


def weapon_view(game_dir, weapon_id, pending=None):
    """A weapon held in the demo room, and the frames of one shot (or punch) as a level plays them."""
    data = _game(game_dir, pending)
    lv = _demo(data, {}, weapon=str(weapon_id))
    w = lv.weapons.get(str(weapon_id))
    if w is None:
        raise EditorError("There is no weapon %s." % weapon_id)
    if w.get("kind") == "melee":
        fxs = [firstperson.FX(recoil=-2), firstperson.FX(recoil=-3), firstperson.FX(recoil=-1), firstperson.FX()]
    else:
        fxs = [firstperson.FX(muzzle=True, recoil=1), firstperson.FX(muzzle=True, recoil=2), firstperson.FX(recoil=1),
               firstperson.FX()] * max(1, int(w.get("burst", 1)))
    return {"rows": _picture(lv), "frames": [_picture(lv, fx=f) for f in fxs], "cols": 80, "lines": 17,
            "sprite": w.get("sprite"), "drawn": bool(lv.sprites.get(w.get("sprite")))}


def check(game_dir, level_id, pending=None, runs_=5):
    """The level bot plays the level ``runs_`` times: how far it gets, and what the level holds."""
    data = _game(game_dir, pending)
    if level_id not in (data.levels or {}):
        raise EditorError("There is no level called %s." % level_id)
    try:
        return levelbot.check(data, level_id, max(1, min(10, int(runs_ or 5))))
    except Exception as err:
        raise EditorError("The level cannot be played like this: %s" % err)
