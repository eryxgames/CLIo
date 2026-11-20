# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Minds for monsters: brains that weigh their tactics (``brain``), squads that share what they know and
give each member a part (``squad``), and a search for games of moves and answers (``search``: minimax with
alpha-beta, Monte Carlo tree search), for duels and cards to come.

Everything here keeps the engine's rule: what a mind does depends only on the level's state, so a game
played back, or played on another machine, goes the same way (docs: claude/clio-saves-and-multiplayer-design).
"""
from __future__ import annotations

from . import brain, search, squad
from .squad import Squad

__all__ = ["brain", "search", "squad", "Squad", "beat", "group"]


def beat(lv, heard=None):
    """Before the monsters act: squads share what they know; a brainy monster that heard a shot knows where."""
    if heard and lv.noise_at:
        for m in lv.monsters:
            if m.awake and not m.dead and (m.x, m.y) in heard and brain.params(lv, m) is not None:
                m.seen_at = (lv.noise_at[0], lv.noise_at[1], lv.beat)
    squad.beat(lv, heard)


def group(lv, auto, members=None):
    """Brainy monsters put near each other (within ``radius`` cells, a chain of them) form squads: ``auto`` is a
    level's ``"squads": {"auto": {...}}``."""
    if not isinstance(auto, dict):
        return
    radius = int(auto.get("radius", 4))
    pool = [m for m in (members if members is not None else lv.monsters)
            if m.squad is None and not m.dead and brain.has(lv, m)]
    pool.sort(key=lambda m: m.id)
    done = set()
    for m in pool:
        if m.id in done:
            continue
        group_ = [m]
        done.add(m.id)
        i = 0
        while i < len(group_):
            a = group_[i]
            for o in pool:
                if o.id not in done and max(abs(o.x - a.x), abs(o.y - a.y)) <= radius:
                    done.add(o.id)
                    group_.append(o)
            i += 1
        if len(group_) >= 2:
            name = squad.free_name(lv, "auto")
            for o in group_:
                squad.join(lv, o, name, spec=auto)
