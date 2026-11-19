# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""A player for first-person levels, for tests and balance.

    python tests/levelbot.py [runs] [game] [level]

It walks to its goals in order (the level's ``"bot"`` list: items or map
characters), turns to face what it can see, shoots with the gun that suits the
distance, sidesteps fire and steps off a boss's marked floor.  It is not
clever; if it can finish a level, a person can.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine.data import GameData  # noqa: E402
from engine.firstperson import DIRS  # noqa: E402
from engine.level import Level, TextConsole  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class Bot(TextConsole):
    def __init__(self, lv, goals, verbose=False):
        super().__init__(self.out, None)
        self.lv, self.goals, self.verbose = lv, list(goals), verbose
        self.lines = []
        self.turns = 0
        self.last = None

    def out(self, text):
        self.lines.append(text)
        if self.verbose:
            print(text)

    def page(self, lv, lines, automap=False):
        pass

    def read(self, lv):
        self.turns += 1
        if self.turns > 1500:
            return None
        cmd = self.decide(lv)
        if not cmd.startswith("turn"):
            self.last = None
        if self.verbose:
            print("> %s   (%d,%d %s hp %d)" % (cmd, lv.player.x, lv.player.y, "NESW"[lv.player.facing], lv.player.hp))
        return cmd

    # ---- where things are ------------------------------------------------ #
    def face(self, lv, dx, dy):
        """The command that turns towards (dx, dy), or None when already facing it."""
        want = DIRS.index((dx, dy))
        d = (want - lv.player.facing) % 4
        return None if d == 0 else {1: "turn right", 2: "turn around", 3: "turn left"}[d]

    def go(self, lv, x, y):
        p = lv.player
        if (p.x, p.y) == (x, y):
            return None
        dist = {}
        frontier = [(x, y)]
        dist[(x, y)] = 0
        while frontier:
            nxt = []
            for (cx, cy) in frontier:
                for dx, dy in DIRS:
                    n = (cx + dx, cy + dy)
                    if n in dist:
                        continue
                    c = lv.cell(*n)
                    if c.kind in ("wall", "panel", "exit") or (c.kind == "door" and c.sealed):
                        continue
                    if c.kind == "door" and c.key and c.key not in p.keys and c.open < 1:
                        continue
                    m = lv.monster_at(*n)
                    if m is not None and m.barrel:
                        continue
                    dist[n] = dist[(cx, cy)] + 1
                    nxt.append(n)
            frontier = nxt
            if (p.x, p.y) in dist:
                break
        here = dist.get((p.x, p.y))
        if here is None:
            return None
        for dx, dy in DIRS:
            n = (p.x + dx, p.y + dy)
            if dist.get(n, 999) < here and not lv.monster_at(*n):
                return self.face(lv, dx, dy) or "k"
        for dx, dy in DIRS:                              # blocked by a monster: face it and shoot
            n = (p.x + dx, p.y + dy)
            if dist.get(n, 999) < here:
                return self.face(lv, dx, dy) or "f"
        return None

    def goal_cell(self, lv):
        while self.goals:
            g = self.goals[0]
            for it in lv.items:
                if it.iid == g and not it.taken:
                    return it.x, it.y
            for row in lv.grid:
                for c in row:
                    if c.ch == g and (c.kind != "exit" or not c.pressed):
                        if c.kind == "exit":
                            return c.x, c.y + 1 if lv.cell(c.x, c.y + 1).kind == "floor" else c.y
                        if not (c.ch == "T" and "arena" in lv.events):
                            return c.x, c.y
            self.goals.pop(0)
        return None

    # ---- what to do ------------------------------------------------------ #
    def decide(self, lv):
        p = lv.player
        # off the scheduled fire
        if (p.x, p.y) in lv.marks:
            for dx, dy in DIRS:
                n = (p.x + dx, p.y + dy)
                if lv.free(*n) and n not in lv.marks:
                    return self.face(lv, dx, dy) or "k"
        # out of a fireball's way
        for s in lv.shots:
            nxt = s.path[s.i + 1: s.i + 1 + s.speed]
            if (p.x, p.y) in nxt:
                for side in ("h", "l"):
                    fx, fy = DIRS[p.facing]
                    rx, ry = DIRS[(p.facing + 1) % 4]
                    k = -1 if side == "h" else 1
                    n = (p.x + rx * k, p.y + ry * k)
                    if lv.free(*n) and n not in [c for c in s.path[s.i:]] and n not in lv.marks:
                        return side
        target = self.target(lv)
        if lv.cell(p.x, p.y).toxic and target:            # never stand on toxic floor: get across
            step = self.go(lv, *target)
            if step:
                return step
        weapon = self.pick_weapon(lv)
        if weapon:
            return weapon
        cone = [m for m in lv.cone() if not m.barrel or self.barrel_worth(lv, m)]
        if cone:
            m = cone[0]
            return "f %s" % m.tag
        # something awake and near but not in front: face it
        near = sorted([m for m in lv.monsters if not m.dead and not m.gone and m.awake and not m.barrel
                       and lv.dist(m) <= 6 and lv.line_of_sight(p.x, p.y, m.x, m.y)], key=lv.dist)
        if near and self.last != "turned":
            m = near[0]
            dx, dy = m.x - p.x, m.y - p.y
            d = (dx // abs(dx), 0) if abs(dx) >= abs(dy) and dx else (0, dy // abs(dy) if dy else 1)
            t = self.face(lv, *d)
            if t:
                self.last = "turned"
                return t
        if target is not None and target != self.goal_cell(lv):
            step = self.go(lv, *target)
            if step:
                return step
        goal = self.goal_cell(lv)
        if goal is None:
            return "w"
        step = self.go(lv, *goal)
        if step is None:
            if self.goals:
                g = self.goals[0]
                if g == "E":
                    fx, fy = DIRS[p.facing]
                    t = self.face(lv, 0, -1)
                    return t or "use"
                self.goals.pop(0)
            return "w"
        return step

    def target(self, lv):
        """Where to go now: a known medkit when hurt, else the next goal."""
        p = lv.player
        if p.hp < 45:
            meds = [it for it in lv.items if not it.taken and "health" in it.pickup and (it.x, it.y) in lv.seen_cells]
            if meds:
                it = min(meds, key=lambda it: abs(it.x - p.x) + abs(it.y - p.y))
                return it.x, it.y
        return self.goal_cell(lv)

    def barrel_worth(self, lv, b):
        p = lv.player
        if max(abs(b.x - p.x), abs(b.y - p.y)) <= 2:
            return False
        return any(not m.dead and not m.barrel and m.awake and max(abs(m.x - b.x), abs(m.y - b.y)) <= 1
                   for m in lv.monsters)

    def pick_weapon(self, lv):
        p = lv.player
        cone = lv.cone()
        if not cone:
            return None
        d = lv.dist(cone[0])
        want = "1"
        if p.ammo.get("bullets", 0) > 0:
            want = "2"
        if "4" in p.weapons and p.ammo.get("bullets", 0) >= 2:
            want = "4"
        if "3" in p.weapons and p.ammo.get("shells", 0) > 0 and (d <= 3 or want == "1"):
            want = "3"
        if want != p.weapon and want in p.weapons:
            return want
        return None


def play(game="rootless", level="e1m1", seed=1, verbose=False):
    data = GameData(os.path.join(ROOT, "games", game))
    lv = Level(data, level, seed=seed)
    goals = lv.spec.get("bot") or []
    bot = Bot(lv, goals, verbose)
    outcome = lv.run(bot)
    return outcome, lv


if __name__ == "__main__":
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    game = sys.argv[2] if len(sys.argv) > 2 else "rootless"
    level = sys.argv[3] if len(sys.argv) > 3 else "e1m1"
    results = []
    for seed in range(runs):
        outcome, lv = play(game, level, seed, verbose=runs == 1)
        results.append((outcome, lv.beat, lv.player.hp, lv.stats["kills"], lv.total_kills, lv.stats["secrets"],
                        lv.boss.gone if lv.boss else None))
        print(seed, *results[-1])
    wins = [r for r in results if r[0] == "exit"]
    print("finished %d of %d; beats %s" % (len(wins), runs, sorted(r[1] for r in wins)))
