"""Procedural dungeons: mazes of rooms, stocked from tables in ``dungeon.json``.

A game opts in with a ``"generator"`` block in ``game.json``::

    "generator": {"type": "maze", "entry": "camp", "loops": 0.25}

and describes its floors in ``dungeon.json`` (size, room texts, monsters,
loot).  Every new game is carved from the world seed, so ``--seed 7`` always
gives the same dungeon.  Each floor is a perfect maze with a few extra loops;
the stair down sits in the room farthest from the entrance, guarded by the
floor's elite - on the last floor, by the boss.
"""
from __future__ import annotations

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
    if isinstance(table[0], (list, tuple)):
        total = sum(float(t[1]) for t in table)
        r = rng.uniform(0, total)
        for value, weight in table:
            r -= float(weight)
            if r <= 0:
                return value
        return table[-1][0]
    return rng.choice(table)


def generate(game):
    """Build all floors into ``game.world.scenes``."""
    w = game.world
    rng = w.rng
    cfg = game.cfg.get("generator", {})
    D = game.data.dungeon
    floors = D.get("floors", [])
    loops = float(cfg.get("loops", 0.2))
    entry = cfg.get("entry")
    prev_far = None
    first_start = None

    for n, fl in enumerate(floors, 1):
        last = n == len(floors)
        fw, fh = int(fl.get("w", 4)), int(fl.get("h", 3))
        edges, start, far, dist = carve(rng, fw, fh, loops)
        sid = lambda c: "f%d_%d_%d" % (n, c[0], c[1])             # noqa: E731
        cells = [(x, y) for y in range(fh) for x in range(fw)]
        degree = {c: sum(1 for e in edges if c in e) for c in cells}
        dead_ends = [c for c in cells if degree[c] == 1 and c not in (start, far)]
        rng.shuffle(dead_ends)
        others = [c for c in cells if c not in (start, far) and c not in dead_ends]
        rng.shuffle(others)

        kinds = {start: "start", far: "boss" if last else "stairs"}
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
            entry_text = deal(kind)
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

        # ---- stock the rooms
        depth_loot = fl.get("loot", [])
        for c in cells:
            scene = w.scenes[sid(c)]
            kind = kinds[c]
            if kind == "monster":
                mid = w.spawn(_pick(rng, fl.get("monsters", [])), scene["id"],
                              {"ambush": rng.random() < float(fl.get("ambush_chance", 0.8))})
                if mid and rng.random() < float(fl.get("loot_chance", 0.35)) and depth_loot:
                    scene["items"].append(_pick(rng, depth_loot))
            elif kind == "plain":
                if rng.random() < float(fl.get("loot_chance", 0.35)) and depth_loot:
                    scene["items"].append(_pick(rng, depth_loot))
            elif kind == "trap":
                dmg = rng.randint(*fl.get("trap_damage", [6, 10]))
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
                gold = rng.randint(*fl.get("chest_gold", [8, 16]))
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
                eid = w.spawn(fl["elite"], scene["id"], {"ambush": False})
                scene["_elite"] = eid
            elif kind == "boss" and fl.get("boss"):
                w.spawn(fl["boss"], scene["id"], {"ambush": True})
            if kind == "start":
                scene["on_first_enter"] = [{"set": "floor_%d" % n}, {"save": "save"}] + \
                    ([{"say": fl["arrival"], "style": "story"}] if fl.get("arrival") else [])

        if fl.get("wanderer"):
            spots = [c for c in cells if kinds[c] in ("plain", "trap") and dist.get(c, 0) >= 2]
            if spots:
                w.spawn(fl["wanderer"], sid(rng.choice(spots)),
                        {"ambush": True, "movable": True, "moves_after_commands": 3,
                         "roam": [sid(c) for c in cells if kinds[c] not in ("start", "merchant", "shrine", "boss")]})

        # ---- stairs between floors
        if prev_far is not None:
            up = w.scenes[sid(start)]
            down = w.scenes[prev_far]
            guard = down.pop("_elite", None)
            ex = {"door_name": "Stair Down", "dir": "d", "scene_id": up["id"]}
            if guard:
                ex["guard"] = guard
                ex["guard_text"] = "%s bars the stair. There is no way down but through it." % \
                    w.characters[guard].get("name", "Something")
            down["exits"].append(ex)
            up["exits"].append({"door_name": "Stair Up", "dir": "u", "scene_id": down["id"]})
        else:
            first_start = sid(start)
        prev_far = sid(far)

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
