# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""A simple player for first-person levels: for tests, for balance, and for the editor's check.

It walks to its goals in order (the level's ``"bot"`` list: item ids or map
characters; the exit ``E`` last), turns to face what it can see, shoots with the
gun that suits the distance, sidesteps fire and steps off a boss's marked floor.
It is not clever: if it can finish a level, a person can.
"""
from .firstperson import DIRS
from .level import Level, TextConsole


class Bot(TextConsole):
    def __init__(self, lv, goals, verbose=False):
        super().__init__(self.out, None)
        self.lv, self.goals, self.verbose = lv, list(goals), verbose
        self.lines = []
        self.turns = 0
        self.last = None
        self.exit = None

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

    def step(self, lv, dx, dy):
        """A step to (dx, dy) without turning: forwards, back, or to the side."""
        f = lv.player.facing
        return {DIRS[f]: "k", DIRS[(f + 1) % 4]: "l", DIRS[(f + 2) % 4]: "j", DIRS[(f + 3) % 4]: "h"}[(dx, dy)]

    def go(self, lv, x, y):
        """The next command on the shortest way to (x, y), or None when there or there is no way.

        It searches forward from where the player stands, so it knows that a step on to
        slick floor or oil goes on until something stops it (and takes what lies on the way),
        and it keeps off burning floor unless there is no other way."""
        p = lv.player
        if (p.x, p.y) == (x, y):
            return None
        for hot in (False, True):
            first = {(p.x, p.y): None}
            frontier = [(p.x, p.y)]
            found = None
            while frontier and found is None:
                nxt = []
                for (cx, cy) in frontier:
                    for dx, dy in DIRS:
                        n = (cx + dx, cy + dy)
                        if not self.open_cell(lv, n, hot and n != (x, y)):
                            continue
                        way = [n] + lv.slide_path(n[0], n[1], dx, dy) if (cx, cy) == (p.x, p.y) else \
                            [n] + self.slide(lv, n, dx, dy)
                        end = way[-1]
                        if end in first:
                            if (x, y) in way and found is None:
                                found = first[(cx, cy)] or (dx, dy)
                            continue
                        first[end] = first[(cx, cy)] or (dx, dy)
                        if (x, y) in way:
                            found = first[end]
                            break
                        nxt.append(end)
                    if found:
                        break
                frontier = nxt
            if found:
                dx, dy = found
                if lv.monster_at(p.x + dx, p.y + dy):           # blocked by a monster: face it and shoot
                    return self.face(lv, dx, dy) or "f"
                return self.face(lv, dx, dy) or "k"
        return None

    def open_cell(self, lv, n, careful):
        c = lv.cell(*n)
        if c.kind in ("wall", "panel", "exit") or c.crate or (c.kind == "door" and (c.sealed or c.open_while)):
            return False
        if c.kind == "door" and c.key and c.key not in lv.player.keys and c.open < 1:
            return False
        m = lv.monster_at(*n)
        if m is not None and m.barrel:
            return False
        return not (careful is False and n in getattr(lv, "fires", {}))

    def slide(self, lv, n, dx, dy):
        """Where a slide from ``n`` would go, walls and crates only (the bot plans ahead, monsters move)."""
        out = []
        x, y = n
        while lv.cell(x, y).slick and len(out) < 40 and self.open_cell(lv, (x + dx, y + dy), True):
            x, y = x + dx, y + dy
            out.append((x, y))
        return out

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
                            self.exit = (c.x, c.y)
                            for dx, dy in DIRS:              # stand in front of it
                                if lv.cell(c.x + dx, c.y + dy).kind == "floor":
                                    return c.x + dx, c.y + dy
                            return c.x, c.y
                        if not (c.on_enter and c.on_enter in lv.events):
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
        # out of the fire, and out of line of a flamethrower that levels its nozzle
        fires = getattr(lv, "fires", {})
        safe = [(dx, dy) for dx, dy in DIRS if lv.free(p.x + dx, p.y + dy) and (p.x + dx, p.y + dy) not in fires
                and (p.x + dx, p.y + dy) not in lv.marks and not lv.cell(p.x + dx, p.y + dy).toxic]
        if (p.x, p.y) in fires and safe:
            return self.step(lv, *safe[0])
        for m in lv.monsters:
            a = m.spec.get("attack") or {}
            if not m.dead and m.intent == "windup" and a.get("kind") == "flame" and (m.x == p.x or m.y == p.y) \
                    and lv.dist(m) <= int(a.get("range", 3)) and lv.line_of_sight(m.x, m.y, p.x, p.y):
                aside = [d for d in safe if p.x + d[0] != m.x and p.y + d[1] != m.y]
                if aside:
                    return self.step(lv, *aside[0])
        # out of sight of a gun that has spun up: it winds down, and comes to the door
        for m in lv.monsters:
            if not m.dead and not m.gone and m.spun and lv.line_of_sight(m.x, m.y, p.x, p.y):
                away = [d for d in safe if not lv.cell(p.x + d[0], p.y + d[1]).slick]
                hidden = [d for d in away if not lv.line_of_sight(m.x, m.y, p.x + d[0], p.y + d[1])]
                back = [d for d in away if abs(p.x + d[0] - m.x) + abs(p.y + d[1] - m.y) > abs(p.x - m.x) + abs(p.y - m.y)
                        and lv.cell(p.x, p.y).kind == "door"]             # out of a doorway; in the open, fight
                if hidden or back:
                    return self.step(lv, *(hidden or back)[0])
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
                if self.exit and lv.cell(*self.exit).kind == "exit":
                    t = self.face(lv, self.exit[0] - p.x, self.exit[1] - p.y) \
                        if abs(self.exit[0] - p.x) + abs(self.exit[1] - p.y) == 1 else None
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


def play(data, level, seed=1, verbose=False, goals=None):
    """Play ``level`` of a loaded game once: ``("exit" | "dead" | "quit", the Level)``."""
    lv = Level(data, level, seed=seed)
    bot = Bot(lv, goals if goals is not None else (lv.spec.get("bot") or ["E"]), verbose)
    return lv.run(bot), lv


def check(data, level, runs=5):
    """How the bot fares in ``runs`` games of a level, as a summary the editor can show."""
    games = []
    for seed in range(runs):
        outcome, lv = play(data, level, seed)
        games.append({"seed": seed, "outcome": outcome if outcome != "quit" else "stuck", "beats": lv.beat,
                      "health": lv.player.hp, "kills": lv.stats["kills"], "secrets": lv.stats["secrets"],
                      "where": [lv.player.x, lv.player.y]})
    lv = Level(data, level, seed=0)
    return {"games": games, "finished": sum(1 for g in games if g["outcome"] == "exit"), "runs": runs,
            "par": lv.par, "monsters": lv.total_kills, "items": lv.total_items, "secrets": lv.total_secrets,
            "goals": list(lv.spec.get("bot") or ["E"]), "size": [lv.w, lv.h]}
