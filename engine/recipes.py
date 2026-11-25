# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""Recipes: working pieces pasted into a game's files - ``python clio.py GAME --add KIND NAME``.

    python clio.py mygame --add console reactor          # a console, its scene, and what it shows
    python clio.py mygame --add console bay --as airlock # under a name of your own
    python clio.py mygame --add menu wheel               # a menu of the game's own, in a look
    python clio.py mygame --add model door               # a model whose parts move (tracks)
    python clio.py mygame --add console list             # what there is

A console comes from one of CLIo's own games (the station starter, Erebus: Last Watch) as it is
there: its simulator into ``sims.json``, the models and planets its panels show (those the game
has none of by that name), and a scene that runs it - reached from the game's first scene, setting
the flag ``<id>_done`` when it is done and coming back. Nothing the game has is changed or
replaced; what was written is said, and the game is checked afterwards. Then it is yours to change.
"""
from __future__ import annotations

import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATION, EREBUS = os.path.join(ROOT, "templates", "station"), os.path.join(ROOT, "games", "erebus")

CONSOLES = {      # name: (where it is, its sim there, what it is)
    "reactor": (STATION, "reactor", "two controls, a function done at once and one held; gauges, a big number, lamps, plots, a model by heat"),
    "scan": (STATION, "scan", "a beam held on a drifting target; a model coming into a scope, a planet and its relief, a held function that ends it"),
    "helm": (STATION, "helm", "a hover craft flown by marks to a pad: the view ahead in lines, the map, a scan of the ground"),
    "bay": (EREBUS, "bay", "a switch, a control and two held functions that have to be done in order; a hatch as far open as a value says"),
    "approach": (EREBUS, "approach", "the view ahead as space: rocks, marks to fly by, a ring to stop in"),
}
MENUS = {
    "wheel": ("parts round a hub: orders, one locked until another is done, a value, one held to be done",
              {"title": "Orders", "look": "wheel", "hub": "Watch", "items": [
                  {"id": "first", "label": "First", "state": "ready", "tone": "good", "hint": "Something to do.",
                   "effects": [{"set": "first_done"}, {"say": "Done."}], "again": True},
                  {"id": "second", "label": "Second", "state": "ready", "hint": "Open once the first is done.",
                   "locked": "!first_done", "why": "Do the first one first.", "effects": [{"say": "And the second."}], "again": True},
                  {"id": "power", "kind": "slide", "label": "Power", "var": "power", "low": 0, "high": 100, "step": 10, "unit": "%",
                   "hint": "Left and right."},
                  {"id": "launch", "label": "Launch", "hold": True, "tone": "hot", "hint": "Enter arms it; hold Enter and it goes.",
                   "effects": [{"say": "Away."}]},
                  {"id": "close", "label": "Close", "hint": "Back."}]}),
    "ring": ("things round a dial with a needle: a short list of things to do",
             {"title": "Bay", "look": "ring", "items": [
                 {"id": "probe", "label": "Probe", "hint": "A probe away.", "effects": [{"say": "The probe drops away."}], "again": True},
                 {"id": "lamps", "kind": "check", "label": "Lamps", "flag": "lamps", "hint": "On or off."},
                 {"id": "close", "label": "Close", "hint": "Back."}]}),
    "bar": ("a lit line that moves, with a page of values behind one item",
            {"title": "Console", "look": "bar", "items": [
                {"id": "status", "label": "Status", "hint": "How things stand.", "effects": [{"say": "All quiet."}], "again": True},
                {"label": "Settings", "items": [
                    {"id": "alarm", "kind": "check", "label": "Alarm", "flag": "alarm"},
                    {"id": "level", "kind": "slide", "label": "Level", "var": "level", "low": 0, "high": 10}]},
                {"id": "close", "label": "Close"}]}),
}
MODELS = {
    "door": ("a leaf on a hinge and a bolt, opened by a clip of tracks (show it with a scope's \"clip\" and \"at\")",
             {"materials": {"steel": {"color": "#b4bac2", "metal": 0.7, "rough": 0.45}, "dark": {"color": "#4a5058", "metal": 0.4, "rough": 0.7}},
              "parts": [{"shape": "box", "size": [0.15, 0.15, 2.0], "at": [0, 0, 1.0], "material": "dark"},
                        {"shape": "box", "size": [1.2, 0.1, 1.9], "at": [0.65, 0, 1.0], "material": "steel", "group": "leaf"},
                        {"shape": "box", "size": [0.3, 0.06, 0.08], "at": [1.2, 0.08, 1.0], "material": "dark", "group": "bolt"}],
              "look": {"view": "solid"},
              "tracks": {"open": {"length": 2, "loop": False, "parts": {
                  "bolt": {"t": [0, 0.5, 2], "move": [[0, 0, 0], [-0.3, 0, 0], [-0.3, 0, 0]]},
                  "leaf": {"t": [0, 0.5, 2], "about": [0, 0, 1.0], "turn": [[0, 0, 0], [0, 0, 0], [95, 0, 0]]}}}}}),
    "beacon": ("a tripod that unfolds and a mast that rises (Erebus's)", (EREBUS, "beacon")),
    "hauler": ("a simple cargo hauler in named groups, for the structure, plan and heat views", (STATION, "hauler")),
    "soldier": ("a soldier moved by CLIo Motion: he strides, levels his rifle and fires, staggers, falls and lies",
                {"motion": "soldier"}),
    "hound": ("a hound moved by CLIo Motion: it trots and runs, bites, falls and lies", {"motion": "hyena"}),
    "walker": ("a two-legged machine moved by CLIo Motion, a cell high, that comes apart part by part",
               {"motion": {"character": "mech", "scale": 0.2}, "break": "parts"}),
}
KINDS = {"console": CONSOLES, "menu": MENUS, "model": MODELS}


class RecipeError(Exception):
    pass


def _read(folder, name):
    path = os.path.join(folder, name + ".json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(folder, name, data):
    """A file of the game: by the editor where it has a page for it (its layout and a backup kept), else plainly."""
    from . import editor, schema
    if name in schema.BY_FILE and os.path.isfile(os.path.join(folder, name + ".json")):
        editor.save(folder, name, data)
        return
    with open(os.path.join(folder, name + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def _free(name, taken):
    if name not in taken:
        return name
    n = 2
    while "%s%d" % (name, n) in taken:
        n += 1
    return "%s%d" % (name, n)


def _named(spec, key, out):
    """The names a console's panels show: ``{"scope": {"model": X}}``, ``{"planet": X}``, a scan's planet."""
    if isinstance(spec, dict):
        sc = spec.get("scope")
        if key == "models" and isinstance(sc, dict) and isinstance(sc.get("model"), str):
            out.add(sc["model"])
        if key == "planets":
            if isinstance(spec.get("planet"), str):
                out.add(spec["planet"])
            if isinstance(spec.get("scan"), dict) and isinstance(spec["scan"].get("planet"), str):
                out.add(spec["scan"]["planet"])
        for v in spec.values():
            _named(v, key, out)
    elif isinstance(spec, list):
        for v in spec:
            _named(v, key, out)
    return out


def listing(kind=None):
    """What there is to add, as lines."""
    out = []
    for k, table in KINDS.items():
        if kind in (None, k):
            out += ["%s %s: %s" % (k, name, entry[2] if k == "console" else entry[0]) for name, entry in table.items()]
    return out


def add(game_dir, kind, name, as_id=None):
    """Paste the recipe into the game. Returns the lines that say what was written. RecipeError if
    there is no such recipe, no such game, or the name asked for is taken."""
    from .data import GameData
    table = KINDS.get(kind)
    if table is None or name not in table:
        raise RecipeError("There is no %s called '%s'. There is:\n  %s" % (kind, name, "\n  ".join(listing(kind if table else None))))
    if _read(game_dir, "game") is None:
        raise RecipeError("%s has no game.json: it is not a game's folder." % game_dir)
    said = []
    if kind == "menu":
        menus = _read(game_dir, "menus") or {}
        mid = as_id or _free(name, menus)
        if mid in menus:
            raise RecipeError("The game has a menu called '%s' already." % mid)
        menus[mid] = copy.deepcopy(table[name][1])
        _write(game_dir, "menus", menus)
        said.append('menus.json: the menu "%s" (%s). An effect {"menu": "%s"} opens it - in a scene\'s action, say.'
                    % (mid, table[name][0], mid))
    elif kind == "model":
        models = _read(game_dir, "models") or {}
        mid = as_id or _free(name, models)
        if mid in models:
            raise RecipeError("The game has a model called '%s' already." % mid)
        spec = table[name][1]
        if isinstance(spec, tuple):
            spec = (_read(spec[0], "models") or {}).get(spec[1])
        models[mid] = copy.deepcopy(spec)
        _write(game_dir, "models", models)
        clips = list((models[mid].get("tracks") or {}))
        if models[mid].get("motion") is not None:
            more = ' A level\'s monster with "model": "%s" walks, attacks and falls with it.' % mid
        else:
            more = (' A panel shows it moving with {"scope": {"model": "%s", "view": "solid", "clip": "%s", "at": VALUE}}.'
                    % (mid, clips[0]) if clips else "")
        said.append('models.json: the model "%s" (%s).%s python clio.py GAME --view-model %s shows it.' % (
            mid, table[name][0], more, mid))
    else:
        source, sim_id, what = table[name]
        sims = _read(game_dir, "sims") or {}
        scenes = _read(game_dir, "scenes")
        if scenes is None:
            raise RecipeError("The game has no scenes.json to put the console's scene in.")
        taken = set(sims) | {s.get("id") for s in (scenes if isinstance(scenes, list) else scenes.values()) if isinstance(s, dict)} \
            | (set(scenes) if isinstance(scenes, dict) else set())
        cid = as_id or _free(name, taken)
        if cid in taken:
            raise RecipeError("The game has a scene or a simulator called '%s' already." % cid)
        spec = copy.deepcopy(_read(source, "sims")[sim_id])
        sims[cid] = spec
        for key in ("models", "planets"):                # what its panels show, where the game has none by that name
            needs = sorted(_named(spec.get("panels"), key, set()))
            have = _read(game_dir, key) or {}
            given = _read(source, key) or {}
            new = [n for n in needs if n not in have and n in given]
            for n in new:
                have[n] = copy.deepcopy(given[n])
            if new:
                _write(game_dir, key, have)
                said.append("%s.json: %s (what its panels show)." % (key, ", ".join(new)))
            kept = [n for n in needs if n in have and n not in new]
            if kept:
                said.append("%s.json: the game's own %s is shown (it was there)." % (key, ", ".join(kept)))
        _write(game_dir, "sims", sims)
        first = (_read(game_dir, "game") or {}).get("initial_scene")
        listed = scenes if isinstance(scenes, list) else list(scenes.values())
        home = next((s for s in listed if isinstance(s, dict) and s.get("id") == first), None) or \
            (scenes.get(first) if isinstance(scenes, dict) else None) or next((s for s in listed if isinstance(s, dict)), None)
        back = [{"goto": home["id"] if home and home.get("id") else first}] if (home or first) else []
        title = str(spec.get("title") or cid).split("  ")[0].title()
        scene = {"id": cid, "name": title, "description": "The %s console." % title.lower(), "sim": cid, "exits": [],
                 "on_sim_done": [{"say": "%s: done." % title}, {"set": cid + "_done"}] + back,
                 "on_sim_fail": [{"say": "%s: not this time." % title}] + back, "on_sim_quit": list(back)}
        if isinstance(scenes, list):
            scenes.append(scene)
        else:
            scenes[cid] = scene
        if home is not None:
            home.setdefault("exits", []).append({"door_name": title, "scene_id": cid})
        _write(game_dir, "scenes", scenes)
        said.insert(0, 'sims.json: the simulator "%s" (%s).' % (cid, what))
        said.append('scenes.json: the scene "%s" runs it%s. Done, it sets the flag "%s_done" and comes back.' % (
            cid, ', reached from "%s" (go %s)' % (home.get("name") or home.get("id"), title.lower()) if home else "", cid))
        said.append("python -m engine.sim %s %s lets the autopilot try it; python clio.py GAME --shots DIR draws it." % (game_dir, cid))
    wrong = GameData(game_dir).validate()
    said.append("The game checks clean." if not wrong else "The game now has %d problem(s):\n  %s" % (len(wrong), "\n  ".join(wrong[:8])))
    return said
