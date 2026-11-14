# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The game editor's working parts: read a game, check it, write a file.

Everything here is plain functions on a game folder, so the same code serves
the local editor (``python clio.py mygame --edit``, see ``server.py``) and can
serve any other front end later.  The rules are the engine's own: a check is
``GameData.validate()`` on the files as they would be after saving.
"""
import json
import os
import re
import shutil
import tempfile
import time

from .. import schema
from ..data import GameData, GameDataError, config_path

BACKUP = ".editor-backup"
_DEFAULT = {"scenes": "scenes.json", "items": "items.json", "characters": "characters.json",
            "texts": "texts.json", "dialogues": "dialogues.json", "quests": "quests.json",
            "triggers": "triggers.json", "music": "music.json", "sounds": "sounds.json",
            "sprites": "sprites.json", "dungeon": "dungeon.json"}
_WHERE = {"scene": "scenes", "item": "items", "character": "characters", "dialogue": "dialogues",
          "quest": "quests", "trigger": "triggers", "mode": "game", "floor": "dungeon", "dungeon": "dungeon",
          "initial_scene": "game"}


class EditorError(Exception):
    """Something the person at the editor can put right."""


def paths(game_dir):
    """``{key: path}`` of the files the editor may read and write - all of them inside the game folder."""
    game_dir = os.path.abspath(game_dir)
    cfg_file = config_path(game_dir)
    if not cfg_file:
        raise EditorError("There is no game.json in %s." % game_dir)
    with open(cfg_file, encoding="utf-8") as f:
        cfg = json.load(f)
    out = {"game": cfg_file}
    named = cfg.get("files", {}) if isinstance(cfg.get("files"), dict) else {}
    for key, default in _DEFAULT.items():
        path = os.path.abspath(os.path.join(game_dir, str(named.get(key, default))))
        if os.path.dirname(path) == game_dir:               # a file kept elsewhere is not this game's to change
            out[key] = path
    return out


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _problem(text):
    """A validator's sentence, with the thing it is about picked out so the editor can point at it."""
    m = re.match(r"(\w+) '([^']*)'", text)
    kind = _WHERE.get(m.group(1)) if m else None
    if kind is None:
        first = text.split(" ", 1)[0].rstrip(":")
        kind = _WHERE.get(first)
        return {"text": text, "kind": kind, "id": None}
    return {"text": text, "kind": kind, "id": m.group(2)}


def check(game_dir, pending=None):
    """Problems the engine finds - in the files as they are, or as they would be with ``pending`` saved.

    ``pending`` is ``{key: data}`` for files that were changed and not yet written.
    """
    where = paths(game_dir)
    work = tempfile.mkdtemp(prefix="clio-edit-")
    try:
        for key, path in where.items():
            target = os.path.join(work, os.path.basename(path))
            if pending and key in pending:
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(pending[key], f)
            elif os.path.isfile(path):
                shutil.copyfile(path, target)
        try:
            found = GameData(work).validate()
        except GameDataError as err:
            found = [str(err)]
        except Exception as err:                            # data too broken to load is a problem to report, not a crash
            found = ["The game cannot be loaded like this: %s: %s" % (type(err).__name__, err)]
        return [_problem(p) for p in found]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def load(game_dir):
    """Everything the editor shows: the files, the schema to build forms from, and the current problems."""
    where = paths(game_dir)
    files = {}
    for key, path in where.items():
        exists = os.path.isfile(path)
        kind = schema.BY_FILE[key]
        files[key] = {"name": os.path.basename(path), "exists": exists,
                      "data": _read(path) if exists else ([] if kind["shape"] == "list" else {})}
    cfg = files["game"]["data"]
    return {"id": cfg.get("id") or os.path.basename(os.path.abspath(game_dir)),
            "title": cfg.get("title") or os.path.basename(os.path.abspath(game_dir)),
            "folder": os.path.abspath(game_dir), "files": files, "schema": schema.KINDS,
            "problems": check(game_dir)}


def save(game_dir, key, data):
    """Write one file. Returns the problems the game has afterwards.

    The file keeps its layout (two-space indent, the same escaping, line ends
    and final newline as before), so a version-control diff shows only what changed.
    The first save of a day keeps the previous version in ``.editor-backup``.
    """
    where = paths(game_dir)
    if key not in where:
        raise EditorError("'%s' is not a file of this game." % key)
    kind = schema.BY_FILE[key]
    want = list if kind["shape"] == "list" else dict
    if not isinstance(data, want):
        raise EditorError("%s must be a JSON %s." % (os.path.basename(where[key]),
                                                     "list" if want is list else "object"))
    if key == "game" and not isinstance(data.get("files", {}), dict):
        raise EditorError("\"files\" in game.json must be an object.")
    path = where[key]
    ascii_only, newline, line_end = True, "\n", "\n"
    if os.path.isfile(path):
        with open(path, encoding="utf-8", newline="") as f:  # as it is on disk: Windows line ends stay Windows
            old = f.read()
        line_end = "\r\n" if "\r\n" in old else "\n"
        ascii_only, newline = old.isascii(), ("\n" if old.endswith("\n") else "")
        keep = os.path.join(os.path.dirname(path), BACKUP)
        os.makedirs(keep, exist_ok=True)
        copy = os.path.join(keep, "%s-%s" % (time.strftime("%Y%m%d"), os.path.basename(path)))
        if not os.path.exists(copy):
            shutil.copyfile(path, copy)
    text = (json.dumps(data, indent=2, ensure_ascii=ascii_only) + newline).replace("\n", line_end)
    handle, temp = tempfile.mkstemp(prefix=".saving-", dir=os.path.dirname(path))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(temp, path)                              # all of the new file or none of it
    except Exception:
        if os.path.exists(temp):
            os.remove(temp)
        raise
    return {"saved": os.path.basename(path), "problems": check(game_dir)}
