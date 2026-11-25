# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""JSON Schema for a game's files, written from what the editor knows (engine/schema.py), so any editor
that reads JSON Schema - VS Code among them - completes keys, says what each is for, and marks a
wrong type as it is typed: ``python clio.py --schema DIR``.

One file a data file (``clio-scenes.schema.json``...), a schema for a console's panels' widgets
(``clio-sims``), and ``vscode-settings.json`` - the lines that tie each schema to its file by name,
to paste into a workspace's ``.vscode/settings.json``. The schemas describe; they forbid nothing a
game may have: keys they do not know pass. ``--check`` stays the judge of a game.
"""
from __future__ import annotations

import json
import os

DRAFT = "http://json-schema.org/draft-07/schema#"
WIDGET_KEYS = {
    "gauge": "A value as a bar with its number (max, unit, label, warn, hot).",
    "center": "A value about a middle (max).", "number": "A number (big: large figures; unit, label).",
    "control": "A value the player's keys set (max, keys).", "compass": "A heading as a strip of compass.",
    "lamps": "Lamps lit while their conditions hold: [{label, if, tone}].", "text": "Words, with {values} in them.",
    "plot": "Values over time in dots: names (min, max, rows).", "scope": "A vector display: a scene's name, or {model, view, clip, at...}.",
    "planet": "A planet of planets.json (view, turn, sites).", "map": "The simulator's map.",
    "ahead": "The view ahead of the vehicle in lines: true, or {look, far, fov, tilt}.",
    "scan": "A surface scan: true (the simulator's map) or {planet, unit, turn, pulse}.",
    "functions": "What the console does when asked: true, or names.", "rule": "A line across.", "space": "Empty rows.",
}


def field(f):
    """One of the editor's fields as a JSON Schema: what it is for, what it may be chosen from, what
    is inside it. No type is demanded: a text may be a list of lines, a number a formula, and the
    schemas are for writing with, not for judging."""
    kind = f.get("type")
    out = {"description": "%s (%s)" % (f.get("label") or f["key"], kind) if kind not in (None, "text", "long") else
           (f.get("label") or f["key"])}
    if kind == "choice":
        opts = [o[0] if isinstance(o, (list, tuple)) else o for o in f.get("options") or []]
        if opts and all(isinstance(o, str) for o in opts):
            out["anyOf"] = [{"enum": opts}, {}]              # (a game's own names pass too)
    elif kind == "bool":
        out["anyOf"] = [{"enum": [True, False]}, {}]
    elif kind == "group":
        out["properties"] = {g["key"]: field(g) for g in f.get("fields") or []}
    elif kind == "effects":
        out["items"] = {"$ref": "#/definitions/effect"}
    elif kind == "rows" and f.get("fields"):
        out["items"] = {"properties": {g["key"]: field(g) for g in f["fields"]}}
    return out


def effect():
    from . import schema
    return {"description": "One thing that happens.",
            "properties": {e["key"]: {"description": e.get("label") or e["key"]} for e in schema.EFFECTS}}


def for_kind(kind):
    """The JSON Schema of one data file."""
    from . import schema
    thing = {"properties": {f["key"]: field(f) for f in kind["fields"]}}
    if kind["key"] == "sims":
        widget = {"description": "A widget: one of %s." % ", ".join(WIDGET_KEYS),
                  "properties": {k: {"description": v} for k, v in WIDGET_KEYS.items()}}
        panel = {"description": "A panel: a frame with a title and widgets, or panels side by side (cols) or one over another (rows).",
                 "properties": {"title": {"description": "Words in its frame."}, "size": {"description": "Columns (in cols) or rows (in rows) it takes."},
                                "colour": {"anyOf": [{"enum": ["green", "amber", "cyan", "white", "red", "blue", "violet"]}, {}]},
                                "border": {"description": "One of the menus' frames."}, "pulse": {"description": "A cue of the music its frame beats with."},
                                "widgets": {"items": widget},
                                "cols": {"items": {"$ref": "#/definitions/panel"}},
                                "rows": {"items": {"$ref": "#/definitions/panel"}}}}
        thing["properties"]["panels"] = {"$ref": "#/definitions/panel", "description": "A screen of its own: panels in a layout."}
        thing["properties"].setdefault("functions", {"description": "What the console does when asked: name -> "
                                       "{label, key, hold, toggle, if, why, lasts, cooldown, uses, set, add, keeps, says, tone, words, effects}."})
        defs = {"effect": effect(), "panel": panel}
    else:
        defs = {"effect": effect()}
    if kind["key"] == "game":
        from .panels import CONSOLE_LOOKS
        thing["properties"]["console"] = {"description": "One look for its consoles.", "anyOf": [{"enum": list(CONSOLE_LOOKS)}, {}]}
    if kind["shape"] == "list":
        thing["properties"].setdefault("id", {"description": "Its id: how the rest of the game names it."})
        body = {"items": thing}
    elif kind["shape"] == "map":
        body = {"additionalProperties": thing}
    else:
        body = thing
    return dict({"$schema": DRAFT, "title": "CLIo: %s (%s.json)" % (kind.get("label") or kind["key"], kind["file"]),
                 "definitions": defs}, **body)


def write(out_dir, say=print):
    """Write a schema for each data file, and the settings that tie them to the files. How many."""
    from . import schema
    os.makedirs(out_dir, exist_ok=True)
    ties = []
    for kind in schema.KINDS:
        name = "clio-%s.schema.json" % kind["file"]
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n") as f:
            json.dump(for_kind(kind), f, indent=1)
            f.write("\n")
        ties.append({"fileMatch": ["games/*/%s.json" % kind["file"], "templates/*/%s.json" % kind["file"]],
                     "url": "./%s/%s" % (os.path.basename(os.path.normpath(out_dir)), name)})
    with open(os.path.join(out_dir, "vscode-settings.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"json.schemas": ties}, f, indent=1)
        f.write("\n")
    say("%d schemas in %s. For VS Code: put the \"json.schemas\" of %s into .vscode/settings.json (the paths are from the "
        "workspace's folder)." % (len(ties), out_dir, os.path.join(out_dir, "vscode-settings.json")))
    return len(ties)
