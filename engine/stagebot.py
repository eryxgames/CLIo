# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The stage bot: finds a way through an arcade stage (engine/arcade.py) without losing a life.

It tries moves - keys held for a few ticks - on copies of the stage, and goes on first from the copies
nearest the goal (by a walk over the map's tiles, which it works out once), as a person would who sees
the whole map. What it finds is a list of moves and a journal of key events that plays the same run
back on the stage (engine/realtime.py): a stage that the bot clears can be cleared.

    python -m engine.stagebot GAME [STAGE...]
"""

from __future__ import annotations

import heapq
import itertools
import sys
from collections import deque

from .arcade import FP, make
from .keys import PRESS, RELEASE, REPEAT
from .realtime import Controls

STEP = 4                                             # ticks a move lasts
UNREACHED = 10 ** 6


def moves_for(st):
    """The moves the bot tries: sets of keys held."""
    if st.topdown:
        dirs = [("up",), ("down",), ("left",), ("right",), ("up", "left"), ("up", "right"), ("down", "left"),
                ("down", "right")]
        out = [()] + dirs
        if st.gun:
            out += [d + ("x",) for d in dirs] + [("x",)]
        return out
    out = [(), ("right",), ("left",), ("right", "space"), ("left", "space"), ("space",), ("up",), ("down",),
           ("down", "space")]
    if st.gun:
        out += [("right", "x"), ("left", "x"), ("x",)]
    return out


def walk_map(st, targets):
    """Tiles from each tile to the nearest of ``targets``, over what is not a wall (pits and spikes cost)."""
    W, H = st.W, st.H
    dist = [[UNREACHED] * W for _ in range(H)]
    q = deque()
    for tx, ty in targets:
        if 0 <= tx < W and 0 <= ty < H:
            dist[ty][tx] = 0
            q.append((tx, ty))
    while q:
        x, y = q.popleft()
        d = dist[y][x] + 1
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < W and 0 <= ny < H and dist[ny][nx] > d:
                k = st.grid[ny][nx]
                if k == "wall" or (k == "pit" and st.topdown):
                    continue
                dist[ny][nx] = d
                q.append((nx, ny))
    return dist


class Bot:
    def __init__(self, stage, step=STEP, weight=5):
        self.weight = weight
        self.start = st = stage.clone()
        st.paused = None
        self.step = step
        self.moves = moves_for(st)
        exits = [(x, y) for y in range(st.H) for x in range(st.W) if st.grid[y][x] == "exit"]
        self.to_exit = walk_map(st, exits) if exits else None
        self.maps = {}
        self.per_tile = max(1, FP // max(1, st.ph["speed"]))      # ticks a tile takes, running
        self.big = (st.W + st.H) * self.per_tile

    def _from(self, at):
        """Tiles from ``at`` to every tile (worked out once for each tile asked about)."""
        m = self.maps.get(at)
        if m is None:
            m = self.maps[at] = walk_map(self.start, [at])
        return m

    def _near(self, st, places):
        p = st.player
        tx, ty = clamp_tile(st, p.cx // FP, p.cy // FP)
        return min([self._from(at)[ty][tx] for at in places] or [UNREACHED])

    def h(self, st):
        """Ticks to the goal, about: each thing still to do counts more than any walk to it, so doing one
        always brings the goal nearer."""
        p = st.player
        tx, ty = clamp_tile(st, p.cx // FP, p.cy // FP)
        big = self.big
        hurt = (st.max_health - st.health) * big // 4
        g = st.goal
        if g == "survive":
            return max(0, st.time_ticks - st.ticks) + hurt
        if g == "clear":
            alive = [e for e in st.enemies if e.alive]
            if not alive:
                return 0
            near = self._near(st, [clamp_tile(st, e.cx // FP, e.cy // FP) for e in alive])
            return sum(e.hp for e in alive) * big + min(near, big) * self.per_tile + hurt
        left = max(0, (st.chips_total if g == "chips" else st.need) - st.chips)
        places = [at for at, what in st.items.items() if what == "chip"] if left else []
        door = any(k == "door" for row in st.grid for k in row)
        if door and not st.keys:
            keys = [at for at, what in st.items.items() if what == "key"]
            if keys:
                left += 1
                places += keys
        if left:
            return left * big + min(self._near(st, places), big) * self.per_tile + hurt
        if self.to_exit is None:
            return hurt
        return min(self.to_exit[ty][tx], big) * self.per_tile + hurt

    def key(self, st):
        p = st.player
        return (p.x // 64, p.y // 64, (p.vx > 0) - (p.vx < 0), max(-3, min(3, p.vy // 64)), p.climbing,
                st.chips, st.keys, st.health, len(st.items), sum(e.hp for e in st.enemies if e.alive),
                st.ticks // (st.rate * 2) if st.goal == "survive" else 0)

    def run(self, budget=6000):
        """The moves that clear the stage, or None. ``budget``: copies looked on from, at most."""
        start = self.start
        tie = itertools.count()
        heap = [(self.h(start), next(tie), start, None)]
        seen = {self.key(start)}
        self.looked = 0
        while heap and self.looked < budget:
            _, _, st, node = heapq.heappop(heap)
            self.looked += 1
            held = node[0] if node else ()
            for mv in self.moves:
                t = st.clone()
                now = frozenset(mv)
                for i in range(self.step):
                    pressed = sorted(now - frozenset(held)) if i == 0 else ()
                    released = sorted(frozenset(held) - now) if i == 0 else ()
                    t.step(Controls(t.tick, now, pressed, released))
                    if t.result:
                        break
                if t.result == "won":
                    path = [mv]
                    n = node
                    while n:
                        path.append(n[0])
                        n = n[1]
                    self.path = path[::-1]
                    return self.path
                if t.result or t.deaths > st.deaths or t.dying:
                    continue
                k = self.key(t)
                if k in seen:
                    continue
                seen.add(k)
                heapq.heappush(heap, (t.ticks + self.weight * self.h(t), next(tie), t, (mv, node)))
        self.path = None
        return None

    def journal(self, path=None):
        """Key events for the moves, by tick (keys read as a kitty terminal reads them): an Enter starts
        the stage, and the first move's keys go down as it comes up; each move holds its keys ``step``
        ticks."""
        out = [[0, [["enter", PRESS]]]]
        held = ()
        tick = 1
        for mv in (path if path is not None else self.path) or []:
            evs = [["enter", RELEASE]] if tick == 1 else []
            evs += [[k, RELEASE] for k in held if k not in mv]
            evs += [[k, REPEAT if k in held else PRESS] for k in mv]
            if evs:
                out.append([tick, evs])
            held = mv
            tick += self.step
        if held:
            out.append([tick, [[k, RELEASE] for k in held]])
        return out


def clamp_tile(st, tx, ty):
    return max(0, min(st.W - 1, tx)), max(0, min(st.H - 1, ty))


def solve(stage, budget=6000, step=STEP):
    """``(moves, journal)`` that clear the stage, or ``(None, None)``."""
    bot = Bot(stage, step)
    path = bot.run(budget)
    return (path, bot.journal()) if path is not None else (None, None)


def main(argv=None):
    import os
    import time
    from .data import GameData
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    path = argv.pop(0)
    data = GameData(path if os.path.isdir(path) else os.path.join("games", path))
    ids = argv or sorted(data.stages)
    bad = 0
    for sid in ids:
        t0 = time.time()
        bot = Bot(make(data, sid))
        moves = bot.run(budget=20000)
        took = time.time() - t0
        if moves is None:
            bad += 1
            print("%s: no way through found (%d positions, %.1fs)" % (sid, bot.looked, took))
        else:
            print("%s: cleared in %.1f seconds of play (%d moves, %d positions, %.1fs)"
                  % (sid, len(moves) * bot.step / float(bot.start.rate), len(moves), bot.looked, took))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
