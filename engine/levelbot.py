# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""A simple player for first-person levels: for tests, for balance, and for the editor's check.

It walks to its goals in order (the level's ``"bot"`` list: item ids or map
characters; the exit ``E`` last; ``board`` climbs into the nearest vehicle and
``out`` climbs down), turns to face what it can see, shoots with the gun that suits
the distance, sidesteps fire and steps off a boss's marked floor. It is not clever:
if it can finish a level, a person can.
"""
import math

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
        self.fields = {}                                 # open land: the way to a goal from everywhere, by goal

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
        if getattr(lv, "world", None) is not None:
            return self.go_window(lv, x, y)
        if getattr(lv, "land", None) is not None:
            return self.go_far(lv, x, y)
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
                m = lv.monster_at(p.x + dx, p.y + dy)
                if m is not None and not m.vehicle:             # blocked by a monster: face it and shoot
                    return self.face(lv, dx, dy) or "f"
                return self.face(lv, dx, dy) or "k"
        return None

    def go_far(self, lv, x, y):
        """In open land: a step down the way to (x, y) worked out from the goal over the whole land (a search
        from the player each beat is too slow there), kept a while and worked out again as things change."""
        p = lv.player
        flying = p.vehicle is not None and bool(p.vehicle.vehicle.get("fly"))
        key = (x, y, flying, p.vehicle is not None)
        got = self.fields.get(key)
        if got is None or lv.beat - got[0] >= 25:
            if len(self.fields) > 6:
                self.fields.clear()
            got = self.fields[key] = (lv.beat, self.field_to(lv, x, y))
        field = got[1]
        here = field.get((p.x, p.y))
        best = None
        for dx, dy in DIRS:
            n = (p.x + dx, p.y + dy)
            d = field.get(n)
            if d is None or not self.open_cell(lv, n, True) or (here is not None and d >= here):
                continue
            if best is None or d < best[0]:
                best = (d, dx, dy)
        if best is None:
            self.fields.pop(key, None)                   # the way is shut: work it out again next beat
            return None
        _, dx, dy = best
        m = lv.monster_at(p.x + dx, p.y + dy)
        if m is not None and not m.vehicle:             # blocked by a monster: face it and shoot
            return self.face(lv, dx, dy) or "f"
        return self.face(lv, dx, dy) or "k"

    def go_window(self, lv, x, y, R=44):
        """In a world without end: the way within ``R`` cells round the player to the goal, or (when the goal
        is further, or cannot be reached from here) to the reachable cell nearest it; kept a few beats."""
        p = lv.player
        plan = getattr(self, "plan", None)
        if plan and plan[0] == (x, y) and lv.beat - plan[1] < 10 and plan[2] and plan[2][0] == (p.x, p.y):
            path = plan[2]
        else:
            path = self.window_path(lv, x, y, R)
        if len(path) < 2:
            self.plan = None
            return None
        nx, ny = path[1]
        if not self.open_cell(lv, (nx, ny), True):
            self.plan = None
            m = lv.monster_at(nx, ny)
            if m is not None and not m.vehicle:
                return self.face(lv, nx - p.x, ny - p.y) or "f"
            path = self.window_path(lv, x, y, R)
            if len(path) < 2:
                return None
            nx, ny = path[1]
        turn = self.face(lv, nx - p.x, ny - p.y)
        if turn:
            self.plan = ((x, y), lv.beat, path)
            return turn
        m = lv.monster_at(nx, ny)
        if m is not None and not m.vehicle:
            return "f"
        self.plan = ((x, y), lv.beat, path[1:])
        return "k"

    def window_path(self, lv, gx, gy, R):
        import heapq
        p = lv.player
        start = (p.x, p.y)
        parked = {(m.x, m.y) for m in lv.monsters if not m.dead and not m.gone and (m.vehicle or m.barrel)}
        parked.discard((gx, gy))
        safe = p.vehicle is not None or p.boots > 0           # acid does not hurt: no reason to go round it
        cost = {start: 0}
        came = {start: None}
        heap = [(0, start)]
        best, best_k = start, math.hypot(gx - p.x, gy - p.y)
        while heap:
            d, c = heapq.heappop(heap)
            if d > cost[c]:
                continue
            if c == (gx, gy):
                best = c
                break
            k = math.hypot(gx - c[0], gy - c[1]) + 0.15 * d
            if k < best_k:
                best, best_k = c, k
            for dx, dy in DIRS:
                n = (c[0] + dx, c[1] + dy)
                if abs(n[0] - p.x) > R or abs(n[1] - p.y) > R or n in parked:
                    continue
                cell = lv.cell(*n)
                if not self.open_ground(lv, cell):
                    continue
                nd = d + (1 if safe or not cell.toxic else 8)
                if nd < cost.get(n, 1 << 30):
                    cost[n], came[n] = nd, c
                    heapq.heappush(heap, (nd, n))
        path = []
        c = best
        while c is not None:
            path.append(c)
            c = came[c]
        return path[::-1]

    def field_to(self, lv, gx, gy):
        """Steps to (gx, gy) from every cell (toxic ones count three), for go_far."""
        import heapq
        dist = {(gx, gy): 0}
        heap = [(0, gx, gy)]
        parked = {(m.x, m.y) for m in lv.monsters if not m.dead and not m.gone and (m.vehicle or m.barrel)}
        parked.discard((gx, gy))                         # machines and barrels stay put: go round them
        while heap:
            d, cx, cy = heapq.heappop(heap)
            if d > dist[(cx, cy)]:
                continue
            here = lv.cell(cx, cy)
            cost = 3 if here.toxic else 1
            for dx, dy in DIRS:
                n = (cx + dx, cy + dy)
                if not (0 <= n[0] < lv.w and 0 <= n[1] < lv.h) or n in parked or not self.open_ground(lv, lv.cell(*n)):
                    continue
                nd = d + cost
                if nd < dist.get(n, 1 << 30):
                    dist[n] = nd
                    heapq.heappush(heap, (nd, n[0], n[1]))
        return dist

    def open_ground(self, lv, c):
        """Can the player stand on (or fly over) this cell, things that move aside?"""
        if c.kind in ("wall", "panel", "exit", "switch") or c.crate or (c.kind == "door" and (c.sealed or c.open_while)):
            return False
        if c.kind == "door" and c.key and c.key not in lv.player.keys and c.open < 1:
            return False
        v = lv.player.vehicle
        if v is not None and (c.kind == "door" or c.teleport or c.lift):
            return False                                 # a machine goes through no doors
        if (c.deep or c.steep) and not (v is not None and v.vehicle.get("fly")):
            return False                                 # deep water, a cliff: only flying
        return True

    def open_cell(self, lv, n, careful):
        c = lv.cell(*n)
        if not self.open_ground(lv, c):
            return False
        m = lv.monster_at(*n)
        if m is not None and m.vehicle:
            return bool(self.goals) and self.goals[0] == "board"
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
            if g == "board":
                if lv.player.vehicle is None:
                    rides = [m for m in lv.monsters if m.vehicle and not m.dead]
                    if rides:
                        m = min(rides, key=lambda m: abs(m.x - lv.player.x) + abs(m.y - lv.player.y))
                        return m.x, m.y
                self.goals.pop(0)
                continue
            if g == "out":
                return lv.player.x, lv.player.y
            for it in lv.items:
                if it.iid == g and not it.taken:
                    return it.x, it.y
            for row in lv.grid:
                for c in row:
                    if c.ch == g and (c.kind not in ("exit", "switch") or not c.pressed):
                        if c.kind in ("exit", "switch"):
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
        if self.goals and self.goals[0] == "out":
            self.goals.pop(0)
            if p.vehicle is not None:
                return "out"
        if p.vehicle is not None and "fuel" in p.vehicle.vehicle and p.vehicle.fuel <= 0 and not p.vehicle.started:
            return "out"                                 # the tanks are dry: on foot from here
        if p.vehicle is not None:                      # riding: claw what is in reach (or shoot), else on to the goal
            ahead = lv.monster_at(p.x + DIRS[p.facing][0], p.y + DIRS[p.facing][1])
            if ahead is not None and not ahead.barrel:
                return "f"
            if p.vehicle.vehicle.get("gun") and any(not m.barrel for m in lv.cone()):
                return "f"
            goal = self.goal_cell(lv)
            step = self.go(lv, *goal) if goal is not None else None
            if step is None and self.goals:
                self.goals.pop(0)
                return "w"
            return step or "w"
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
        # out of the way of a ball rolling at him: aside if he can, else on, away from it
        for b in lv.monsters:
            if not getattr(b, "ball", False) or not b.rolling or b.gone:
                continue
            dx, dy = b.rolling
            ahead = (p.x - b.x) * dx + (p.y - b.y) * dy
            if (p.x - b.x) * dy - (p.y - b.y) * dx == 0 and 0 < ahead <= 8:
                aside = [(dy, dx), (-dy, -dx)]
                for sx, sy in aside:
                    if lv.free(p.x + sx, p.y + sy) and not lv.cell(p.x + sx, p.y + sy).toxic:
                        return self.step(lv, sx, sy)
                if lv.free(p.x + dx, p.y + dy):
                    return self.face(lv, dx, dy) or "k"
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
        w = lv.weapons.get(p.weapon) or {}
        if w.get("kind") == "melee":                     # fists or a blade: only what is in reach
            cone = [m for m in cone if lv.dist(m) <= 1]
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
                if self.exit and lv.cell(*self.exit).kind in ("exit", "switch") and not lv.cell(*self.exit).pressed:
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
        if getattr(lv, "world", None) is not None and p.vehicle is None:   # a long way to go: take what helps
            def helps(it):
                pk = it.pickup
                if "health" in pk:
                    return p.hp < 90
                if pk.get("weapon") or pk.get("armor"):
                    return True
                return any(p.ammo.get(a, 0) < (12 if a == "shells" else 30) for a in (pk.get("ammo") or {}))
            near = [it for it in lv.items if not it.taken and (it.x, it.y) in lv.seen_cells
                    and max(abs(it.x - p.x), abs(it.y - p.y)) <= 7 and helps(it)]
            if near:
                it = min(near, key=lambda it: abs(it.x - p.x) + abs(it.y - p.y))
                return it.x, it.y
        return self.goal_cell(lv)

    def barrel_worth(self, lv, b):
        p = lv.player
        if getattr(b, "ball", False) or max(abs(b.x - p.x), abs(b.y - p.y)) <= 2:
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
            "goals": list(lv.spec.get("bot") or ["E"]),
            "size": None if getattr(lv, "world", None) is not None else [lv.w, lv.h]}   # a world has no size
