# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Levels without end: made a chunk at a time round the player, as he goes.

A level with a ``"world"`` block is never built whole. Its ground is worked out a chunk (16 x 16 cells)
at a time, when something looks at it. Its monsters and items wake with the chunks round the player and
go to sleep where they stand when he has gone on. What changed in a chunk - a door opened, a monster
hurt or moved, an item taken - is kept for when he comes back; a chunk nobody touched is forgotten and
made again, the same, if he does.

Two kinds of ground:

- ``"land"``: the level's ``"land"`` going on for ever, with **sites** (small maps: a camp, a ruin, a
  beacon) set down on it, some at fixed places, some here and there by chance.
- ``"dungeon"``: rooms and corridors, a room to a chunk, without end; it gets harder the further one goes.

Everything is made from the level's seed and the chunk's place, so the same seed makes the same world,
and a save (its lines played back) comes out the same.
"""
from __future__ import annotations

import json
import math
import random

from .level import CELL_STATE as MUTABLE, cell_state as _state

N = 16                       # a chunk is N x N cells
ORIGIN = 1 << 20             # where the start is: room to go a long way each way
SIZE = 1 << 21
WALL_KINDS = ("wall", "panel", "exit", "switch", "door")


def _hash(*parts):
    """0..1 from anything, the same every time and on every machine."""
    x = 2166136261
    for ch in "/".join(str(p) for p in parts).encode("utf-8"):
        x = ((x ^ ch) * 16777619) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 2246822519) & 0xFFFFFFFF
    x ^= x >> 13
    return x / 4294967296.0



def _weighted(rng, table):
    total = sum(max(0.0, float(t.get("weight", 1))) for t in table)
    if total <= 0:
        return None
    r = rng.random() * total
    for t in table:
        r -= max(0.0, float(t.get("weight", 1)))
        if r < 0:
            return t
    return table[-1]


def _span(v, default):
    """[lo, hi] or a number, as (lo, hi)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v), int(v)
    if isinstance(v, list) and len(v) == 2 and all(isinstance(a, (int, float)) for a in v):
        return int(min(v)), int(max(v))
    return default


class Chunks:
    """The chunks of a level without end: made, woken, put to sleep and forgotten as the player goes."""

    def __init__(self, lv, spec):
        self.lv, self.spec = lv, spec
        self.kind = str(spec.get("kind", "land"))
        self.r = max(1, int(spec.get("awake", 2)))           # chunks each way round the player that are awake
        self.keep_r = max(self.r + 2, int(spec.get("keep", 6)))   # cells further off than this are forgotten
        self.loaded = {}                                     # (kx, ky) -> its 256 cells, row by row
        self.sigs = {}                                       # (kx, ky) -> its cells' states as made
        self.changes = {}                                    # (kx, ky) -> {i: state} of a forgotten chunk
        self.awake, self.spawned, self.counted = set(), set(), {}
        self.sleepers = {}                                   # (kx, ky) -> the monsters and items asleep there
        self.pinned = set()                                  # chunks always kept (a goal's)
        self.walls = set()                                   # map walls standing on open land, in loaded chunks
        self.secret_chunks = set()
        self.here = None
        self.start = (ORIGIN, ORIGIN)
        self.facing = None
        self.maker = (DungeonMaker if self.kind == "dungeon" else LandMaker)(self, lv, spec)

    # ---- the grid -------------------------------------------------------- #
    def __iter__(self):
        """The loaded chunks' cells, a chunk at a time (in place of a level's rows)."""
        return iter(list(self.loaded.values()))

    def cell(self, x, y):
        cells = self.loaded.get((x >> 4, y >> 4))
        if cells is None:
            if not (0 <= x < SIZE and 0 <= y < SIZE):
                from .level import VOID
                return VOID
            cells = self.load((x >> 4, y >> 4))
        return cells[((y & 15) << 4) | (x & 15)]

    def load(self, key):
        cells = self.maker.cells(*key)
        self.sigs[key] = [_state(c) for c in cells]
        diff = self.changes.pop(key, None)
        if diff:
            for i, state in diff.items():
                for name, v in zip(MUTABLE, state):
                    setattr(cells[i], name, v)
        self.loaded[key] = cells
        lv = self.lv
        for c in cells:
            if c.plate:
                lv.plate_cells.append(c)
            if c.open_while:
                lv.held_cells.append(c)
            if c.conveyor is not None:
                lv.belts.append(c)
            if self.kind == "land" and (c.x, c.y) in lv.land.stamp and c.kind in WALL_KINDS:
                self.walls.add((c.x, c.y))
        return cells

    def evict(self, key):
        """Forget a chunk's cells, keeping only what changed in them."""
        cells = self.loaded.pop(key)
        sig = self.sigs.pop(key)
        diff = {i: _state(c) for i, c in enumerate(cells) if _state(c) != sig[i]}
        if diff:
            self.changes[key] = diff
        lv = self.lv
        gone = set(map(id, cells))
        for name in ("plate_cells", "held_cells", "belts"):
            have = getattr(lv, name)
            if any(id(c) in gone for c in have):
                setattr(lv, name, [c for c in have if id(c) not in gone])
        for c in cells:
            self.walls.discard((c.x, c.y))
        self.maker.forget(*key)

    # ---- waking and sleeping --------------------------------------------- #
    def wake(self, key):
        if key not in self.loaded:
            self.load(key)
        lv = self.lv
        if key not in self.secret_chunks:                    # its secrets count once it has been near the player
            self.secret_chunks.add(key)
            lv.total_secrets += sum(1 for i, c in enumerate(self.loaded[key]) if self.sigs[key][i][MUTABLE.index("secret")])
        if key not in self.spawned:
            self.spawned.add(key)
            n = 0
            for what, name, x, y, extra in self.maker.spawns(*key):
                if what == "monster":
                    m = lv.add_monster(name, x, y)
                    if m is None:
                        continue
                    m.home, m.spawned = key, (x, y, m.hp)
                    if extra.get("awake"):
                        m.awake = True
                    if not m.barrel and not m.spec.get("boss"):
                        lv.total_kills += 1
                else:
                    it = lv.add_item(name, x, y)
                    if it is None:
                        continue
                    it.home, it.spawned = key, (x, y)
                    it.on_pickup = extra.get("on_pickup")
                    lv.total_items += 1
                n += 1
            self.counted[key] = n
        for obj in self.sleepers.pop(key, ()):
            (lv.monsters if hasattr(obj, "hp") else lv.items).append(obj)
        self.awake.add(key)

    def follow(self, force=False):
        """After a beat: wake the chunks round the player, put the ones he left to sleep, forget far ones."""
        p = self.lv.player
        here = (p.x >> 4, p.y >> 4)
        moved = here != self.here
        self.here = here
        r = self.r
        if moved or force:
            hold = {(here[0] + i, here[1] + j) for i in range(-r - 1, r + 2) for j in range(-r - 1, r + 2)}
            self.awake &= hold                               # a chunk past the edge by one stays awake a while
        self.sleep_strays()
        if moved or force:
            for j in range(-r, r + 1):
                for i in range(-r, r + 1):
                    key = (here[0] + i, here[1] + j)
                    if key not in self.awake:
                        self.wake(key)
            kr = self.keep_r
            far = [k for k in self.loaded if k not in self.pinned and k not in self.awake
                   and max(abs(k[0] - here[0]), abs(k[1] - here[1])) > kr]
            for key in sorted(far):
                self.evict(key)
            self.maker.prune(here, kr + 1)
            seen = self.lv.seen_cells
            if len(seen) > 150000:                           # the map remembers the last 400 cells or so each way
                px, py = p.x, p.y
                self.lv.seen_cells = {c for c in seen if abs(c[0] - px) <= 400 and abs(c[1] - py) <= 400}

    def sleep_strays(self):
        """Monsters and items that are not in an awake chunk go to sleep where they are."""
        lv, awake = self.lv, self.awake
        going = {}
        keep = []
        for m in lv.monsters:
            key = (m.x >> 4, m.y >> 4)
            if key in awake:
                keep.append(m)
            else:
                going.setdefault(key, []).append(m)
        if going:
            lv.monsters = keep
        keep = []
        for it in lv.items:
            key = (it.x >> 4, it.y >> 4)
            if key in awake:
                keep.append(it)
            elif not it.taken:
                going.setdefault(key, []).append(it)
            else:
                going.setdefault(key, [])
        if len(keep) != len(lv.items):
            lv.items = keep
        for key in sorted(going):
            objs = [o for o in going[key] if not getattr(o, "dead", False) and not getattr(o, "gone", False)]
            got = self.sleepers.setdefault(key, [])
            got.extend(objs)
            if self.pristine(key, got, going[key]):
                del self.sleepers[key]                       # as it was made: made again when he comes back
                self.spawned.discard(key)
                lv.total_kills -= sum(1 for o in got if hasattr(o, "hp") and not o.barrel and not o.spec.get("boss"))
                lv.total_items -= sum(1 for o in got if not hasattr(o, "hp"))

    def pristine(self, key, objs, seen):
        if key not in self.spawned or len(objs) != self.counted.get(key) or len(seen) != len(objs):
            return False
        for o in objs:
            if getattr(o, "home", None) != key:
                return False
            if hasattr(o, "hp"):
                if o.awake or (o.x, o.y, o.hp) != o.spawned:
                    return False
            elif o.taken or (o.x, o.y) != o.spawned:
                return False
        return True

    def begin(self):
        for key in sorted(self.pinned):                  # fixed places are known from the start
            if key not in self.loaded:
                self.load(key)
        self.follow(force=True)

    # ---- what it holds --------------------------------------------------- #
    def meets(self):
        """The monsters and items this world can put about: (kinds, item ids), for the pictures to load."""
        return self.maker.meets()

    def known(self, ch):
        """Cells of a fixed place with this character (the goal's exit), loaded or not."""
        return self.maker.known(ch)


def _legend(lv, legend):
    from .level import LEGEND
    out = dict(LEGEND)
    out.update(lv.spec.get("legend") or {})
    out.update(legend or {})
    return out


def _cell_spec(lv, spec):
    if isinstance(spec, str):
        return {"monster": spec} if spec in (lv.data.monsters or {}) else {"item": spec}
    return dict(spec) if isinstance(spec, dict) else {}


# --------------------------------------------------------------------------- #
# open land without end
# --------------------------------------------------------------------------- #
class Site:
    """A small map set down on the land: a camp, a ruin, a beacon."""

    def __init__(self, lv, spec, i):
        self.spec = spec
        self.name = str(spec.get("name") or "site%d" % i)
        self.rows = [str(r) for r in spec.get("map") or []]
        self.w = max((len(r) for r in self.rows), default=0)
        self.h = len(self.rows)
        self.legend = _legend(lv, spec.get("legend"))
        self.chance = float(spec.get("chance", 0.0))
        self.away = float(spec.get("away", 0))
        self.spacing = max(0, int(spec.get("spacing", 2)))
        self.weight = float(spec.get("weight", 1))
        self.landmarks = [m for m in spec.get("landmarks") or [] if isinstance(m, dict)]

    def char(self, mx, my):
        if 0 <= my < self.h and 0 <= mx < len(self.rows[my]):
            return self.rows[my][mx]
        return " "


class LandMaker:
    def __init__(self, world, lv, spec):
        from .land import Land
        from . import firstperson as fp
        self.world, self.lv, self.spec = world, lv, spec
        lspec = dict(lv.spec.get("land") or {})
        lspec["edge"], lspec["size"] = "open", [SIZE, SIZE]
        self.seed = lv.world_seed
        self.land = Land(lspec, seed=self.seed & 0xFFFF)
        if "seed" not in (lv.spec.get("land") or {}) or lv.spec["world"].get("seed") == "run":
            self.land.seed = self.seed & 0xFFFF
        self.land.numbers += json.dumps({"world": spec, "seed": self.land.seed}, sort_keys=True, default=str)
        self.land.look(fp.sky_spec(lv.spec.get("sky")))
        lv.land = self.land
        sx, sy = world.start
        self.land.set_pad(sx - 3, sy - 3, sx + 3, sy + 3, lspec.get("pad"), lspec.get("blend", 6))
        self.base = self.land.base
        self.sites = [Site(lv, s, i) for i, s in enumerate(spec.get("sites") or []) if isinstance(s, dict)]
        self.chance_sites = [s for s in self.sites if s.chance > 0 and not isinstance(s.spec.get("at"), list)]
        self.fixed = []                                      # (site, x0, y0)
        for s in self.sites:
            at = s.spec.get("at")
            if isinstance(at, list) and len(at) == 2 and s.rows:
                x0 = sx + int(at[0]) - s.w // 2
                y0 = sy + int(at[1]) - s.h // 2
                self.fixed.append((s, x0, y0))
                for my, row in enumerate(s.rows):
                    for mx, ch in enumerate(row):
                        if isinstance(s.legend.get(ch), dict) and s.legend[ch].get("start"):
                            world.start = (x0 + mx, y0 + my)
        self.fixed_by_chunk = {}
        for site in self.fixed:
            s, x0, y0 = site
            for ky in range((y0 - 6) >> 4, ((y0 + s.h + 6) >> 4) + 1):
                for kx in range((x0 - 6) >> 4, ((x0 + s.w + 6) >> 4) + 1):
                    self.fixed_by_chunk.setdefault((kx, ky), []).append(site)
            for ky in range(y0 >> 4, ((y0 + s.h - 1) >> 4) + 1):
                for kx in range(x0 >> 4, ((x0 + s.w - 1) >> 4) + 1):
                    world.pinned.add((kx, ky))               # a fixed place is always known (its exit, say)
            for m in s.landmarks:
                at = m.get("at") or [0, 0]
                self.land.marks.append(dict(m, at=[x0 + int(at[0]), y0 + int(at[1])]))
                if m.get("solid"):
                    self.land.blocked.add((x0 + int(at[0]), y0 + int(at[1])))
            self.land.pads.append((x0 - 1, y0 - 1, x0 + s.w, y0 + s.h, self.base, 4.0))   # flat ground under it
        self.land.share()
        self.picked = {}                                     # (kx, ky) -> (site, x0, y0) or None
        self.marks_of = {}                                   # (kx, ky) -> the landmarks its site put up
        self.land.pad_fn = self.pads_in
        self.spawn_rules = [r for r in spec.get("spawns") or [] if isinstance(r, dict)]
        self.things = [t for t in spec.get("things") or [] if isinstance(t, dict) and isinstance(t.get("at"), list)]

    # where the sites are
    def priority(self, kx, ky):
        return _hash(self.seed, "site", kx, ky)

    def site_at(self, kx, ky):
        """The chance site of a chunk, if it has one: (site, x0, y0)."""
        key = (kx, ky)
        if key in self.picked:
            return self.picked[key]
        got = None
        if self.chance_sites:
            pr = self.priority(kx, ky)
            rng = random.Random("%d/site/%d/%d" % (self.seed, kx, ky))
            s = _weighted(rng, [{"weight": s.weight, "site": s} for s in self.chance_sites])["site"]
            sx, sy = self.world.start
            cx, cy = kx * N + 8, ky * N + 8
            ok = pr < s.chance and math.hypot(cx - sx, cy - sy) >= s.away and s.w <= N - 2 and s.h <= N - 2
            if ok and (kx, ky) in self.fixed_by_chunk:
                ok = False
            if ok:                                           # the strongest in its neighbourhood, so they spread out
                sp = s.spacing
                for j in range(-sp, sp + 1):
                    for i in range(-sp, sp + 1):
                        if (i or j) and self.priority(kx + i, ky + j) < pr \
                                and self.priority(kx + i, ky + j) < s.chance:
                            ok = False
            if ok:
                x0 = kx * N + 1 + rng.randrange(max(1, N - 1 - s.w))
                y0 = ky * N + 1 + rng.randrange(max(1, N - 1 - s.h))
                land, top = self.land, self.land.top
                for px, py in ((x0, y0), (x0 + s.w - 1, y0), (x0, y0 + s.h - 1), (x0 + s.w - 1, y0 + s.h - 1),
                               (x0 + s.w // 2, y0 + s.h // 2)):
                    h = land.raw(px, py) * top
                    if h < land.sea_h + 0.1 or abs(h - self.base) > 1.4:
                        ok = False                           # not in the water, not on a mountain
                        break
                if ok:
                    got = (s, x0, y0)
        if len(self.picked) > 20000:                         # a long way travelled: work them out again
            self.picked.clear()
        self.picked[key] = got
        return got

    def pads_in(self, kx, ky):
        """The flattened ground of the chance site in a chunk (fixed sites' are the land's own)."""
        site = self.site_at(kx, ky)
        if not site:
            return []
        s, x0, y0 = site
        return [(x0 - 1, y0 - 1, x0 + s.w, y0 + s.h, self.base, 4.0)]

    def sites_over(self, kx, ky):
        out = list(self.fixed_by_chunk.get((kx, ky), []))
        site = self.site_at(kx, ky)
        if site:
            out.append(site)
        return out

    # the cells
    def put_marks(self, kx, ky):
        """The landmarks of a chunk's chance site, put up (once): they may stand a little outside it."""
        if (kx, ky) in self.marks_of:
            return
        site = self.site_at(kx, ky)
        marks = []
        if site:
            s, x0, y0 = site
            marks = [dict(m, at=[x0 + int((m.get("at") or [0, 0])[0]), y0 + int((m.get("at") or [0, 0])[1])])
                     for m in s.landmarks]
            self.land.marks.extend(marks)
            for m in marks:
                if m.get("solid"):
                    self.land.blocked.add(tuple(m["at"]))
        self.marks_of[(kx, ky)] = marks

    def prune(self, here, r):
        """Take down the landmarks of chance sites further than ``r`` chunks off."""
        far = [k for k in self.marks_of if max(abs(k[0] - here[0]), abs(k[1] - here[1])) > r]
        if not far:
            return
        drop = []
        for k in far:
            drop += self.marks_of.pop(k)
        if drop:
            ids = set(map(id, drop))
            self.land.marks = [m for m in self.land.marks if id(m) not in ids]
            for m in drop:
                if m.get("solid"):
                    self.land.blocked.discard(tuple(m["at"]))

    def cells(self, kx, ky):
        from .level import Cell
        lv, land = self.lv, self.land
        sites = self.sites_over(kx, ky)
        for j in (-1, 0, 1):
            for i in (-1, 0, 1):
                self.put_marks(kx + i, ky + j)
        out = []
        for y in range(ky * N, ky * N + N):
            for x in range(kx * N, kx * N + N):
                ch, legend = " ", None
                for s, x0, y0 in sites:
                    c = s.char(x - x0, y - y0)
                    if c != " ":
                        ch, legend = c, s.legend
                        break
                if legend is None:
                    out.append(Cell(x, y, land.char(x, y), land.cell_spec(x, y)))
                    continue
                spec = _cell_spec(lv, legend.get(ch))
                c = Cell(x, y, ch, {k: v for k, v in spec.items() if k not in ("monster", "item")})
                out.append(c)
                land.add_stamp(x, y, lv.stamp_floor(c))
        return out

    def forget(self, kx, ky):
        for c in [(x, y) for (x, y) in list(self.land.stamp) if x >> 4 == kx and y >> 4 == ky]:
            self.land.drop_stamp(*c)

    # what is put about
    def spawns(self, kx, ky):
        lv, land = self.lv, self.land
        out = []
        sx, sy = self.world.start
        for s, x0, y0 in self.sites_over(kx, ky):
            for my, row in enumerate(s.rows):
                for mx, ch in enumerate(row):
                    x, y = x0 + mx, y0 + my
                    if x >> 4 != kx or y >> 4 != ky:
                        continue
                    spec = _cell_spec(lv, s.legend.get(ch))
                    for what in ("monster", "item"):
                        if spec.get(what):
                            out.append((what, spec[what], x, y, spec))
        for t in self.things:
            x, y = sx + int(t["at"][0]), sy + int(t["at"][1])
            if x >> 4 == kx and y >> 4 == ky:
                for what in ("monster", "item"):
                    if t.get(what):
                        out.append((what, t[what], x, y, t))
        rng = random.Random("%d/spawn/%d/%d" % (self.seed, kx, ky))
        taken = {(x, y) for _w, _n, x, y, _e in out}
        cx, cy = kx * N + 8, ky * N + 8
        dist = math.hypot(cx - sx, cy - sy)
        for rule in self.spawn_rules:
            what = "monster" if rule.get("monster") else "item" if rule.get("item") else None
            if what is None or dist < float(rule.get("away", 0)):
                continue
            per = float(rule.get("per_chunk", 0.3)) * min(1.0 + dist * float(rule.get("more", 0.0)),
                                                          float(rule.get("most", 3.0)))
            n = int(per) + (1 if rng.random() < per - int(per) else 0)
            on = rule.get("on")
            for _ in range(n):
                for _try in range(10):
                    x, y = kx * N + rng.randrange(N), ky * N + rng.randrange(N)
                    if (x, y) in taken or (x, y) in land.stamp or math.hypot(x - sx, y - sy) < float(rule.get("away", 0)):
                        continue
                    k = land.at_cell(x, y)[2]
                    biome = ("deep water" if k == -2 else "water") if k < 0 else land.biomes[k].name
                    if on and biome not in on:
                        continue
                    c = self.world.cell(x, y)
                    floats = what == "monster" and bool(((lv.data.monsters or {}).get(rule["monster"]) or {}).get("float"))
                    if c.solid or ((c.deep or c.steep) and not floats):
                        continue
                    taken.add((x, y))
                    out.append((what, rule[what], x, y, rule))
                    break
        return out

    def meets(self):
        kinds, iids = set(), set()
        lv = self.lv
        mons = lv.data.monsters or {}
        for r in self.spawn_rules + self.things:
            if r.get("monster"):
                kinds.add(r["monster"])
            if r.get("item"):
                iids.add(r["item"])
        for s in self.sites:
            for ch in set("".join(s.rows)):
                spec = _cell_spec(lv, s.legend.get(ch))
                if spec.get("monster"):
                    kinds.add(spec["monster"])
                if spec.get("item"):
                    iids.add(spec["item"])
        return {k for k in kinds if k in mons}, iids

    def known(self, ch):
        out = []
        for s, x0, y0 in self.fixed:
            for my, row in enumerate(s.rows):
                for mx, c in enumerate(row):
                    if c == ch:
                        out.append((x0 + mx, y0 + my))
        return out

    def uses(self):
        pics, mdls = set(), set()
        for s in self.sites:
            for m in s.landmarks:
                pics.add(m.get("sprite"))
                mdls.add(m.get("model"))
        return pics - {None}, mdls - {None}


# --------------------------------------------------------------------------- #
# a dungeon without end
# --------------------------------------------------------------------------- #
class DungeonMaker:
    """A room to a chunk (or a crossing of corridors), joined to its neighbours through gaps in the chunks'
    edges; deeper the further from the start; the exit in a room some chunks off."""

    def __init__(self, world, lv, spec):
        self.world, self.lv, self.spec = world, lv, spec
        self.seed = lv.world_seed
        self.legend = _legend(lv, spec.get("legend"))
        self.room_chance = float(spec.get("rooms", 0.8))
        self.size = _span(spec.get("room_size"), (4, 11))
        self.links = float(spec.get("links", 0.7))
        self.doors = float(spec.get("doors", 0.35))
        self.pools = float(spec.get("pools", 0.0))
        self.every = max(1, int(spec.get("depth_every", 2)))
        self.monsters = [t for t in spec.get("monsters") or [] if isinstance(t, dict) and t.get("monster")]
        self.items = [t for t in spec.get("items") or [] if isinstance(t, dict) and t.get("item")]
        self.per_room = _span(spec.get("per_room"), (0, 2))
        self.items_per_room = _span(spec.get("items_per_room"), (0, 1))
        self.more = float(spec.get("more", 0.5))
        self.most = int(spec.get("most", 6))                 # at most this many more a room, however deep
        walls = spec.get("walls")
        self.walls = walls if isinstance(walls, list) and all(isinstance(w, str) and len(w) == 1 for w in walls) else None
        self.k0 = (ORIGIN >> 4, ORIGIN >> 4)
        ex = spec.get("exit") if isinstance(spec.get("exit"), dict) else {}
        away = max(1, int(ex.get("away", 5)))
        turn = _hash(self.seed, "exit") * 2 * math.pi
        self.exit_chunk = (self.k0[0] + int(round(away * math.cos(turn))), self.k0[1] + int(round(away * math.sin(turn))))
        world.pinned.add(self.exit_chunk)
        self.plans = {}
        _rows, (x0, y0, w, h) = self.plan(*self.k0)
        world.start = (self.k0[0] * N + x0 + w // 2, self.k0[1] * N + y0 + h // 2)

    def depth(self, kx, ky):
        return max(abs(kx - self.k0[0]), abs(ky - self.k0[1])) // self.every

    def edge_open(self, kind, kx, ky):
        """The edge on the west (``"v"``) or north (``"h"``) side of chunk (kx, ky): open, and where."""
        near = {(kx, ky), (kx - 1, ky) if kind == "v" else (kx, ky - 1)}
        if self.k0 in near or self.exit_chunk in near:
            return True, 2 + int(_hash(self.seed, kind, kx, ky, "at") * 12)
        return _hash(self.seed, kind, kx, ky) < self.links, 2 + int(_hash(self.seed, kind, kx, ky, "at") * 12)

    def plan(self, kx, ky):
        """The chunk as rows of characters, and its room (x0, y0, w, h) or None."""
        key = (kx, ky)
        if key in self.plans:
            return self.plans[key]
        rng = random.Random("%d/room/%d/%d" % (self.seed, kx, ky))
        g = [["#"] * N for _ in range(N)]
        room = None
        if key in (self.k0, self.exit_chunk) or rng.random() < self.room_chance:
            lo, hi = self.size
            w, h = rng.randint(lo, min(hi, N - 3)), rng.randint(lo, min(hi, N - 3))
            x0, y0 = 1 + rng.randrange(N - 2 - w + 1), 2 + rng.randrange(max(1, N - 3 - h + 1))
            room = (x0, y0, w, h)
            for y in range(y0, y0 + h):
                for x in range(x0, x0 + w):
                    g[y][x] = "."
            if self.pools and key != self.k0 and rng.random() < self.pools and w >= 5 and h >= 5:
                px, py = x0 + 1 + rng.randrange(w - 3), y0 + 1 + rng.randrange(h - 3)
                for y in range(py, py + 2):
                    for x in range(px, px + 2):
                        g[y][x] = "~"
        ax, ay = (room[0] + room[2] // 2, room[1] + room[3] // 2) if room else (8, 8)
        gates = []
        for kind, (ex, ey), (dx, dy) in (("v", (kx, ky), (-1, 0)), ("v", (kx + 1, ky), (1, 0)),
                                         ("h", (kx, ky), (0, -1)), ("h", (kx, ky + 1), (0, 1))):
            is_open, at = self.edge_open(kind, ex, ey)
            if is_open:
                gates.append((dx, dy, at))
        if not gates:                                        # never shut in: the start's way out is always there
            gates.append((1, 0, 8))
        doorways = []
        for dx, dy, at in gates:
            if dx:                                           # through the west or east edge, on row ``at``
                bx = 0 if dx < 0 else N - 1
                path = [(ax, y) for y in range(min(ay, at), max(ay, at) + 1)] + \
                       [(x, at) for x in range(min(ax, bx), max(ax, bx) + 1)]
            else:
                by = 0 if dy < 0 else N - 1
                path = [(x, ay) for x in range(min(ax, at), max(ax, at) + 1)] + \
                       [(at, y) for y in range(min(ay, by), max(ay, by) + 1)]
            for x, y in path:
                if g[y][x] == "#":
                    g[y][x] = ","                            # corridor
            if room:
                x0, y0, w, h = room
                for x, y in path:                            # the first cell outside the room: perhaps a door
                    inside = x0 <= x < x0 + w and y0 <= y < y0 + h
                    near_room = x0 - 1 <= x <= x0 + w and y0 - 1 <= y <= y0 + h
                    if not inside and near_room:
                        doorways.append((x, y))
        for x, y in doorways:
            walls_ns = (y == 0 or g[y - 1][x] == "#") and (y == N - 1 or g[y + 1][x] == "#")
            walls_ew = (x == 0 or g[y][x - 1] == "#") and (x == N - 1 or g[y][x + 1] == "#")
            if (walls_ns or walls_ew) and rng.random() < self.doors:
                g[y][x] = "+"
        for y in range(N):
            for x in range(N):
                if g[y][x] == ",":
                    g[y][x] = "."
        if room and self.walls:                              # the room's own walls
            from .levelgen import dress
            dress(g, [room], self.walls, rng)
        if key == self.exit_chunk and room:                  # the exit: in the room's wall, where no way goes
            x0, y0, w, h = room
            spots = [(x, y0 - 1) for x in range(x0, x0 + w)] + [(x, y0 + h) for x in range(x0, x0 + w)] + \
                    [(x0 - 1, y) for y in range(y0, y0 + h)] + [(x0 + w, y) for y in range(y0, y0 + h)]
            for x, y in spots:
                if 0 < x < N - 1 and 0 < y < N - 1 and g[y][x] not in ".+~":
                    g[y][x] = "E"
                    break
        rows = ["".join(r) for r in g]
        self.plans[key] = (rows, room)
        if len(self.plans) > 2000:
            self.plans.clear()
        return rows, room

    def cells(self, kx, ky):
        from .level import Cell
        rows, _room = self.plan(kx, ky)
        out = []
        for y in range(N):
            for x in range(N):
                ch = rows[y][x]
                spec = _cell_spec(self.lv, self.legend.get(ch))
                out.append(Cell(kx * N + x, ky * N + y, ch, {k: v for k, v in spec.items() if k not in ("monster", "item")}))
        return out

    def forget(self, kx, ky):
        pass

    def prune(self, here, r):
        pass

    def spawns(self, kx, ky):
        rows, room = self.plan(kx, ky)
        if room is None or (kx, ky) == self.k0:
            return []
        rng = random.Random("%d/spawn/%d/%d" % (self.seed, kx, ky))
        d = self.depth(kx, ky)
        x0, y0, w, h = room
        free = [(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w) if rows[y][x] == "."]
        rng.shuffle(free)
        out = []
        mons = [t for t in self.monsters if int(t.get("from", 0)) <= d]
        lo, hi = self.per_room
        n = rng.randint(lo, hi) + min(int(d * self.more), self.most)
        for _ in range(n):
            t = _weighted(rng, mons) if mons else None
            if t is None or not free:
                break
            x, y = free.pop()
            out.append(("monster", t["monster"], kx * N + x, ky * N + y, t))
        lo, hi = self.items_per_room
        items = [t for t in self.items if int(t.get("from", 0)) <= d]
        for _ in range(rng.randint(lo, hi)):
            t = _weighted(rng, items) if items else None
            if t is None or not free:
                break
            x, y = free.pop()
            out.append(("item", t["item"], kx * N + x, ky * N + y, t))
        return out

    def meets(self):
        mons = self.lv.data.monsters or {}
        return ({t["monster"] for t in self.monsters if t["monster"] in mons}, {t["item"] for t in self.items})

    def known(self, ch):
        rows, _room = self.plan(*self.exit_chunk)
        kx, ky = self.exit_chunk
        return [(kx * N + x, ky * N + y) for y in range(N) for x in range(N) if rows[y][x] == ch]

    def uses(self):
        return set(), set()


def problems(spec, data, where="world"):
    """What is wrong with a level's ``"world"`` (for --check)."""
    out = []
    if not isinstance(spec, dict):
        return ["%s should be an object" % where]
    kind = spec.get("kind", "land")
    if kind not in ("land", "dungeon"):
        out.append("%s: kind should be \"land\" or \"dungeon\"" % where)
    for key in ("awake", "keep"):
        if key in spec and not (isinstance(spec[key], int) and 1 <= spec[key] <= 12):
            out.append("%s: %s should be a whole number, 1 to 12" % (where, key))
    mons, items = data.monsters or {}, data.items or {}
    for rule in list(spec.get("spawns") or []) + list(spec.get("monsters") or []) + list(spec.get("items") or []) \
            + list(spec.get("things") or []):
        if not isinstance(rule, dict):
            out.append("%s: spawns, monsters, items and things should be objects" % where)
            continue
        if rule.get("monster") and rule["monster"] not in mons:
            out.append("%s: unknown monster '%s'" % (where, rule["monster"]))
        if rule.get("item") and rule["item"] not in items:
            out.append("%s: unknown item '%s'" % (where, rule["item"]))
    for i, s in enumerate(spec.get("sites") or []):
        if not isinstance(s, dict) or not isinstance(s.get("map"), list):
            out.append("%s: site %d should have a map" % (where, i + 1))
            continue
        w, h = max((len(r) for r in s["map"]), default=0), len(s["map"])
        if not isinstance(s.get("at"), list) and (w > N - 2 or h > N - 2):
            out.append("%s: site '%s' is %dx%d: a site put by chance fits in %d x %d" % (where, s.get("name", i + 1), w, h,
                                                                                        N - 2, N - 2))
        if not isinstance(s.get("at"), list) and not s.get("chance"):
            out.append("%s: site '%s' needs an \"at\" or a \"chance\"" % (where, s.get("name", i + 1)))
    if kind == "land" and not isinstance(data.levels, dict):
        pass
    return out
