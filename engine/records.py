# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Scores and the table of best runs.

A game that wants scoring says what counts in ``game.json``::

    "score": {"depth": 100, "kills": 5, "level": 25, "gold": 1, "win": 500}

Each name is looked up in the world (a counter in ``vars``, ``level`` / ``gold``
/ ``xp`` of the player, ``turns``, ``places``, ``quests``, a flag, or ``win``)
and multiplied by its weight.  Finished runs are kept, best first, in
``records.dat`` next to the saved games - one table per game mode.
"""
from __future__ import annotations

import json
import os
import time

KEEP = 10
FILE = "records.dat"


def value(game, name):
    """The number a score term stands for."""
    w = game.world
    p = w.player
    if name == "win":
        return 1 if game.over == "win" or w.flags.get("game_won") else 0
    if name in ("level", "gold", "xp"):
        return p.get(name, 0) or 0
    if name == "turns":
        return w.turn
    if name == "places":
        return len(w.visited)
    if name == "quests":
        return sum(1 for q in w.quests.values() if q.get("status") == "done")
    if name == "health":
        return w.stats.get("health", 0)
    if name in w.vars and isinstance(w.vars[name], (int, float)):
        return w.vars[name]
    return 1 if w.flags.get(name) else 0


def score(game, spec=None):
    spec = game.cfg.get("score") if spec is None else spec
    if not isinstance(spec, dict):
        return 0
    total = 0.0
    for name, weight in spec.items():
        try:
            total += float(weight) * float(value(game, name))
        except (TypeError, ValueError):
            continue
    return max(0, int(round(total)))


def path(folder):
    return os.path.join(folder, FILE)


def load(folder):
    """All tables: ``{mode: [entry, ...]}`` (empty if there are none or the file is damaged)."""
    try:
        with open(path(folder), "r", encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(blob, dict):
        return {}
    return {k: [e for e in v if isinstance(e, dict)] for k, v in blob.items() if isinstance(v, list)}


def add(folder, mode, entry, keep=KEEP):
    """File a finished run. Returns its place in the table (1 = best), or None if it missed it."""
    tables = load(folder)
    table = tables.setdefault(mode or "game", [])
    entry = dict(entry)
    entry.setdefault("date", time.strftime("%Y-%m-%d"))
    table.append(entry)
    table.sort(key=lambda e: -int(e.get("score", 0)))       # stable: an older equal score stays ahead
    place = next(i for i, e in enumerate(table, 1) if e is entry)
    del table[keep:]
    try:
        tmp = path(folder) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(tables, f, indent=1)
        os.replace(tmp, path(folder))
    except OSError:
        pass
    return place if place <= keep else None
