# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Two pictures of a game for the editor: where the rooms are, and how a conversation runs.

Both are worked out with the engine's own rules - the room map by
``automap.layout``, which is what the player's map uses, and the conversation
by the rules of ``dialogue.py`` - so what the editor draws is what the game does.
"""
import copy

from .. import automap
from ..data import GameData
from . import EditorError, workdir


def world_map(game_dir, pending=None):
    """Rooms on the grid the player's map uses, and the ways between them.

    Returns ``{"start", "levels", "generated", "rooms": [{"id", "name", "x", "y", "z", "placed",
    "reached", "pinned"}], "ways": [{"from", "to", "name", "dir", "level", "barred", "one_way", "missing"}]}``.

    A room is ``placed`` when the layout gave it a place, ``reached`` when exits
    lead to it from the first scene, and ``pinned`` when its data says where it
    is (``"map": [x, y, level]``).  A way is ``barred`` by a lock, a block or a
    guard; ``one_way`` when nothing leads back; ``missing`` when it leads to a
    scene that does not exist.  ``level`` is +1 or -1 for stairs.
    """
    with workdir(game_dir, pending) as work:
        data = GameData(work)
        scenes = copy.deepcopy(data.scenes)                 # the layout writes a direction onto exits that have none
        start = data.config.get("initial_scene") or next(iter(scenes), None)
        places = automap.layout(scenes, start) if start in scenes else {}
        reached, todo = {start} if start in scenes else set(), [start] if start in scenes else []
        while todo:
            for ex in scenes[todo.pop()].get("exits", []):
                to = ex.get("scene_id") if isinstance(ex, dict) else None
                if to in scenes and to not in reached:
                    reached.add(to)
                    todo.append(to)
        rooms, ways = [], []
        for sid, sc in scenes.items():
            at = places.get(sid)
            rooms.append({"id": sid, "name": sc.get("name", sid), "placed": at is not None, "reached": sid in reached,
                          "pinned": isinstance(sc.get("map"), (list, tuple)),
                          "x": at[0] if at else None, "y": at[1] if at else None, "z": at[2] if at else None})
            for ex in sc.get("exits", []):
                if not isinstance(ex, dict):
                    continue
                to = ex.get("scene_id")
                generated = isinstance(to, str) and to.startswith("@")      # made when the game is played
                back = to in scenes and any(isinstance(b, dict) and b.get("scene_id") == sid for b in scenes[to].get("exits", []))
                d = ex.get("dir") or ex.get("_dir") or ""
                barred = "locked" if ex.get("locked") else "blocked" if ex.get("blocked") else "guarded" if ex.get("guard") else ""
                ways.append({"from": sid, "to": to, "name": ex.get("door_name", ""), "dir": d,
                             "level": automap.DIRS.get(automap.DIR_WORDS.get(str(d).lower(), d), (0, 0, 0))[2],
                             "barred": barred, "one_way": to in scenes and not back,
                             "missing": to not in scenes and not generated, "generated": generated})
        return {"start": start, "levels": sorted({r["z"] for r in rooms if r["placed"]}, reverse=True),
                "generated": bool(data.config.get("generator")), "rooms": rooms, "ways": ways}


def dialogue_graph(tree):
    """How a conversation runs: its nodes in the order they can be reached, and the jumps between them.

    ``tree`` is one entry of ``dialogues.json``.  Returns ``{"nodes": [{"id", "text", "depth",
    "start", "reached", "stays", "ends"}], "jumps": [{"from", "to", "by", "kind"}], "missing": [...]}``.

    ``depth`` is how many jumps from a starting node (None when it is never
    reached); ``stays`` counts answers that are given without leaving the node;
    ``ends`` says the conversation can end there.  A jump's ``kind`` is
    ``choice`` (the player picked ``by``), ``then`` (the node continues by
    itself), or ``start``.  ``missing`` lists jumps to nodes that do not exist.
    """
    if not isinstance(tree, dict) or not isinstance(tree.get("nodes"), dict):
        raise EditorError("This dialogue has no nodes to draw.")
    nodes = tree["nodes"]
    start = tree.get("start")
    if isinstance(start, list):
        starts = [e if isinstance(e, str) else (e.get("node") or e.get("goto")) for e in start if isinstance(e, (str, dict))]
    elif start in nodes:
        starts = [start]
    else:
        starts = [next(iter(nodes))] if nodes else []
    starts = [s for i, s in enumerate(starts) if s and s not in starts[:i]]
    jumps, missing, info = [], [], {}
    for nid, node in nodes.items():
        node = node if isinstance(node, dict) else {}
        choices = [c for c in (node.get("choices") or []) if isinstance(c, dict)]
        stays, ends = 0, False
        for c in choices:
            to = c.get("goto")
            if to in (None, ""):
                stays += 1
            elif to == "end":
                ends = True
            elif to != "back":
                jumps.append({"from": nid, "to": to, "by": c.get("text", ""), "kind": "choice"})
        to = node.get("goto")
        if to == "end" or (not to and not choices):
            ends = True                                     # nothing to choose and nowhere to go: it is over
        elif to and to != "back":
            jumps.append({"from": nid, "to": to, "by": "", "kind": "then"})
        text = node.get("text") if isinstance(node.get("text"), str) else ""
        if not text and node.get("variants"):
            text = next((v.get("text", "") for v in node["variants"] if isinstance(v, dict)), "")
        info[nid] = {"id": nid, "text": text, "stays": stays, "ends": ends, "start": nid in starts, "depth": None}
    for j in jumps:
        if j["to"] not in nodes:
            missing.append(dict(j))
    for s in starts:
        if s not in nodes:
            missing.append({"from": None, "to": s, "by": "", "kind": "start"})
    level, depth = [s for s in starts if s in nodes], 0
    while level:                                            # breadth first: the shortest way to each node
        nxt = []
        for nid in level:
            if info[nid]["depth"] is None:
                info[nid]["depth"] = depth
                nxt += [j["to"] for j in jumps if j["from"] == nid and j["to"] in nodes]
        level, depth = [n for n in nxt if info[n]["depth"] is None], depth + 1
    out = [dict(n, reached=n["depth"] is not None) for n in info.values()]
    out.sort(key=lambda n: (n["depth"] is None, n["depth"] or 0))
    return {"nodes": out, "jumps": [j for j in jumps if j["to"] in nodes], "missing": missing}
