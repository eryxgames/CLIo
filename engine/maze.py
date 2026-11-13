# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Procedural dungeons: mazes of rooms, stocked from tables in ``dungeon.json``.

A game opts in with a ``"generator"`` block in ``game.json``::

    "generator": {"type": "maze", "entry": "camp", "loops": 0.25}

and describes its floors in ``dungeon.json`` (size, room texts, monsters,
loot).  Every new game is carved from the world seed, so ``--seed 7`` always
gives the same dungeon.  Each floor is a perfect maze with a few extra loops;
the stair down sits in the room farthest from the entrance, guarded by the
floor's elite - on the last floor, by the boss.

Monster rooms may hold a pack instead of a single creature::

    "pack_chance": 0.3,
    "packs": [[["bone_rat", "bone_rat"], 3], [["bone_rat", "gloom_bat"], 2]]

A game mode with ``"endless": true`` keeps the dungeon going below the last
written floor: :func:`extend` builds one more floor each time the player
arrives on the deepest one, reusing the floor descriptions in turn and scaling
their monsters so that every floor is harder than the one above.  The
``"endless"`` block of ``dungeon.json`` tunes this (see docs/AUTHORING.md).
"""
from __future__ import annotations

import copy

from .automap import DIRS, OPPOSITE

_ORTHO = ("n", "e", "s", "w")


def carve(rng, w, h, loops=0.2):
    """A maze on a w x h grid. Returns ``(edges, start, farthest, distances)``."""
    cells = [(x, y) for y in range(h) for x in range(w)]
    start = rng.choice(cells)
    edges = set()
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack[-1]
        options = []
        for d in _ORTHO:
            dx, dy, _ = DIRS[d]
            n = (x + dx, y + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in seen:
                options.append(n)
        if not options:
            stack.pop()
            continue
        n = rng.choice(options)
        edges.add(frozenset(((x, y), n)))
        seen.add(n)
        stack.append(n)
    for (x, y) in cells:                              # a few loops so it is not a pure tree
        for d in ("e", "s"):
            dx, dy, _ = DIRS[d]
            n = (x + dx, y + dy)
            if n in seen and frozenset(((x, y), n)) not in edges and rng.random() < loops:
                edges.add(frozenset(((x, y), n)))
    dist = {start: 0}
    queue = [start]
    while queue:
        c = queue.pop(0)
        for e in edges:
            if c in e:
                (o,) = [p for p in e if p != c]
                if o not in dist:
                    dist[o] = dist[c] + 1
                    queue.append(o)
    far = max(cells, key=lambda c: (dist.get(c, 0), c))
    return edges, start, far, dist


def _pick(rng, table):
    """Weighted choice from ``[[value, weight], ...]`` or a plain list."""
    if not table:
        return None
    weighted = all(isinstance(t, (list, tuple)) and len(t) == 2 and isinstance(t[1], (int, float))
                   and not isinstance(t[1], bool) for t in table)
    if weighted:
        total = sum(float(t[1]) for t in table)
        r = rng.uniform(0, total)
        for value, weight in table:
            r -= float(weight)
            if r <= 0:
                return value
        return table[-1][0]
    return rng.choice(table)


def _ids(table):
    """The values of a weighted (or plain) table."""
    out = []
    for t in table or []:
        out.append(t[0] if isinstance(t, (list, tuple)) and len(t) == 2
                   and isinstance(t[1], (int, float)) and not isinstance(t[1], bool) else t)
    return out


def scene_id(n, cell):
    return "f%d_%d_%d" % (n, cell[0], cell[1])


# ---------------------------------------------------------------------- #
# endless floors: how strong is a floor, and how strong should it be
# ---------------------------------------------------------------------- #
def floor_power(game, fl):
    """A rough strength for a floor: the average of health x hitting power of its monsters."""
    chars = game.data.characters
    total = weight = 0.0
    for entry in fl.get("monsters") or []:
        mid, wgt = (entry[0], float(entry[1])) if isinstance(entry, (list, tuple)) else (entry, 1.0)
        st = chars.get(mid, {}).get("stats") or {}
        total += wgt * float(st.get("max_health", st.get("health", 20))) * (6 + float(st.get("attack", 5)))
        weight += wgt
    return (total / weight) if weight else 1.0


def floor_plan(game, n):
    """How to build floor ``n``: ``(description, monster factor, rank, hazard factor)``.

    Floors up to the number written in ``dungeon.json`` are used as they are.
    Deeper ones take the written floors in turn, with the ``endless.floor``
    overrides on top; their monsters are scaled so that each floor is
    ``growth`` stronger than the one before, whichever description it uses.
    ``rank`` counts the times the written floors have been gone through (it
    picks the name prefix), and the hazard factor scales traps and gold.
    """
    D = game.data.dungeon
    floors = D.get("floors", [])
    count = len(floors)
    if n <= count:
        return floors[n - 1], 1.0, 0, 1.0
    E = D.get("endless") or {}
    order = [int(i) for i in (E.get("cycle") or range(count)) if 0 <= int(i) < count] or list(range(count))
    turn = (n - count - 1) % len(order)
    fl = dict(floors[order[turn]])
    fl.update(E.get("floor") or {})
    names = E.get("names") or []
    if turn < len(names):
        fl["name"] = names[turn]
    growth = float(E.get("growth", 0.25))
    deeper = (1.0 + growth) ** (n - count)
    factor = max(1.0, (floor_power(game, floors[-1]) * deeper / max(1.0, floor_power(game, fl))) ** 0.5)
    return fl, factor, (n - 1) // count, deeper ** 0.5


def scaled(game, template_id, factor, rank=0):
    """Spawn overrides that make a monster ``factor`` times tougher."""
    if factor <= 1.0 and not rank:
        return {}
    base = game.data.characters.get(template_id) or {}
    st = base.get("stats") or {}
    hp = int(round(float(st.get("max_health", st.get("health", 20))) * factor))
    out = {"stats": {"health": hp, "max_health": hp,
                     "attack": int(round((6 + float(st.get("attack", 5))) * factor - 6)),
                     "defense": int(round(float(st.get("defense", 0)) * (1 + (factor - 1) * 0.5)))}}
    if base.get("xp"):
        out["xp"] = int(round(base["xp"] * factor * factor))
    gold = base.get("gold")
    if isinstance(gold, (list, tuple)):
        out["gold"] = [int(round(g * factor)) for g in gold]
    elif gold:
        out["gold"] = int(round(gold * factor))
    prefixes = (game.data.dungeon.get("endless") or {}).get("prefixes") or []
    if rank and prefixes and base.get("name") and not base.get("unique"):
        prefix, name = prefixes[min(rank, len(prefixes)) - 1], base["name"]
        out["name"] = ("The %s %s" % (prefix, name[4:])) if name.startswith("The ") else "%s %s" % (prefix, name)
    return out


# ---------------------------------------------------------------------- #
# one floor
# ---------------------------------------------------------------------- #
def build_floor(game, n, fl, last=False, factor=1.0, rank=0, endless=None, hazard=1.0):
    """Carve and stock floor ``n``. Returns ``(start_scene_id, far_scene_id)``."""
    w = game.world
    rng = w.rng
    cfg = game.cfg.get("generator", {})
    D = game.data.dungeon
    loops = float(cfg.get("loops", 0.2))
    fw, fh = int(fl.get("w", 4)), int(fl.get("h", 3))
    edges, start, far, dist = carve(rng, fw, fh, loops)
    sid = lambda c: scene_id(n, c)                              # noqa: E731
    cells = [(x, y) for y in range(fh) for x in range(fw)]
    degree = {c: sum(1 for e in edges if c in e) for c in cells}
    dead_ends = [c for c in cells if degree[c] == 1 and c not in (start, far)]
    rng.shuffle(dead_ends)
    others = [c for c in cells if c not in (start, far) and c not in dead_ends]
    rng.shuffle(others)

    boss_floor = bool(fl.get("boss")) and (last or endless is not None)
    kinds = {start: "start", far: "boss" if boss_floor else "stairs"}
    specials = []
    specials += ["treasure"] * int(fl.get("treasure", 1))
    specials += ["shrine"] * int(fl.get("shrine", 1))
    if fl.get("merchant"):
        specials.append("merchant")
    pool = dead_ends + others
    for kind in specials:
        if not pool:
            break
        if kind == "merchant":                               # keep the shop near the entrance
            pool.sort(key=lambda c: dist.get(c, 99))
            cell = pool.pop(0)
            rng.shuffle(pool)
            pool.sort(key=lambda c: 0 if degree[c] == 1 else 1)
        else:
            cell = pool.pop(0)
        kinds[cell] = kind
    for c in cells:
        if c in kinds:
            continue
        r = rng.random()
        if r < float(fl.get("monster_chance", 0.5)):
            kinds[c] = "monster"
        elif r < float(fl.get("monster_chance", 0.5)) + float(fl.get("trap_chance", 0.1)):
            kinds[c] = "trap"
        else:
            kinds[c] = "plain"
    # never leave a floor without a fight or two
    if not any(k == "monster" for k in kinds.values()):
        for c in cells:
            if kinds[c] == "plain":
                kinds[c] = "monster"
                break

    music = fl.get("music") or {"generate": {"mood": fl.get("mood", "dark"),
                                             "seed": "%s-f%d-%d" % (game.data.id, n, w.seed % 5)}}
    area = "Floor %d %s %s" % (n, "-", fl.get("name", "")) if fl.get("name") else "Floor %d" % n
    texts = fl.get("rooms", {})
    decks = {}                                       # deal room texts without repeats

    def deal(kind):
        table = texts.get(kind) or texts.get("plain") or [{"name": "Chamber", "text": "A bare stone chamber."}]
        key = kind if texts.get(kind) else "plain"
        if not decks.get(key):
            decks[key] = list(table)
            rng.shuffle(decks[key])
        return decks[key].pop()

    for c in cells:
        kind = kinds[c]
        text_kind = kind
        if kind == "stairs" and not texts.get("stairs") and texts.get("boss"):
            text_kind = "boss"                       # a boss floor used as an ordinary one
        entry_text = deal(text_kind)
        name = entry_text.get("name", "Chamber")
        scene = {
            "id": sid(c), "name": name, "area": area, "map": [c[0], c[1], -n],
            "description": entry_text.get("text", ""), "items": [], "passive_items": [],
            "characters": [], "exits": [], "music": music, "floor": n, "kind": kind,
            "random_events": list(fl.get("ambient", [])),
            "hint": fl.get("hint") or D.get("hint"),
        }
        if entry_text.get("art"):
            scene["art"] = entry_text["art"]
        icon = {"shrine": "+", "merchant": "$", "treasure": "*", "boss": "!"}.get(kind)
        if icon:
            scene["map_icon"] = icon
            scene["map_label"] = {"shrine": "shrine", "merchant": "merchant", "treasure": "treasure",
                                  "boss": "lair"}[kind]
        w.scenes[scene["id"]] = scene

    doors = fl.get("doors") or ["Passage"]
    for e in edges:
        a, b = tuple(e)
        for src, dst in ((a, b), (b, a)):
            delta = (dst[0] - src[0], dst[1] - src[1], 0)
            d = next(k for k, v in DIRS.items() if v == delta)
            door = doors[(src[0] + src[1] + dst[0] + dst[1]) % len(doors)]
            w.scenes[sid(src)]["exits"].append({"door_name": door, "dir": d, "scene_id": sid(dst)})

    def spawn(template, scene, extra):
        over = scaled(game, template, factor, rank)
        over.update(extra)
        return w.spawn(template, scene["id"], over)

    # ---- stock the rooms
    depth_loot = fl.get("loot", [])
    packs = fl.get("packs") or []
    pack_chance = float(fl.get("pack_chance", 0.0)) if packs else 0.0
    for c in cells:
        scene = w.scenes[sid(c)]
        kind = kinds[c]
        if kind == "monster":
            members = None
            if pack_chance and rng.random() < pack_chance:
                members = _pick(rng, packs)
            if not members:
                members = [_pick(rng, fl.get("monsters", []))]
            ambush = rng.random() < float(fl.get("ambush_chance", 0.8))
            made = [spawn(m, scene, {"ambush": ambush}) for m in members if m]
            # a lone monster may be sitting on something; a pack always is
            chance = float(fl.get("pack_loot", 1.0) if len(made) > 1 else fl.get("loot_chance", 0.35))
            if any(made) and rng.random() < chance and depth_loot:
                scene["items"].append(_pick(rng, depth_loot))
        elif kind == "plain":
            if rng.random() < float(fl.get("loot_chance", 0.35)) and depth_loot:
                scene["items"].append(_pick(rng, depth_loot))
        elif kind == "trap":
            lo, hi = fl.get("trap_damage", [6, 10])
            dmg = int(round(rng.randint(int(lo), int(hi)) * hazard))
            trap = _pick(rng, D.get("traps") or [{"text": "A flagstone sinks under your boot. Darts hiss from the wall!",
                                                 "avoid": "You spot a tripwire at ankle height and step over it."}])
            scene["on_first_enter"] = [{
                "if": {"any": [{"class": D.get("trap_wise", [])}, {"chance": 0.2}]},
                "then": [{"say": trap.get("avoid", "You notice the trap in time."), "style": "success"}],
                "else": [{"sfx": "trap"}, {"say": trap.get("text", "A trap!"), "style": "combat"},
                         {"damage": dmg}]}]
        elif kind == "treasure":
            contents = []
            picks = int(fl.get("chest_items", 2))
            table = fl.get("chest_loot") or depth_loot
            for _ in range(picks):
                it = _pick(rng, table)
                if it and it not in contents:
                    contents.append(it)
            lo, hi = fl.get("chest_gold", [8, 16])
            gold = int(round(rng.randint(int(lo), int(hi)) * hazard))
            locked = rng.random() < float(fl.get("locked_chance", 0.0))
            cid = w.clone_item("chest", {"contents": contents,
                                         "current_state": "locked" if locked else "closed"})
            if cid:
                w.items[cid]["states"]["closed"]["do"] = [{"gold": gold}]
                scene["passive_items"].append(cid)
        elif kind == "shrine":
            sh = w.clone_item("shrine")
            if sh:
                scene["passive_items"].append(sh)
        elif kind == "merchant":
            w.spawn(fl.get("merchant") if isinstance(fl.get("merchant"), str) else "merchant", scene["id"])
        elif kind == "stairs" and fl.get("elite"):
            scene["_guard"] = spawn(fl["elite"], scene, {"ambush": False})
        elif kind == "boss" and fl.get("boss"):
            extra = {"ambush": True}
            if endless is not None and n > len(D.get("floors", [])):
                extra.update(copy.deepcopy(endless.get("boss") or {}))
            scene["_guard"] = spawn(fl["boss"], scene, extra)
        if kind == "start":
            arrival = fl.get("arrival")
            if endless is not None and n > len(D.get("floors", [])) and endless.get("arrival"):
                lines = endless["arrival"]
                arrival = lines[(n - 1) % len(lines)] if isinstance(lines, list) else lines
            scene["on_first_enter"] = [
                {"set": "floor_%d" % n}, {"var": ["depth", "=", n]},
                {"if": "endless", "then": [{"deepen": True}]},
                {"save": True},
            ] + ([{"say": arrival, "style": "story"}] if arrival else [])

    if fl.get("wanderer"):
        spots = [c for c in cells if kinds[c] in ("plain", "trap") and dist.get(c, 0) >= 2]
        if spots:
            spawn(fl["wanderer"], w.scenes[sid(rng.choice(spots))],
                  {"ambush": True, "movable": True, "moves_after_commands": 3,
                   "roam": [sid(c) for c in cells if kinds[c] not in ("start", "merchant", "shrine", "boss")]})
    return sid(start), sid(far)


def link(game, upper_far, lower_start):
    """Join two floors with a stair, watched by whoever guards the upper end."""
    w = game.world
    down = w.scenes[upper_far]
    up = w.scenes[lower_start]
    guard = down.pop("_guard", None)
    ex = {"door_name": "Stair Down", "dir": "d", "scene_id": up["id"]}
    if guard and guard in w.characters and not w.characters[guard].get("defeated"):
        ex["guard"] = guard
        ex["guard_text"] = "%s bars the stair. There is no way down but through it." % \
            w.characters[guard].get("name", "Something")
    down["exits"].append(ex)
    up["exits"].append({"door_name": "Stair Up", "dir": "u", "scene_id": down["id"]})


def generate(game):
    """Build the written floors into ``game.world.scenes``."""
    w = game.world
    cfg = game.cfg.get("generator", {})
    floors = game.data.dungeon.get("floors", [])
    entry = cfg.get("entry")
    prev_far = None
    first_start = None

    for n, fl in enumerate(floors, 1):
        start, far = build_floor(game, n, fl, last=n == len(floors))
        if prev_far is not None:
            link(game, prev_far, start)
        else:
            first_start = start
        prev_far = far
    w.vars["floors"] = len(floors)

    # ---- connect the hand-written entry scene to floor 1
    if entry in w.scenes and first_start:
        hooked = False
        for ex in w.scenes[entry]["exits"]:
            if str(ex.get("scene_id", "")).startswith("@"):
                ex["scene_id"] = first_start
                hooked = True
        if not hooked:
            w.scenes[entry]["exits"].append({"door_name": "Way Down", "dir": "d", "scene_id": first_start})
        w.scenes[first_start]["exits"].append({"door_name": "Stair Up", "dir": "u", "scene_id": entry})
    elif first_start and w.scene_id not in w.scenes:
        w.scene_id = first_start
    w.positions = None
    return w


def extend(game):
    """Endless mode: make sure there is a floor below the one the player stands on."""
    w = game.world
    built = int(w.vars.get("floors", 0) or 0)
    here = int(w.scene.get("floor", 0) or 0)
    if not built or here < built:
        return None
    n = built + 1
    fl, factor, rank, hazard = floor_plan(game, n)
    endless = game.data.dungeon.get("endless") or {}
    far_above = next((sid for sid, sc in w.scenes.items()
                      if sc.get("floor") == built and sc.get("kind") in ("stairs", "boss")), None)
    start, _far = build_floor(game, n, fl, factor=factor, rank=rank, endless=endless, hazard=hazard)
    if far_above:
        link(game, far_above, start)
    w.vars["floors"] = n
    w.positions = None
    return start
