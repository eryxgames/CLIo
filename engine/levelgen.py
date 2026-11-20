# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Maps made from a seed, for first-person levels: a dungeon's floor.

A level with a ``"generate"`` block has no map of its own: one is made each time it is built, from the
level's seed (``"seed": "run"`` - a new one each game - or the game's), its name and how deep it is (the
game variable named by ``"depth"``). Rooms are set about the floor and joined by corridors (all of them,
and a few more ways round), with doors at some room mouths; the player starts in one room and the exit
is in the room furthest from it - locked, if a key is asked for, with the key in a room one can reach
without it. A closet behind a fist panel holds a secret. Monsters and items are drawn from tables, more
of them the deeper one is.
"""
from __future__ import annotations

from .chunks import _span, _weighted

POOL = "abcdfghijklmnopqrstuvyz0123456789!\"'()*-/<>?[]_{|}`"


def _box_gap(a, b, gap):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax - gap < bx + bw and bx - gap < ax + aw and ay - gap < by + bh and by - gap < ay + ah


def generate(spec, rng, depth, data, legend=None):
    """A floor: (rows of the map, legend entries for what it put about)."""
    kind = spec.get("type", "dungeon")
    if kind != "dungeon":
        raise ValueError("unknown generator '%s'" % kind)
    size = spec.get("size") or [48, 36]
    W, H = max(16, int(size[0])), max(12, int(size[1]))
    g = [["#"] * W for _ in range(H)]
    lo, hi = _span(spec.get("rooms"), (6, 10))
    want = rng.randint(lo, hi)
    rlo, rhi = _span(spec.get("room_size"), (4, 9))
    rooms = []
    for _ in range(want * 40):
        if len(rooms) >= want:
            break
        w, h = rng.randint(rlo, rhi), rng.randint(rlo, max(rlo, rhi - 1))
        if w > W - 4 or h > H - 4:
            continue
        r = (rng.randint(2, W - w - 2), rng.randint(2, H - h - 2), w, h)
        if any(_box_gap(r, o, 2) for o in rooms):
            continue
        rooms.append(r)
    if len(rooms) < 2:
        rooms = [(2, 2, 4, 4), (W - 7, H - 7, 4, 4)]
    for x0, y0, w, h in rooms:
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                g[y][x] = "."
    mid = [(x0 + w // 2, y0 + h // 2) for x0, y0, w, h in rooms]

    # join them: the shortest ways that join them all, then a few more
    joined, links = {0}, []
    while len(joined) < len(rooms):
        best = None
        for a in joined:
            for b in range(len(rooms)):
                if b in joined:
                    continue
                d = abs(mid[a][0] - mid[b][0]) + abs(mid[a][1] - mid[b][1])
                if best is None or d < best[0]:
                    best = (d, a, b)
        joined.add(best[2])
        links.append((best[1], best[2]))
    loops = float(spec.get("loops", 0.15))
    for a in range(len(rooms)):
        for b in range(a + 1, len(rooms)):
            if (a, b) not in links and (b, a) not in links and rng.random() < loops / 2:
                links.append((a, b))
    for a, b in links:
        (ax, ay), (bx, by) = mid[a], mid[b]
        if rng.random() < 0.5:
            path = [(x, ay) for x in range(min(ax, bx), max(ax, bx) + 1)] + [(bx, y) for y in range(min(ay, by), max(ay, by) + 1)]
        else:
            path = [(ax, y) for y in range(min(ay, by), max(ay, by) + 1)] + [(x, by) for x in range(min(ax, bx), max(ax, bx) + 1)]
        for x, y in path:
            g[y][x] = "."

    def ring(r):
        x0, y0, w, h = r
        return [(x, y0 - 1) for x in range(x0, x0 + w)] + [(x, y0 + h) for x in range(x0, x0 + w)] + \
               [(x0 - 1, y) for y in range(y0, y0 + h)] + [(x0 + w, y) for y in range(y0, y0 + h)]

    def walled(x, y):
        ns = g[y - 1][x] == "#" and g[y + 1][x] == "#"
        ew = g[y][x - 1] == "#" and g[y][x + 1] == "#"
        return ns or ew

    doors = float(spec.get("doors", 0.4))
    for r in rooms:
        for x, y in ring(r):
            if g[y][x] == "." and walled(x, y) and rng.random() < doors:
                g[y][x] = "+"

    # start, and the exit as far as the corridors go from it
    start = 0
    dist = _flood(g, mid[start])
    far = max(range(len(rooms)), key=lambda i: (dist.get(mid[i], -1), i))
    sx, sy = mid[start]
    g[sy][sx] = "@"
    ex0, ey0, ew, eh = rooms[far]
    for x, y in ring(rooms[far]):
        if g[y][x] == "#" and 0 < x < W - 1 and 0 < y < H - 1:
            g[y][x] = "E"
            break
    extra = {}
    used = set("#.+@E~SRWX") | set(legend or {}) | set("".join(w for w in spec.get("walls") or [] if isinstance(w, str)))
    pool = [c for c in POOL if c not in used]

    def char_for(value):
        """The map's character for a monster or item (one character per kind)."""
        for c, v in extra.items():
            if v == value:
                return c
        c = pool.pop(0)
        extra[c] = value
        return c

    def floor_cells(r):
        x0, y0, w, h = r
        out = [(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w) if g[y][x] == "."]
        rng.shuffle(out)
        return out

    # a key: the exit's room locked, the key where one can go without it
    key = spec.get("key") if isinstance(spec.get("key"), dict) else None
    if key and key.get("door") and key.get("item"):
        for x, y in ring(rooms[far]):
            if g[y][x] in ".+":
                g[y][x] = str(key["door"])[:1]
        reach = _flood(g, (sx, sy), stop=str(key["door"])[:1])
        options = [i for i in range(len(rooms)) if i not in (start, far) and mid[i] in reach]
        if options:
            i = max(options, key=lambda i: (reach[mid[i]], i))
            spots = floor_cells(rooms[i])
            if spots:
                x, y = spots[0]
                g[y][x] = char_for(key["item"])

    # a secret: a closet behind a fist panel, off a room
    treasure = spec.get("secret")
    if treasure:
        item = treasure if isinstance(treasure, str) else "armor"
        order = [i for i in range(len(rooms)) if i != far]
        rng.shuffle(order)
        done = False
        for i in order:
            x0, y0, w, h = rooms[i]
            for (px, py), (dx, dy) in ([((x, y0 - 1), (0, -1)) for x in range(x0 + 1, x0 + w - 1)] +
                                       [((x, y0 + h), (0, 1)) for x in range(x0 + 1, x0 + w - 1)] +
                                       [((x0 - 1, y), (-1, 0)) for y in range(y0 + 1, y0 + h - 1)] +
                                       [((x0 + w, y), (1, 0)) for y in range(y0 + 1, y0 + h - 1)]):
                cx, cy = px + dx, py + dy
                area = [(cx + i2 * (1 if dx == 0 else 0) + j * dx, cy + i2 * (1 if dy == 0 else 0) + j * dy)
                        for i2 in (-1, 0, 1) for j in (0, 1)]
                ring2 = [(ax + ox, ay + oy) for ax, ay in area for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
                if g[py][px] != "#" or any(not (0 < ax < W - 1 and 0 < ay < H - 1) or g[ay][ax] != "#"
                                           for ax, ay in area + [p for p in ring2 if p not in area and p != (px, py)]):
                    continue
                for ax, ay in area:
                    g[ay][ax] = "."
                g[py][px] = "S"
                tx, ty = cx + dx, cy + dy
                g[ty][tx] = char_for(item)
                done = True
                break
            if done:
                break

    # pools
    pools = float(spec.get("pools", 0.0))
    for i, r in enumerate(rooms):
        x0, y0, w, h = r
        if i in (start, far) or w < 5 or h < 5 or rng.random() >= pools:
            continue
        px, py = x0 + 1 + rng.randrange(w - 3), y0 + 1 + rng.randrange(h - 3)
        for y in range(py, py + 2):
            for x in range(px, px + 2):
                if g[y][x] == ".":
                    g[y][x] = "~"

    # monsters and items, more the deeper
    mons = [t for t in spec.get("monsters") or [] if isinstance(t, dict) and t.get("monster")
            and int(t.get("from", 0)) <= depth and t["monster"] in (data.monsters or {})]
    items = [t for t in spec.get("items") or [] if isinstance(t, dict) and t.get("item")
             and int(t.get("from", 0)) <= depth and t["item"] in (data.items or {})]
    plo, phi = _span(spec.get("per_room"), (0, 2))
    ilo, ihi = _span(spec.get("items_per_room"), (0, 1))
    more = float(spec.get("more", 0.5))
    most = int(spec.get("most", 6))                      # at most this many more a room, however deep
    for i, r in enumerate(rooms):
        spots = floor_cells(r)
        if i != start:
            for _ in range(rng.randint(plo, phi) + min(int(depth * more), most)):
                t = _weighted(rng, mons) if mons else None
                if t is None or not spots:
                    break
                x, y = spots.pop()
                g[y][x] = char_for(t["monster"])
        for _ in range(rng.randint(ilo, ihi)):
            t = _weighted(rng, items) if items else None
            if t is None or not spots:
                break
            x, y = spots.pop()
            g[y][x] = char_for(t["item"])
    guard = spec.get("guard")
    if isinstance(guard, str) and guard in (data.monsters or {}):
        spots = floor_cells(rooms[far])
        if spots:
            x, y = spots[0]
            g[y][x] = char_for(guard)
    dress(g, rooms, spec.get("walls"), rng)
    return ["".join(r) for r in g], extra


def dress(g, rooms, walls, rng):
    """Each room's own walls: one of ``walls`` (map characters), so the rooms do not all look the same."""
    if not (isinstance(walls, list) and walls and all(isinstance(w, str) and len(w) == 1 for w in walls)):
        return
    H, W = len(g), len(g[0])
    for x0, y0, w, h in rooms:
        ch = rng.choice(walls)
        for y in range(max(0, y0 - 1), min(H, y0 + h + 1)):
            for x in range(max(0, x0 - 1), min(W, x0 + w + 1)):
                if g[y][x] == "#":
                    g[y][x] = ch


def _flood(g, start, stop=None):
    """Steps from ``start`` over floor, doors and things (not walls, nor the ``stop`` character)."""
    from collections import deque
    H, W = len(g), len(g[0])
    dist = {start: 0}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if not (0 <= n[0] < W and 0 <= n[1] < H) or n in dist:
                continue
            ch = g[n[1]][n[0]]
            if ch in "#ESP%=" or ch == stop:
                continue
            dist[n] = dist[(x, y)] + 1
            q.append(n)
    return dist


def problems(spec, data, where="generate"):
    """What is wrong with a level's ``"generate"`` (for --check)."""
    out = []
    if not isinstance(spec, dict):
        return ["%s should be an object" % where]
    if spec.get("type", "dungeon") != "dungeon":
        out.append("%s: type should be \"dungeon\"" % where)
    size = spec.get("size")
    if size is not None and not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and 16 <= v <= 200
                                                                                   for v in size)):
        out.append("%s: size should be [width, height], 16 to 200 each" % where)
    mons, items = data.monsters or {}, data.items or {}
    for t in spec.get("monsters") or []:
        if not isinstance(t, dict) or t.get("monster") not in mons:
            out.append("%s: unknown monster %s" % (where, t.get("monster") if isinstance(t, dict) else t))
    for t in spec.get("items") or []:
        if not isinstance(t, dict) or t.get("item") not in items:
            out.append("%s: unknown item %s" % (where, t.get("item") if isinstance(t, dict) else t))
    key = spec.get("key")
    if key is not None and not (isinstance(key, dict) and key.get("door") in ("R", "W", "X") and key.get("item") in items):
        out.append("%s: key should be {\"door\": \"R\"|\"W\"|\"X\", \"item\": a key item}" % where)
    if isinstance(spec.get("secret"), str) and spec["secret"] not in items:
        out.append("%s: the secret holds an unknown item '%s'" % (where, spec["secret"]))
    if spec.get("guard") and spec["guard"] not in mons:
        out.append("%s: unknown guard '%s'" % (where, spec["guard"]))
    if spec.get("seed") not in (None, "run") and not isinstance(spec.get("seed"), int):
        out.append("%s: seed should be \"run\" or a number" % where)
    return out
