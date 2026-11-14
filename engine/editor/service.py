# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Everything the editor's page can ask for, as one function.

The page is the same wherever it runs; only the way a question reaches Python
differs.  Started with ``--edit``, the local server passes each request here.
Opened from a web address, the page runs Python in the browser itself and calls
this function directly - there is no server, and the game never leaves the tab.
"""
from . import (EditorError, advice, archive, balance, check, finish, load, looks, put_texts, save, text_table, texts,
               views)


class Unknown(EditorError):
    """A question the editor does not have."""


def handle(game_dir, path, body=None):
    """The answer to one request: a ``dict`` (sent as JSON) or ``bytes`` (a file). Raises ``EditorError``."""
    body = body or {}
    pending = body.get("pending") or {}
    if path == "/api/game":
        return load(game_dir)
    if path == "/api/check":
        return {"problems": check(game_dir, pending)}
    if path == "/api/save":
        return save(game_dir, str(body.get("file")), body.get("data"))
    if path == "/api/texts":                                # every line a player can read
        found = text_table(game_dir, pending)
        return {"csv": texts.to_csv(found), "count": len(found)} if body.get("csv") else {"rows": found}
    if path == "/api/texts/apply":                          # put texts back: a table from the page, or a CSV file's text
        try:
            rows = texts.from_csv(body["csv"]) if isinstance(body.get("csv"), str) else body.get("rows") or []
        except (ValueError, KeyError) as err:
            raise EditorError("That file could not be read as a table of texts: %s" % err)
        return put_texts(game_dir, rows, pending)
    if path == "/api/enemy":                                # a new enemy of a chosen strength, to look at
        return balance.make_enemy(game_dir, body.get("like") or None, body.get("floor"), body.get("rank") or "regular",
                                  body.get("lean") or 0.0, body.get("name"), pending)
    if path == "/api/odds":                                 # how fights against some characters go
        return balance.odds(game_dir, [str(e) for e in body.get("enemies") or []], pending,
                            body.get("extra") or None, body.get("level") or 1, body.get("fights") or 30)
    if path == "/api/advice":                               # not wrong, but perhaps not meant
        return {"advice": advice(game_dir, pending)}
    if path == "/api/walkthrough":                          # the game's known way through: read it, or keep a new one
        if "text" in body:
            return {"saved": finish.write(game_dir, body["text"])}
        return {"text": finish.read(game_dir)}
    if path == "/api/finish":                               # play the walkthroughs on the game as it is in the page
        return finish.play(game_dir, body.get("text"), pending)
    if path == "/api/map":                                  # the rooms where the player's map puts them
        return views.world_map(game_dir, pending)
    if path == "/api/dialogue":                             # how one conversation runs
        return views.dialogue_graph(body.get("tree"))
    if path == "/api/sprite":                               # grow a sprite as the game would, or name a palette's colours
        if "palette" in body:
            return {"colours": looks.colours(body.get("palette"))}
        return looks.grow(body.get("seed") or "nobody", body.get("size") or 12)
    if path == "/api/archive":                              # the whole game folder as a zip file
        return archive(game_dir)
    raise Unknown("Nothing here.")
