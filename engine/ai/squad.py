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

The roles only weigh in the members' own choices (engine/ai/brain.py): a hurt flanker still falls back,
a gunner with no line of fire still moves.
"""
from __future__ import annotations

from .. import snapshot

TACTICS = ("pincer", "fire_team", "hold", "rush")


class Squad:
    DEFAULTS = {"called": False}

    def __init__(self, name, tactic="pincer", guard=6, memory=12):
        self.name = name
        self.tactic = tactic if tactic in TACTICS else "pincer"
        self.guard = int(guard)                      # a holding squad stirs when he comes this close
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
        sq = lv.squads[name] = Squad(name, spec.get("tactic", "pincer"), spec.get("guard", 6), spec.get("memory", 12))
    sq.members.append(m)
    m.squad = sq
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
    if tactic == "hold":
        tactic = "pincer"
    order = sorted(present, key=lambda m: m.id)
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
    """What is wrong with one squad's settings: {tactic, guard, memory} (and ``radius`` for ``auto``)."""
    if not isinstance(sq, dict):
        return ["%s: '%s' should be an object" % (where, name)]
    out = []
    if sq.get("tactic", "pincer") not in TACTICS:
        out.append("%s: '%s' has an unknown tactic '%s' (%s)" % (where, name, sq.get("tactic"), ", ".join(TACTICS)))
    for key in ("guard", "memory", "radius"):
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
