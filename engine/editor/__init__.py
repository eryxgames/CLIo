# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The game editor's working parts: read a game, check it, write a file.

Everything here is plain functions on a game folder, so the same code serves
the local editor (``python clio.py mygame --edit``, see ``server.py``) and can
serve any other front end later.  The rules are the engine's own: a check is
``GameData.validate()`` on the files as they would be after saving.
"""
import contextlib
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


@contextlib.contextmanager
def workdir(game_dir, pending=None):
    """A throwaway copy of the game's data files, with ``pending`` in place of what is on disk."""
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
        yield work
    finally:
        shutil.rmtree(work, ignore_errors=True)


def check(game_dir, pending=None):
    """Problems the engine finds - in the files as they are, or as they would be with ``pending`` saved.

    ``pending`` is ``{key: data}`` for files that were changed and not yet written.
    """
    with workdir(game_dir, pending) as work:
        try:
            found = GameData(work).validate()
        except GameDataError as err:
            found = [str(err)]
        except Exception as err:                            # data too broken to load is a problem to report, not a crash
            found = ["The game cannot be loaded like this: %s: %s" % (type(err).__name__, err)]
        return [_problem(p) for p in found]


def _files(game_dir):
    files = {}
    for key, path in paths(game_dir).items():
        exists = os.path.isfile(path)
        kind = schema.BY_FILE[key]
        files[key] = {"name": os.path.basename(path), "exists": exists,
                      "data": _read(path) if exists else ([] if kind["shape"] == "list" else {})}
    return files


def load(game_dir):
    """Everything the editor shows: the files, the schema to build forms from, and the current problems."""
    files = _files(game_dir)
    cfg = files["game"]["data"]
    return {"id": cfg.get("id") or os.path.basename(os.path.abspath(game_dir)),
            "title": cfg.get("title") or os.path.basename(os.path.abspath(game_dir)),
            "folder": os.path.abspath(game_dir), "files": files, "schema": schema.KINDS,
            "problems": check(game_dir)}


def current(game_dir, pending=None):
    """``{key: data}`` of the game as it would be with ``pending`` saved."""
    files = {key: file["data"] for key, file in _files(game_dir).items()}
    for key, data in (pending or {}).items():
        if key in files:
            files[key] = data
    return files


def text_table(game_dir, pending=None):
    """Every line a player can read (see ``texts.py``), from the files as they would be with ``pending``."""
    from . import texts
    return texts.rows(current(game_dir, pending))


def put_texts(game_dir, table, pending=None):
    """Put a table of texts back into the game's data without writing anything.

    Returns ``{"files": {key: data}, "report": {...}}`` - only the files that changed, for the
    caller to check and save.
    """
    from . import texts
    files = current(game_dir, pending)
    report = texts.apply(files, table)
    return {"files": {key: files[key] for key in report["files"]}, "report": report}


def advice(game_dir, pending=None):
    """Things that are not wrong but may not be meant: rooms nobody can reach, things nothing refers to.

    The same shape as ``check``.  A thing counts as referred to when its id
    appears anywhere else in the data - as a value, inside a condition such as
    ``has:lamp``, or as a key - so this errs on the side of saying nothing.
    """
    files = current(game_dir, pending)
    out = []
    scenes = [s for s in files.get("scenes", []) if isinstance(s, dict) and "id" in s]
    first = files["game"].get("initial_scene") or (scenes[0]["id"] if scenes else None)
    if scenes and first:
        doors = {s["id"]: [e.get("scene_id") for e in s.get("exits", []) if isinstance(e, dict)] for s in scenes}
        seen, todo = {first}, [first]
        while todo:
            for nxt in doors.get(todo.pop(), []):
                if nxt in doors and nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        for s in scenes:
            if s["id"] not in seen:
                out.append({"text": "scene '%s' cannot be reached through exits from the first scene, '%s'" % (s["id"], first),
                            "kind": "scenes", "id": s["id"]})
    words = {}                                              # every word in the data -> the things it appears in

    def walk(value, owner):
        if isinstance(value, str):
            for word in re.split(r"[^A-Za-z0-9_.\-]+", value):
                if word:
                    words.setdefault(word, set()).add(owner)
        elif isinstance(value, list):
            for v in value:
                walk(v, owner)
        elif isinstance(value, dict):
            for k, v in value.items():
                walk(str(k), owner)
                walk(v, owner)

    from . import texts
    for key, data in files.items():
        for thing_id, thing in texts._things(key, data):
            walk(thing, (key, thing_id))
    for kind in ("items", "characters", "dialogues", "sprites", "music", "sounds"):
        one = schema.BY_FILE[kind]["one"]
        for thing_id, _thing in texts._things(kind, files.get(kind, {})):
            if not (words.get(str(thing_id), set()) - {(kind, thing_id)}):
                out.append({"text": "%s '%s': nothing else in the game refers to it" % (one, thing_id),
                            "kind": kind, "id": thing_id})
    return out


def archive(game_dir):
    """The game folder as the bytes of a zip file (backups and caches left out)."""
    import io
    import zipfile
    game_dir = os.path.abspath(game_dir)
    name = os.path.basename(game_dir)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, dirs, names in os.walk(game_dir):
            dirs[:] = sorted(d for d in dirs if d != BACKUP and d != "__pycache__" and not d.startswith("."))
            for n in sorted(names):
                if n.startswith(".") or n.endswith(".pyc"):
                    continue
                path = os.path.join(folder, n)
                z.write(path, os.path.join(name, os.path.relpath(path, game_dir)).replace(os.sep, "/"))
    return out.getvalue()


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
