# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Brains: monsters that choose what to do.

A monster with a ``"brain"`` (monsters.json) weighs, each beat, what it could do - its **tactics** - and
does the one that scores best:

=========  ===================================================================================
close      go at the player
keep       stay at its distance (``"range"``), with a line of fire
cover      get out of his sight, then lean out to shoot (a gun), or wait for him (a claw)
flank      work round to his side or back, out of where he looks
retreat    hurt and frightened: back to its squad's leader, or away from him
hold       stay where it is (a guard by its post; a gunner with a good line)
search     it has lost him: go where he was last seen, then back to its post
=========  ===================================================================================

What weighs in: how hurt it is (and its ``"flee"`` point), how far he is, whether it can see him, whether
he is looking at it (``exposed``), how many friends are near, its squad's role for it (engine/ai/squad.py)
- and a little for keeping to what it was doing, so it does not dither. A brainy monster only knows
where the player is when it (or its squad) can see or hear him; it loses him after ``"memory"`` beats.

Beside its main attack, a brainy monster may carry ``"grenades"`` ({count, range, fuse, blast, every}): it
throws one where he is (or next to him) when he is in cover from it, or out of its sight but known - never
where one of its own would be caught - and ``"mines"`` ({count, item}): it lays one in a doorway, a
corridor or by the cover it holds or falls back through, when he does not see it.

``"brain"`` is a preset name (``brute``, ``skirmisher``, ``soldier``, ``heavy``, ``coward``, ``assault``,
``swarm``) or an object:
a ``"kind"`` (a preset) with any weight changed (``close``, ``keep``, ``cover``, ``flank``, ``retreat``,
``hold``), ``"flee"`` (0..1 of its health), ``"memory"`` (beats), ``"range"`` ([near, far] cells).

Nothing here draws on the level's chances except the attacks themselves, so a monster without a brain
plays exactly as before; a brainy one breaks ties by a sum of its number and the beat.
"""
from __future__ import annotations

TACTICS = ("close", "keep", "cover", "flank", "retreat", "hold", "search")
BRAINS = {
    "brute": {"close": 1.3, "keep": 0.0, "cover": 0.0, "flank": 0.5, "retreat": 0.3, "hold": 0.1,
              "flee": 0.15, "memory": 10},
    "skirmisher": {"close": 0.6, "keep": 1.0, "cover": 0.4, "flank": 1.1, "retreat": 0.7, "hold": 0.1,
                   "flee": 0.35, "memory": 8},
    "soldier": {"close": 0.6, "keep": 1.0, "cover": 1.1, "flank": 0.8, "retreat": 0.8, "hold": 0.3,
                "flee": 0.3, "memory": 12},
    "heavy": {"close": 0.4, "keep": 1.2, "cover": 0.6, "flank": 0.1, "retreat": 0.3, "hold": 0.9,
              "flee": 0.15, "memory": 14},
    "coward": {"close": 0.2, "keep": 0.8, "cover": 1.2, "flank": 0.3, "retreat": 1.6, "hold": 0.2,
               "flee": 0.6, "memory": 6},
    "assault": {"close": 1.1, "keep": 0.5, "cover": 0.6, "flank": 1.0, "retreat": 0.3, "hold": 0.1,
                "flee": 0.2, "memory": 12},
    "swarm": {"close": 1.2, "keep": 0.0, "cover": 0.0, "flank": 0.9, "retreat": 0.2, "hold": 0.0,
              "flee": 0.0, "memory": 10},
}
WEIGHTS = ("close", "keep", "cover", "flank", "retreat", "hold")
MARK = {"cover": "D", "flank": "F", "retreat": "B", "hold": "H", "search": "?", "keep": "K"}
SAY = {"cover": "%s ducks into cover.", "retreat": "%s falls back.", "search": "%s goes looking for you."}


def _jitter(*parts):
    x = 2166136261
    for p in parts:
        for ch in str(p).encode():
            x = ((x ^ ch) * 16777619) & 0xFFFFFFFF
    return (x % 1000) / 1000.0


def params(lv, m):
    """The monster's brain as numbers, or None (no brain: it hunts as monsters always have)."""
    cache = lv.__dict__.setdefault("_brains", {})
    if m.kind in cache:
        return cache[m.kind]
    raw = m.spec.get("brain")
    out = None
    if isinstance(raw, str) and raw in BRAINS:
        out = dict(BRAINS[raw], kind=raw)
    elif isinstance(raw, dict):
        out = dict(BRAINS.get(raw.get("kind"), BRAINS["soldier"]), kind=raw.get("kind", "soldier"))
        out.update({k: v for k, v in raw.items() if k != "kind"})
    if out is not None:
        a = m.attack
        kind = a.get("kind", "melee")
        reach = int(a.get("range", 8))
        if "range" not in out:
            out["range"] = [1, 1] if kind == "melee" else list(a.get("keep", [2, reach]))
        out["ranged"] = kind in ("hitscan", "projectile", "flame")
    cache[m.kind] = out
    return out


def has(lv, m):
    return (not m.barrel and not m.vehicle and not m.spec.get("boss") and m.grudge is None
            and m.attack.get("kind", "melee") in ("melee", "hitscan", "projectile", "flame")
            and params(lv, m) is not None)


def sees(lv, m):
    """It can see the player now: in its sight and with nothing between."""
    p = lv.player
    sight = int(m.spec.get("sight", 8))
    if lv.land is not None:
        sight = max(sight, 12)
    return max(abs(m.x - p.x), abs(m.y - p.y)) <= sight and lv.line_of_sight(m.x, m.y, p.x, p.y)


def exposed(lv, x, y):
    """The player looks this way: the cell is in front of him, within his eyes' width."""
    p = lv.player
    fx, fy = ((0, -1), (1, 0), (0, 1), (-1, 0))[p.facing]
    vx, vy = x - p.x, y - p.y
    ahead = vx * fx + vy * fy
    across = abs(vx * fy - vy * fx)
    return ahead > 0 and across <= ahead


def field(lv, x, y, floats=False, limit=None):
    """Steps to (x, y), kept for this beat (monsters heading for the same place share it)."""
    cache = lv.__dict__.setdefault("_ai_fields", {})
    if cache.get("beat") != lv.beat:
        cache.clear()
        cache["beat"] = lv.beat
    lim = limit or (24 if lv.land is not None else 40)
    key = (x, y, floats, lim)
    got = cache.get(key)
    if got is None:
        got = cache[key] = lv.distances(x, y, limit=lim, floats=floats)
    return got


def cover_spot(lv, m, tx, ty, ranged):
    """The nearest cell (within 4 steps) out of sight from (tx, ty); for a gun, one next to a cell from which it
    can shoot (to lean out of). None when there is none."""
    from collections import deque
    seen = {(m.x, m.y): 0}
    q = deque([(m.x, m.y)])
    best = None
    while q:
        c = q.popleft()
        d = seen[c]
        hidden = not lv.line_of_sight(tx, ty, c[0], c[1])
        if hidden and c != (tx, ty):
            if not ranged or any(lv.line_of_sight(c[0] + dx, c[1] + dy, tx, ty) and lv.free(c[0] + dx, c[1] + dy, skip=m)
                                 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                key = (d, abs(c[0] - tx) + abs(c[1] - ty))
                if best is None or key < best[0]:
                    best = (key, c)
                    if d <= 1:
                        break
        if d >= 4:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + dx, c[1] + dy)
            if n not in seen and lv.free(n[0], n[1], skip=m):
                seen[n] = d + 1
                q.append(n)
    return best[1] if best else None


def flank_spot(lv, m, tx, ty, lo, hi, side):
    """A cell beside or behind the player (his ``side``: -1 left, 1 right), at the monster's range, that it can
    get to and shoot from; away from his eyes. None when there is none."""
    p = lv.player
    fx, fy = ((0, -1), (1, 0), (0, 1), (-1, 0))[p.facing]
    rx, ry = -fy, fx                                    # his right hand
    taken = {o.goal for o in lv.monsters if o is not m and o.goal}
    near = max(1, lo)
    far = max(near + 1, min(hi, 5))
    best = None
    for dy in range(-far, far + 1):
        for dx in range(-far, far + 1):
            dd = max(abs(dx), abs(dy))
            if dd < near or dd > far:
                continue
            x, y = tx + dx, ty + dy
            if (x, y) in taken or not lv.free(x, y, skip=m):
                continue
            ahead = dx * fx + dy * fy
            across = dx * rx + dy * ry
            if side and across * side <= 0:
                continue
            if ahead > 0 and abs(across) <= ahead:
                continue                                 # in front of him: not a flank
            if not lv.line_of_sight(x, y, tx, ty):
                continue
            score = (ahead, -abs(across) * 0.3 + dd * 0.2, abs(x - m.x) + abs(y - m.y))
            if best is None or score < best[0]:
                best = (score, (x, y))
    return best[1] if best else None


def think(lv, m, b, known, seen, d, los):
    """Its tactic for this beat."""
    role = m.role
    if role == "rout":
        return "retreat"
    if known is None:
        if m.seen_at is not None:
            return "search"
        return "hold"
    if role == "circle":
        return "flank"                                   # a pack keeps off, round him, until it is together
    if role == "swarm":
        return "close"
    lo, hi = b["range"]
    ranged = b["ranged"]
    hpf = max(0.0, m.hp / float(max(1, m.max_hp)))
    flee = float(b.get("flee", 0.3))
    fear = max(0.0, min(1.0, (flee - hpf) / flee)) if flee > 0 else 0.0
    friends = sum(1 for o in lv.monsters if o is not m and o.awake and not o.dead and not o.barrel
                  and max(abs(o.x - m.x), abs(o.y - m.y)) <= 5)
    nerve = min(1.0, friends / 2.0)
    open_ = seen and exposed(lv, m.x, m.y)
    w = {k: float(b.get(k, 0.0)) for k in WEIGHTS}
    s = {}
    s["close"] = w["close"] * ((1.0 if not ranged else (0.9 if d > hi or not los else 0.15)) * (1 - fear))
    s["keep"] = w["keep"] * ((0.85 if lo <= d <= hi and los else 0.45) if ranged else 0.0) * (1 - 0.5 * fear)
    s["cover"] = w["cover"] * (1.0 if open_ else 0.35) * (1.0 if (m.cool or fear) else 0.5) * (1 if seen else 0.3)
    s["flank"] = w["flank"] * (0.45 + 0.55 * nerve) * (1.0 if d >= 3 else 0.2) * (1.0 if open_ else 0.6) * (1 - fear)
    s["retreat"] = w["retreat"] * 2.0 * fear * (1 - 0.5 * nerve)
    s["hold"] = w["hold"] * (0.6 if (ranged and los and lo <= d <= hi) else 0.1)
    if role == "point":
        s["close"] += 0.3
        s["keep"] += 0.3
    elif role == "flank":
        s["flank"] += 0.9 * (1 - fear)
    elif role == "suppress":
        s["keep"] += 0.6
        s["hold"] += 0.5
    elif role == "guard":
        s["hold"] += 1.5
    elif role == "advance":                              # a sweep's half that moves up
        s["close"] += 0.5
        s["flank"] += 0.4
    elif role == "overwatch":                            # the half that covers it
        s["hold"] += 0.8
        s["keep"] += 0.4
    if m.tactic in s:
        s[m.tactic] += 0.15                              # keep to it: no dithering
    for k in s:
        s[k] += 0.05 * _jitter(m.id, lv.beat, k)
    order = sorted(s, key=lambda k: (-s[k], TACTICS.index(k)))
    return order[0] if s[order[0]] > 0 else "close"


def act(lv, m):
    """A beat of a brainy monster: what it knows, what it chooses, then its attack or its move."""
    p, rng = lv.player, lv.rng
    b = params(lv, m)
    a = m.attack
    kind = a.get("kind", "melee")
    seen = sees(lv, m)
    if seen:
        m.seen_at = (p.x, p.y, lv.beat)
    memory = int(b.get("memory", 12))
    known = None
    sq = m.squad
    if sq is not None and sq.knows(lv) is not None:
        known = sq.knows(lv)
    if m.seen_at is not None and lv.beat - m.seen_at[2] <= memory:
        if known is None or (sq is not None and sq.seen_at and m.seen_at[2] >= sq.seen_at[2]):
            known = (m.seen_at[0], m.seen_at[1])
    if seen:
        known = (p.x, p.y)
    if known is None and m.seen_at is not None and lv.beat - m.seen_at[2] > memory * 2:
        m.seen_at = None
    tx, ty = known if known is not None else (p.x, p.y)
    d = max(abs(m.x - p.x), abs(m.y - p.y))
    adjacent = abs(m.x - p.x) + abs(m.y - p.y) == 1
    los = lv.line_of_sight(m.x, m.y, p.x, p.y)
    reach = int(a.get("range", 8))
    if m.role == "hide":                                 # an ambush: still and quiet, whatever it sees
        m.tactic, m.intent = "hold", None
        if m.post and (m.x, m.y) != tuple(m.post) and not m.seen:
            toward(lv, m, m.post[0], m.post[1], bool(m.float) and lv.land is not None, limit=10)
        return
    tactic = think(lv, m, b, known, seen, max(abs(m.x - tx), abs(m.y - ty)), los)
    if tactic != m.tactic:
        m.goal = None
    m.tactic = tactic
    tell(lv, m, tactic)
    if m.grenades_left > 0 and known is not None and tactic != "retreat" and m.intent is None and not m.stun:
        spot = throw_spot(lv, m, known, seen, los)
        if spot is not None:
            lv.queue.append(lambda: lv.lob_at(m, spot[0], spot[1]))
            return
    every = int(a.get("move_every", 1) or 1)
    still = every > 1 and (lv.beat + m.id) % every != 0
    fl = bool(m.float) and lv.land is not None

    # the attack, as monsters of its kind attack (it only shoots what it sees)
    if kind == "hitscan" and a.get("spinup"):
        if los and d <= reach and seen:
            if m.spun:
                m.intent = "spin"
                lv.queue.append(lambda: lv.ranged(m, None, d))
                return
            m.spin += 1
            m.intent = "spin"
            if m.spin == 1 and m.seen:
                lv.say("%s's barrels start to spin." % m.tag, "aim")
                lv.sfx((m.spec.get("sounds") or {}).get("spinup") or "spinup")
                lv.interrupt = lv.interrupt or "%s spins up" % m.tag
            if m.spin >= int(a["spinup"]):
                m.spun = True
            return
        if m.spin or m.spun:
            if m.seen:
                lv.say("%s's barrels wind down." % m.tag, "dim")
            m.spin, m.spun, m.intent = 0, False, None
    elif kind == "flame":
        lined = (m.x == p.x or m.y == p.y) and d <= reach and los
        if m.intent == "windup":
            m.intent, m.cool = None, int(a.get("cool", 1))
            if lined:
                lv.queue.append(lambda: lv.flame(m, None))
            return
        if lined and seen and not m.cool and tactic not in ("retreat", "search") \
                and rng.random() < float(a.get("eager", 0.7)):
            m.intent = "windup"
            if m.seen:
                lv.say("%s levels its nozzle." % m.tag, "wind")
                lv.sfx((m.spec.get("sounds") or {}).get("windup"))
            return
    elif kind in ("hitscan", "projectile"):
        if m.intent in ("aim", "windup"):
            m.intent, m.cool = None, int(a.get("cool", 1))
            if los:
                lv.queue.append(lambda: (lv.ranged(m, None, d) if kind == "hitscan" else lv.throw(m, None)))
            return
        if adjacent and a.get("claw"):
            lv.queue.append(lambda: lv.bite(m, None, a.get("claw")))
            return
        eager = float(a.get("eager", 0.55)) * {"keep": 1.0, "hold": 1.1, "cover": 1.3, "flank": 0.5,
                                                 "retreat": 0.35, "close": 1.0, "search": 0.0}[tactic]
        if m.role in ("suppress", "overwatch"):
            eager += 0.15
        if flanking(m):
            eager *= 0.4                                 # on its way round: it fires when it gets there
        if los and seen and d <= reach and not m.cool and rng.random() < min(0.95, eager):
            m.intent = "aim" if kind == "hitscan" else "windup"
            if m.seen:
                lv.say(("%s takes aim." if kind == "hitscan" else "%s raises a burning hand.") % m.tag,
                       "aim" if kind == "hitscan" else "wind")
            if kind == "projectile":
                lv.sfx((m.spec.get("sounds") or {}).get("windup"))
            return
    elif kind == "melee":
        if adjacent:
            lv.queue.append(lambda: lv.bite(m, None, a.get("damage", [10, 18])))
            return
    if still:
        return
    if m.mines_left > 0 and known is not None and mine_here(lv, m, known, tactic):
        lv.lay_mine(m)
        m.lobbed = lv.beat
        toward(lv, m, known[0], known[1], fl, away=True)    # and off it
        return
    move(lv, m, b, tactic, tx, ty, known, los, d, fl, kind)
    if kind == "melee" and known is not None and max(abs(m.x - p.x), abs(m.y - p.y)) <= 3 \
            and tactic == "close" and m.intent != "charge":
        m.intent = "charge"
        if m.seen:
            lv.say("%s charges!" % m.tag, "charge")


def throw_spot(lv, m, known, seen, los):
    """Where to throw a grenade: at him, or a cell next to him, when he is in cover from this one or out of its
    sight (but known), within its ``range`` and two cells off at least, where none of its own would be caught,
    and the throw has a clear way. None: not now."""
    g = m.spec.get("grenades") or {}
    if m.lobbed is not None and lv.beat - m.lobbed < int(g.get("every", 6)):
        return None
    kx, ky = known
    if not 2 <= max(abs(m.x - kx), abs(m.y - ky)) <= int(g.get("range", 5)):
        return None
    p = lv.player
    if seen and los and not lv.covered(m.x, m.y, p.x, p.y):
        return None                                      # it has a clear shot: it shoots
    best = None
    for dy in (0, -1, 1):
        for dx in (0, -1, 1):
            x, y = kx + dx, ky + dy
            if lv.cell(x, y).solid or not lv.line_of_sight(m.x, m.y, x, y) or max(abs(x - m.x), abs(y - m.y)) < 2:
                continue
            if any(not o.dead and not o.gone and not o.barrel and max(abs(o.x - x), abs(o.y - y)) <= 1
                   for o in lv.monsters):
                continue                                 # one of its own would be caught
            key = (max(abs(dx), abs(dy)), abs(dx) + abs(dy))
            if best is None or key < best[0]:
                best = (key, (x, y))
    return best[1] if best else None


def narrow(lv, x, y):
    """A doorway or a corridor: where a mine is hard to go round."""
    c = lv.cell(x, y)
    if c.kind == "door":
        return True
    s = lambda dx, dy: lv.cell(x + dx, y + dy).solid      # noqa: E731
    return (s(1, 0) and s(-1, 0)) or (s(0, 1) and s(0, -1))


def mine_here(lv, m, known, tactic):
    """Whether it lays a mine where it stands: unseen, in a narrow place he would come through or by the cover
    it holds, holding or falling back, a few cells from him, with no other thing there, and not too soon
    after the last."""
    if m.seen or not (m.role in ("overwatch", "suppress", "guard") or tactic in ("retreat", "hold", "cover")):
        return False
    if m.lobbed is not None and lv.beat - m.lobbed < 4:
        return False
    if max(abs(m.x - known[0]), abs(m.y - known[1])) < 3:
        return False
    if not narrow(lv, m.x, m.y) and not any(lv.cell(m.x + dx, m.y + dy).solid for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
        return False                                     # a doorway, a corridor, or the cover it held
    return not any(not it.taken and (it.x, it.y) == (m.x, m.y) for it in lv.items)


def flanking(m):
    return m.tactic == "flank" and m.goal is not None and (m.x, m.y) != m.goal


def toward(lv, m, x, y, fl, limit=None, away=False):
    return lv.step_towards(m, field(lv, x, y, fl, limit), away=away)


def move(lv, m, b, tactic, tx, ty, known, los, d, fl, kind):
    p = lv.player
    lo, hi = b["range"]
    steps = int(m.attack.get("speed", 1)) if kind == "melee" else 1
    if tactic == "search":
        goal = (m.seen_at[0], m.seen_at[1]) if m.seen_at else m.post
        if goal is None or (m.x, m.y) == tuple(goal):
            m.seen_at = None                              # nobody here: back to its post
            return
        toward(lv, m, goal[0], goal[1], fl)
        return
    if tactic == "hold":
        if m.role == "guard" and m.post and (m.x, m.y) != m.post and known is None:
            toward(lv, m, m.post[0], m.post[1], fl)
        elif b["ranged"] and los and d < lo:
            toward(lv, m, tx, ty, fl, away=True)
        return
    if tactic == "retreat":
        sq = m.squad
        lead = sq.leader if sq is not None and sq.leader is not None and sq.leader is not m and not sq.leader.dead else None
        if lead is not None and max(abs(lead.x - m.x), abs(lead.y - m.y)) > 1 \
                and max(abs(lead.x - tx), abs(lead.y - ty)) >= max(abs(m.x - tx), abs(m.y - ty)):
            if toward(lv, m, lead.x, lead.y, fl, limit=16):
                return
        toward(lv, m, tx, ty, fl, away=True)
        return
    if tactic == "cover":
        if m.goal is None or not lv.free(m.goal[0], m.goal[1], skip=m) and (m.x, m.y) != m.goal:
            m.goal = cover_spot(lv, m, tx, ty, b["ranged"])
        if m.goal is None:
            tactic = "keep" if b["ranged"] else "close"
        elif (m.x, m.y) != m.goal:
            toward(lv, m, m.goal[0], m.goal[1], fl, limit=8)
            return
        else:                                            # in cover: a gun leans out when it can shoot again
            if b["ranged"] and not m.cool and known is not None:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    x, y = m.x + dx, m.y + dy
                    if lv.free(x, y, skip=m) and lv.line_of_sight(x, y, p.x, p.y):
                        lv.move_mob(m, x, y)
                        m.goal = None                    # out of cover now: it finds new cover after the shot
                        return
            return
    if tactic == "retreat" and m.role == "rout":
        toward(lv, m, tx, ty, fl, away=True)
        return
    if tactic == "flank":
        if m.goal is None or (m.x, m.y) == m.goal or (lv.beat + m.id) % 3 == 0:
            if m.role == "circle":
                lo, hi = 3, 5
            spot = flank_spot(lv, m, tx, ty, lo, hi, m.side)
            m.goal = spot
        if m.goal is not None and (m.x, m.y) != m.goal:
            for _ in range(steps):
                if not toward(lv, m, m.goal[0], m.goal[1], fl, limit=20):
                    break
            return
        tactic = "keep" if b["ranged"] else "close"
    if tactic == "keep" and b["ranged"]:
        if not los or d > hi:
            toward(lv, m, tx, ty, fl)
        elif d < lo:
            toward(lv, m, tx, ty, fl, away=True)
        elif _jitter(m.id, lv.beat, "side") < 0.3:       # a step to the side now and then
            here = (m.x, m.y)
            opts = [(m.x + dx, m.y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            opts = [c for c in opts if lv.free(c[0], c[1], skip=m) and lv.line_of_sight(c[0], c[1], p.x, p.y)]
            if opts:
                c = opts[int(_jitter(m.id, lv.beat, "pick") * len(opts))]
                if c != here:
                    lv.move_mob(m, c[0], c[1])
        return
    # close: at him
    if kind == "flame":
        best = None
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (0, 0)):
            x, y = m.x + dx, m.y + dy
            if (dx or dy) and not lv.free(x, y, skip=m):
                continue
            dd = max(abs(x - tx), abs(y - ty))
            line = (x == tx or y == ty) and 1 <= dd <= int(m.attack.get("range", 3))
            fld = field(lv, tx, ty, fl)
            score = (0 if line else 1, fld.get((x, y), 999) if not line else -dd, dx, dy)
            if best is None or score < best[0]:
                best = (score, x, y)
        if best and (best[1], best[2]) != (m.x, m.y):
            lv.move_mob(m, best[1], best[2])
        return
    for _ in range(steps):
        if abs(m.x - p.x) + abs(m.y - p.y) == 1:
            break
        if m.role == "swarm" and m.spot is not None and (m.x, m.y) != tuple(m.spot) and lv.free(m.spot[0], m.spot[1], skip=m):
            if toward(lv, m, m.spot[0], m.spot[1], fl, limit=20):     # to its own side of him
                continue
        if not toward(lv, m, tx, ty, fl):
            break


def tell(lv, m, tactic):
    """Say what it is doing when it changes its mind - if the player sees it do so."""
    if tactic == m.said:
        return
    m.said = tactic
    if not m.seen:
        return
    if tactic == "flank" and m.side:
        lv.say("%s slips round to your %s." % (m.tag, "right" if m.side > 0 else "left"), "alert")
    elif tactic in SAY:
        lv.say(SAY[tactic] % m.tag, "dim")


def problems(spec, where):
    """What is wrong with a monster's ``"brain"`` (for --check)."""
    if spec is None:
        return []
    if isinstance(spec, str):
        return [] if spec in BRAINS else ["%s: unknown brain '%s' (%s)" % (where, spec, ", ".join(sorted(BRAINS)))]
    if not isinstance(spec, dict):
        return ["%s: brain should be a preset's name or an object" % where]
    out = []
    if spec.get("kind", "soldier") not in BRAINS:
        out.append("%s: unknown brain '%s' (%s)" % (where, spec.get("kind"), ", ".join(sorted(BRAINS))))
    for k, v in spec.items():
        if k in WEIGHTS + ("flee", "memory") and not isinstance(v, (int, float)):
            out.append("%s: brain %s should be a number" % (where, k))
        elif k == "range" and not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) for x in v)
                                   and v[0] <= v[1]):
            out.append("%s: brain range should be [near, far]" % where)
        elif k not in WEIGHTS + ("flee", "memory", "range", "kind"):
            out.append("%s: the brain has no '%s'" % (where, k))
    return out


WAYS = {"close": "comes at you", "keep": "keeps its distance", "cover": "takes cover", "flank": "works round your side",
        "retreat": "falls back when hurt", "hold": "holds its ground"}


def describe(raw):
    """A line for a monster's manual page: how its brain fights (its three strongest ways), or None."""
    if isinstance(raw, str) and raw in BRAINS:
        name, w = raw, BRAINS[raw]
    elif isinstance(raw, dict):
        name = raw.get("kind", "soldier")
        w = dict(BRAINS.get(name, BRAINS["soldier"]), **{k: v for k, v in raw.items() if k in WEIGHTS})
    else:
        return None
    top = sorted((k for k in WEIGHTS if float(w.get(k, 0)) >= 0.5), key=lambda k: (-float(w[k]), WEIGHTS.index(k)))[:3]
    return "mind: %s - %s" % (name, ", ".join(WAYS[k] for k in top)) if top else "mind: %s" % name


def stat(m):
    """The letter ``ps`` shows for what a brainy monster is doing."""
    return MARK.get(m.tactic)
