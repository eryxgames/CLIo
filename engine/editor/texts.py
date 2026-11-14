# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Every line a player can read, as one table - out of the game and back in.

For proofreading, rewording or translating a whole game at once, and for
finding and replacing across it.  A row is a place and the text there:

    scenes/utility_room/description      A cramped maintenance closet: ...
    scenes/utility_room/exits/0/guard_text   The bugrat has nested in ...
    dialogues/maren/nodes/hello/text     So you are the one. ...

The place is the path through the data file: file, the id of the thing, then
keys and list positions.  (``/`` and ``~`` inside a key are written ``~1`` and
``~0``.)  Putting a table back changes only the texts whose place still exists
and still holds text; everything else is reported, nothing is guessed.

What counts as text is decided by a rule of thumb, since the data has no
separate layer for it: names, titles and anything called ``..._text`` always;
otherwise a string with a space in it, unless its key is known to hold
something else (a condition, an id, an author).  Keys that are themselves text
- a choice written as ``{"Ask about the ship": "..."}`` - are not covered.
"""
import csv
import io

from .. import schema

SKIP_FILES = ("music", "sounds", "sprites")                  # notation and pixels, not prose
ALWAYS = {"name", "short", "title", "subtitle", "door_name", "doors", "area", "aliases", "names", "prefixes",
          "map_title", "speaker", "default_name"}
NEVER = {"id", "author", "website", "version", "license", "seed", "style", "wave", "art", "sprite", "portrait",
         "if", "when", "all", "any", "not", "unblock_if", "leave_if", "done_when", "var", "stat", "set", "type",
         "files", "scene_id", "goto", "sfx", "music", "effect"}
HEADER = ["where", "text"]


def is_text(key, value):
    if key in NEVER or not value.strip():
        return False
    if key in ALWAYS or key.endswith("_text") or key.endswith("_prompt"):
        return True
    return " " in value.strip() or "\n" in value


def _esc(part):
    return str(part).replace("~", "~0").replace("/", "~1")


def _unesc(part):
    return part.replace("~1", "/").replace("~0", "~")


def _things(key, data):
    """``(id, thing)`` pairs of a file, the way its kind is laid out."""
    shape = schema.BY_FILE[key]["shape"]
    if shape == "object":
        return [(None, data)]
    if shape == "list":
        return [(str(t.get("id", i)) if isinstance(t, dict) else str(i), t) for i, t in enumerate(data)]
    return list(data.items())


def rows(files):
    """``[{"where", "text", "kind", "id"}, ...]`` for ``files`` = ``{key: data}``, in file order."""
    out = []

    def walk(value, key, path, kind, thing_id):
        if isinstance(value, str):
            if is_text(key, value):
                out.append({"where": "/".join(path), "text": value, "kind": kind, "id": thing_id})
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, key, path + [str(i)], kind, thing_id)
        elif isinstance(value, dict):
            for k, v in value.items():
                walk(v, k, path + [_esc(k)], kind, thing_id)

    for kind in schema.KINDS:
        key = kind["file"]
        if key in SKIP_FILES or key not in files:
            continue
        for thing_id, thing in _things(key, files[key]):
            base = [key] if thing_id is None else [key, _esc(thing_id)]
            if isinstance(thing, dict):
                for k, v in thing.items():
                    walk(v, k, base + [_esc(k)], key, thing_id)
            else:
                walk(thing, key, base, key, thing_id)
    return out


def _holder(files, where):
    """The container and key (or index) a place names, or None when the place does not exist."""
    parts = [_unesc(p) for p in where.split("/")]
    if len(parts) < 2 or parts[0] not in files or parts[0] in SKIP_FILES or parts[0] not in schema.BY_FILE:
        return None
    key, rest = parts[0], parts[1:]
    node = files[key]
    if schema.BY_FILE[key]["shape"] != "object":
        found = dict(_things(key, node)).get(rest[0])
        if found is None:
            return None
        node, rest = found, rest[1:]
        if not rest:
            return None
    for i, part in enumerate(rest):
        last = i == len(rest) - 1
        if isinstance(node, dict):
            if part not in node:
                return None
            if last:
                return node, part
            node = node[part]
        elif isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                return None
            if last:
                return node, int(part)
            node = node[int(part)]
        else:
            return None
    return None


def apply(files, table):
    """Put texts back. ``table`` is rows with ``where`` and ``text``; ``files`` is changed in place.

    Returns ``{"changed": n, "same": n, "files": [keys changed], "missing": [places that do not exist
    or no longer hold text]}``.
    """
    changed, same, touched, missing = 0, 0, [], []
    for row in table:
        where, text = str(row.get("where", "")).strip(), row.get("text")
        if not where:
            continue
        spot = _holder(files, where) if isinstance(text, str) else None
        if spot is None or not isinstance(spot[0][spot[1]], str):
            missing.append(where)
            continue
        holder, key = spot
        if holder[key] == text:
            same += 1
            continue
        holder[key] = text
        changed += 1
        if where.split("/")[0] not in touched:
            touched.append(where.split("/")[0])
    return {"changed": changed, "same": same, "files": touched, "missing": missing}


def to_csv(table):
    """The table as CSV text: a header, then one row per text. Line breaks inside a text stay inside its cell."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(HEADER)
    for row in table:
        writer.writerow([row["where"], row["text"]])
    return out.getvalue()


def from_csv(text):
    """Rows from CSV text as a spreadsheet saves it. Columns beyond the first two are ignored."""
    text = text.lstrip("﻿")
    sample = text[:2048]
    delimiter = ";" if sample.count(";") > sample.count(",") and "where;" in sample.lower() else ","
    table = []
    for i, cells in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)):
        if not cells or not cells[0].strip():
            continue
        if i == 0 and cells[0].strip().lower() == "where":
            continue
        if len(cells) < 2:
            raise ValueError("Row %d has a place but no text column." % (i + 1))
        table.append({"where": cells[0].strip(), "text": cells[1].replace("\r\n", "\n")})
    return table
