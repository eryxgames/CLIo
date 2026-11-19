# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Everything the editor's page can ask for, as one function.

The page is the same wherever it runs; only the way a question reaches Python
differs.  Started with ``--edit``, the local server passes each request here.
Opened from a web address, the page runs Python in the browser itself and calls
this function directly - there is no server, and the game never leaves the tab.
"""
from . import (EditorError, advice, archive, balance, check, finish, levels, load, looks, put_texts, save, text_table,
               texts, views)


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
    if path == "/api/monster":                              # a monster grown on a body plan, with its far versions
        return looks.monster(body.get("seed") or "nobody", body.get("body") or "biped", body.get("size") or 18)
    if path == "/api/far":                                  # far versions made from a drawing
        return looks.far(body.get("pixels"), body.get("keep") or "")
    if path == "/api/distances":                            # a sprite as a level draws it, cell by cell further away
        return looks.distances(body.get("sprite"), body.get("size") or 1.0)
    if path == "/api/picture":                              # a sprite drawn in its style, as the game draws it
        return looks.picture(game_dir, str(body.get("name") or ""), pending)
    if path == "/api/banner":                               # a banner of game.json, drawn as the game draws it
        return looks.banner(game_dir, str(body.get("key") or "title_banner"), body.get("width") or 78, pending)
    if path == "/api/levels":                               # what map characters mean, tiles, monsters and items
        return levels.info(game_dir, pending)
    if path == "/api/tile":                                 # one of the engine's tiles, as data to draw over
        return levels.engine_tile(body.get("name") or "steel")
    if path == "/api/view":                                 # a level seen from a cell
        return levels.view(game_dir, str(body.get("level") or ""), body.get("x"), body.get("y"), body.get("facing"),
                           body.get("style") or "pixel", pending, body.get("width") or 80)
    if path == "/api/tileview":                             # a tile on the walls (floor, ceiling) of a small room
        return levels.tile_view(game_dir, str(body.get("name") or ""), body.get("where") or "wall", pending)
    if path == "/api/weaponview":                           # a weapon in the hands, and one shot of it
        return levels.weapon_view(game_dir, str(body.get("weapon") or ""), pending)
    if path == "/api/modelview":                            # a 3D model in a small room: turning, broken, its frames
        return levels.model_view(game_dir, str(body.get("name") or ""), pending, body.get("turns") or 12)
    if path == "/api/modelimport":                          # a glTF file from Blender, made a model (not written)
        return levels.model_import(body.get("data"), str(body.get("name") or ""), body.get("scale") or 0.4)
    if path == "/api/levelcheck":                           # the level bot plays the level a few times
        return levels.check(game_dir, str(body.get("level") or ""), pending, body.get("runs") or 5)
    if path == "/api/archive":                              # the whole game folder as a zip file
        return archive(game_dir)
    if path == "/api/sheet":                                # a sheet of pictures as PNG, or where each one is on it
        return looks.sheet(game_dir, str(body.get("what") or "monsters"), body.get("scale") or 4,
                           body.get("labels", True), body.get("background") or "clear", body.get("format") or "png",
                           pending)
    if path == "/api/fromimage":                            # a picture (a PNG, or a browser's pixels) made a sprite
        return looks.from_image(body)
    if path == "/api/sheetimport":                          # an edited sheet taken back: what changed, not written
        return looks.sheet_back(game_dir, body, pending)
    if path == "/api/endscreen":                            # the end screen of a game of levels, as the game draws it
        return looks.end_screen(game_dir, pending, body.get("width") or 100, body.get("height") or 34)
    raise Unknown("Nothing here.")
