# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Squads: monsters that know what the others know, and each have a part in one plan.

A squad shares one memory: where the player was last seen, and when. When one member sees him, all of
them know; when one is woken, it calls the others. Its leader is the strongest member still standing.
Each beat the squad gives every member a **role** by its **tactic**:

- ``"pincer"`` (the default): the leader holds the front (``point``); the rest work round both sides of
  the player (``flank``, alternately left and right of where he faces).
- ``"fire_team"``: half of those with guns pin him down from where they are (``suppress``); the rest flank.
- ``"hold"``: every member stays by its post (``guard``) until the player comes within ``guard`` cells
  of the squad's middle, or shoots one of them; then a pincer.
- ``"rush"``: all at him (``point``).
- ``"assault"``: those that fight close (claws, shotguns) go in together (``point``) while the long guns
  pin him down (``suppress``); grenades flush him out of cover.
- ``"sweep"``: bounding overwatch. Two halves take turns, ``bound`` beats each: one moves up
  (``advance``) while the other holds and covers it (``overwatch``); they mark doorways with mines.
- ``"ambush"``: every member waits where it was put, quiet and still (``hide``), even when it sees him,
  until he comes within ``guard`` cells (3) of one of them, hurts one, or looks one in the face within
  four; then they all fire at once, and fight on as a pincer.
- ``"swarm"``: a pack. Its members keep off, out of his eyes (``circle``), until enough of them are near
  him (``gather``: 3, or all if fewer); then all go in at once, each to its own side of him (``swarm``).
  Each one at him with others of the pack bites harder. When fewer than half are left the rest scatter
  (``rout``).

The roles only weigh in the members' own choices (engine/ai/brain.py): a hurt flanker still falls back,
a gunner with no line of fire still moves.
"""
from __future__ import annotations

from .. import snapshot

TACTICS = ("pincer", "fire_team", "hold", "rush", "assault", "sweep", "ambush", "swarm")


class Squad:
    DEFAULTS = {"called": False, "size0": 0, "bound": 3, "gather": 3, "broken": False}

    def __init__(self, name, tactic="pincer", guard=None, memory=12, bound=3, gather=3):
        self.name = name
        self.tactic = tactic if tactic in TACTICS else "pincer"
        if guard is None:
            guard = 3 if self.tactic == "ambush" else 6
        self.guard = int(guard)                      # a holding squad stirs (an ambush springs) when he comes this close
        self.bound = max(1, int(bound))              # a sweep's halves take turns this many beats
        self.gather = max(1, int(gather))            # a swarm goes in when this many are near him
        self.size0 = 0                               # how many it had at most: a swarm scatters below half
        self.broken = False                          # a swarm that has scattered
        self.memory = int(memory)                    # beats it goes on hunting where he was last seen
        self.members = []                            # Monsters (awake or asleep, in the level or a chunk)
        self.leader = None
        self.seen_at = None                          # (x, y, beat): where the player was last seen by any of them
        self.anchor = None                           # (x, y): the middle of where they were put
        self.stirred = False                         # a holding squad that has started its fight
        self.called = False                          # one of them has called the others

    def knows(self, lv):
        """Where the squad thinks the player is, or None when it has lost him."""
        if self.seen_at is None or lv.beat - self.seen_at[2] > self.memory:
            return None
        return self.seen_at[0], self.seen_at[1]


snapshot.register(Squad)


def tactic_of(members, default="pincer"):
    """The tactic most of these monsters fight by in a squad (their ``"squad_tactic"``), else ``default``."""
    count = {}
    for m in sorted(members, key=lambda m: m.id):
        t = m.spec.get("squad_tactic")
        if t in TACTICS:
            count[t] = count.get(t, 0) + 1
    if not count:
        return default
    return max(count, key=lambda t: count[t])            # the first of the most (dicts keep their order)


def spec_of(lv, name):
    spec = (lv.spec.get("squads") or {}).get(name)
    return spec if isinstance(spec, dict) else {}


def join(lv, m, name, spec=None):
    """Put a monster in the squad called ``name`` (made when first asked for)."""
    if not name or m is None:
        return None
    sq = lv.squads.get(name)
    if sq is None:
        spec = spec if isinstance(spec, dict) else spec_of(lv, name)
        sq = lv.squads[name] = Squad(name, spec.get("tactic", "pincer"), spec.get("guard"), spec.get("memory", 12),
                                     spec.get("bound", 3), spec.get("gather", 3))
    sq.members.append(m)
    m.squad = sq
    sq.size0 = max(sq.size0, len(sq.members))
    if sq.tactic == "ambush" and not sq.stirred:
        m.awake = True                               # an ambush is awake from the start, and says nothing
    xs = [o.post[0] for o in sq.members]
    ys = [o.post[1] for o in sq.members]
    sq.anchor = (sum(xs) // len(xs), sum(ys) // len(ys))
    return sq


def beat(lv, heard=None):
    """Before the monsters act: each squad's memory, its calls and its members' roles."""
    if not lv.squads:
        return
    from .brain import sees
    p = lv.player
    here = {id(m) for m in lv.monsters}
    for name in list(lv.squads):
        sq = lv.squads[name]
        sq.members = [m for m in sq.members if not m.dead and not m.gone]
        if not sq.members:
            del lv.squads[name]
            continue
        present = [m for m in sq.members if id(m) in here]
        if not present:
            continue
        spotted = [m for m in present if m.awake and sees(lv, m)]
        if spotted or any(m.awake and heard and (m.x, m.y) in heard for m in present):
            sq.seen_at = (p.x, p.y, lv.beat)
        if sq.tactic == "ambush" and not sq.stirred:
            spring(lv, sq, present, spotted, heard)
            if not sq.stirred:
                for m in present:
                    m.role, m.side, m.intent = "hide", 0, None
                continue
        if any(m.awake for m in present):
            asleep = [m for m in present if not m.awake]
            if asleep:                                # one of them is up: it calls the rest
                caller = next((m for m in present if m.awake), None)
                if caller is not None and caller.seen and not sq.called:
                    lv.say("%s calls the others: %s." % (caller.tag, ", ".join(m.tag for m in asleep)), "alert")
                    lv.interrupt = lv.interrupt or "%s calls for help" % caller.tag
                sq.called = True
                for m in asleep:
                    lv.wake(m, quiet=True)
        if sq.leader is None or sq.leader not in present:
            sq.leader = max(present, key=lambda m: (m.max_hp, -m.id))
        assign(lv, sq, present)


def spring(lv, sq, present, spotted, heard):
    """An ambush goes off: he is close to one of them, has hurt one, has heard a shot near one, or looks one in
    the face close by. They all take aim at once."""
    p = lv.player
    close = any(max(abs(m.x - p.x), abs(m.y - p.y)) <= sq.guard for m in present)    # heard, if not seen
    found = any(m.seen and max(abs(m.x - p.x), abs(m.y - p.y)) <= 4 for m in present)
    hurt = any(m.hp < m.max_hp for m in present)
    if not (close or found or hurt or (heard and any((m.x, m.y) in heard for m in present))):
        return
    sq.stirred = sq.called = True
    sq.seen_at = (p.x, p.y, lv.beat)
    fire = [m for m in present if m.attack.get("kind") in ("hitscan", "projectile")
            and lv.line_of_sight(m.x, m.y, p.x, p.y) and max(abs(m.x - p.x), abs(m.y - p.y)) <= int(m.attack.get("range", 8))]
    for m in fire:
        m.intent, m.cool = ("aim" if m.attack.get("kind") == "hitscan" else "windup"), 0
    lv.say("Ambush! %s open%s up%s." % (", ".join(m.tag for m in sorted(present, key=lambda m: m.id)),
                                          "s" if len(present) == 1 else "",
                                          " from cover" if fire else ""), "alert")
    lv.interrupt = lv.interrupt or "an ambush"
    lv.sfx("ambush", "spinup")


def assign(lv, sq, present):
    known = sq.knows(lv)
    tactic = sq.tactic
    if tactic == "hold" and not sq.stirred:
        p = lv.player
        near = sq.anchor and max(abs(p.x - sq.anchor[0]), abs(p.y - sq.anchor[1])) <= sq.guard
        hurt = any(m.hp < m.max_hp for m in present)
        if known and (near or hurt):
            sq.stirred = True
        else:
            for m in present:
                m.role, m.side = "guard", 0
            return
    if tactic in ("hold", "ambush"):
        tactic = "pincer"
    order = sorted(present, key=lambda m: m.id)
    for m in order:
        m.spot = None
    if tactic == "swarm":
        return swarm(lv, sq, order, known)
    if tactic == "sweep":
        half = (lv.beat // sq.bound) % 2
        for i, m in enumerate(order):
            m.role, m.side = ("advance" if i % 2 == half else "overwatch"), (1 if i % 4 < 2 else -1)
        return
    if tactic == "assault":
        for m in order:
            close = (m.attack.get("kind") or "melee") in ("melee", "flame") \
                or int((m.attack.get("keep") or [1, m.attack.get("range", 8)])[1]) <= 4
            m.role, m.side = ("point" if close else "suppress"), 0
        return
    gunners = [m for m in order if m is not sq.leader and (m.attack.get("kind") or "melee") in ("hitscan", "projectile")]
    pin = set(map(id, gunners[:(len(gunners) + 1) // 2])) if tactic == "fire_team" else set()
    side = 1
    for m in order:
        if tactic == "rush" or m is sq.leader:
            m.role, m.side = "point", 0
        elif id(m) in pin:                           # half the guns (the odd one too) pin him down
            m.role, m.side = "suppress", 0
        else:
            m.role, m.side = "flank", side
            side = -side


def swarm(lv, sq, order, known):
    """A pack: keep off until enough are near, then all in, each to its own side; scatter when thinned."""
    p = lv.player
    if not sq.broken and len(order) * 2 < sq.size0:
        sq.broken = True                                 # it does not come back together
        if any(m.seen for m in order):
            lv.say("The pack scatters.", "good")
    if sq.broken:
        for m in order:
            m.role, m.side = "rout", 0
        return
    if not sq.stirred and known is not None:
        near = sum(1 for m in order if m.awake and max(abs(m.x - p.x), abs(m.y - p.y)) <= 6)
        if near >= min(sq.gather, len(order)):
            sq.stirred = True
            if any(m.seen for m in order):
                lv.say("The pack comes at you from all sides!", "alert")
                lv.interrupt = lv.interrupt or "the pack"
    if not sq.stirred:
        side = 1
        for m in order:
            m.role, m.side = "circle", side
            side = -side
        return
    free = [(p.x + dx, p.y + dy) for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)) if lv.passable(p.x + dx, p.y + dy)]
    left = list(order)
    for c in free:                                       # each side of him to the nearest one not yet given one
        if not left:
            break
        m = min(left, key=lambda m: (abs(m.x - c[0]) + abs(m.y - c[1]), m.id))
        left.remove(m)
        m.spot = c
    for m in order:
        m.role, m.side = "swarm", 0


def leave(m, lv=None):
    """Take a monster out of its squad (it is gone from the level, or is being made again); a squad with
    nobody left goes too."""
    sq = m.squad
    if sq is not None:
        sq.members = [o for o in sq.members if o is not m]
        if sq.leader is m:
            sq.leader = None
        m.squad = None
        if lv is not None and not sq.members and lv.squads.get(sq.name) is sq:
            del lv.squads[sq.name]


def free_name(lv, base):
    """``base`` if no squad has it yet, else ``base2``, ``base3`` and so on."""
    name, n = base, 1
    while name in lv.squads:
        n += 1
        name = "%s%d" % (base, n)
    return name


def spec_problems(sq, name, where="squads"):
    """What is wrong with one squad's settings: {tactic, guard, memory, bound, gather} (and ``radius`` for
    ``auto``)."""
    if not isinstance(sq, dict):
        return ["%s: '%s' should be an object" % (where, name)]
    out = []
    if sq.get("tactic", "pincer") not in TACTICS:
        out.append("%s: '%s' has an unknown tactic '%s' (%s)" % (where, name, sq.get("tactic"), ", ".join(TACTICS)))
    for key in ("guard", "memory", "radius", "bound", "gather"):
        if key in sq and not (isinstance(sq[key], int) and not isinstance(sq[key], bool) and sq[key] >= 0):
            out.append("%s: '%s' %s should be a whole number" % (where, name, key))
    return out


def problems(spec, where="squads"):
    """What is wrong with a level's ``"squads"`` (for --check)."""
    if not isinstance(spec, dict):
        return ["%s should be an object: name -> {tactic, guard, memory}" % where]
    out = []
    for name, sq in spec.items():
        out += spec_problems(sq, name, where)
    return out
