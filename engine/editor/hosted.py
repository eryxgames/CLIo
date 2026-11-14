# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The editor without a server: opened from a web address, running in the browser.

The page is the one ``--edit`` serves.  Opened from a static site (GitHub Pages)
it starts Python inside the browser (Pyodide), loads this engine into it, and
asks ``service.handle`` directly.  The game is read from a folder or a zip file
by the browser and lives in the tab's memory; nothing is sent anywhere.

A static site cannot list a folder, so the files that make up the engine, the
demo games and the starter game are listed in ``web/manifest.json``::

    python -m engine.editor.hosted        # after adding or removing a file

A test fails when that list is out of date.
"""
import hashlib
import io
import json
import os
import re
import zipfile

from . import BACKUP, EditorError

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "manifest.json")
GAMES = "/games"                        # where opened games live, in the browser's memory
MOST = 64 * 1024 * 1024                 # a game larger than this is not a folder of text
LEFT_OUT = ("__pycache__", "saves")     # folders that are not part of a game
DEMOS = ("depths", "derelict")          # the games the page offers; a game of your own in games/ is not put on show


# ------------------------------------------------------------------- the list
def _files(folder, keep=lambda name: True):
    found = []
    for where, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in LEFT_OUT)
        for name in sorted(names):
            if not name.startswith(".") and keep(name):
                found.append(os.path.relpath(os.path.join(where, name), ROOT).replace(os.sep, "/"))
    return found


def _game(folder):
    with open(os.path.join(ROOT, folder, "game.json"), encoding="utf-8") as f:
        about = json.load(f)
    return {"id": os.path.basename(folder), "folder": folder, "title": about.get("title") or os.path.basename(folder),
            "about": about.get("description") or about.get("subtitle") or "",
            "files": _files(os.path.join(ROOT, folder), lambda name: not name.endswith(".pyc"))}


def manifest():
    """What the page fetches: the engine's modules, and the games it can open without being given one."""
    return {"engine": _files(os.path.join(ROOT, "engine"), lambda name: name.endswith(".py")),
            "starter": _game("templates/starter"),
            "games": [_game("games/" + g) for g in DEMOS]}


def write():
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest(), f, indent=1)
        f.write("\n")
    return MANIFEST


# ------------------------------------------------------------ games in memory
def unzip(data):
    """The files of a zip archive, as ``(path, bytes)`` pairs."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > MOST:
                raise EditorError("That archive is too large to be a game.")
            return [(i.filename, z.read(i)) for i in z.infolist() if not i.is_dir()]
    except zipfile.BadZipFile:
        raise EditorError("That file is not a zip archive.")


def place(name, files, into=GAMES):
    """Put a game's files where the editor can work on them; returns the game's folder.

    ``files`` are ``(path, bytes)`` pairs as a folder picker or an archive gives them.  The game is the folder with
    ``game.json`` in it: the top one, or the only one nearest the top (an archive of the folder; a folder around
    the game's folder).  ``found_in`` remembers where it was found, for writing back.
    """
    clean = {}
    for path, data in files:
        parts = [p for p in str(path).replace("\\", "/").split("/") if p not in ("", ".")]
        if not parts or ".." in parts or any(p in LEFT_OUT or (p.startswith(".") and p != BACKUP) for p in parts):
            continue
        clean["/".join(parts)] = bytes(data)
    if sum(len(d) for d in clean.values()) > MOST:
        raise EditorError("That is too large to be a game.")
    homes = sorted((p[:-len("game.json")] for p in clean if p == "game.json" or p.endswith("/game.json")),
                   key=lambda home: (home.count("/"), home))
    if not homes:
        raise EditorError("There is no game.json in it. Choose the game's own folder - the one with game.json inside.")
    if len(homes) > 1 and homes[0].count("/") == homes[1].count("/"):
        raise EditorError("There are several games in it (%s). Choose the folder of one of them."
                          % ", ".join(h.strip("/") for h in homes[:4]))
    home = homes[0]
    title = home.strip("/").split("/")[-1] if home else name
    title = re.sub(r"[^A-Za-z0-9_-]+", "_", title or "").strip("_") or "game"
    folder = os.path.join(into, title)
    if os.path.isdir(folder):
        import shutil
        shutil.rmtree(folder)
    for path, data in clean.items():
        if not path.startswith(home):
            continue
        target = os.path.join(folder, *path[len(home):].split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
    _seen.pop(folder, None)
    changed(folder)                                         # from here on, only what the editor writes counts as changed
    found_in[folder] = home.strip("/")
    return folder


_seen = {}
found_in = {}                           # game folder -> where in what was opened the game was found ("" for the top)


def changed(game_dir):
    """The files of the game that differ from the last time this was asked: ``[(path, bytes), ...]``.

    That is what a save wrote - a data file, its backup, a walkthrough - so the page can write the same files into
    the folder the game came from.
    """
    before = _seen.setdefault(game_dir, {})
    out = []
    for where, _dirs, names in os.walk(game_dir):
        for name in sorted(names):
            path = os.path.join(where, name)
            with open(path, "rb") as f:
                data = f.read()
            mark = hashlib.sha1(data).hexdigest()
            rel = os.path.relpath(path, game_dir).replace(os.sep, "/")
            if before.get(rel) != mark:
                before[rel] = mark
                out.append((rel, data))
    return out


if __name__ == "__main__":
    print("wrote %s" % os.path.relpath(write(), ROOT))
