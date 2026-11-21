# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""A level's state as plain data: saved, put back, and summed up.

A level is its seed plus the lines played on it; everything else is worked out. A **snapshot** is the
part that is not: the player, the monsters and items (where they are, what they want, how hurt they
are), shots in the air, fires, the cells that changed (a door opened, oil burnt off), the chances' state,
and - in a level without end - the chunks woken, asleep or changed. Putting a snapshot back on a
level freshly built from the same seed gives the same level, exactly: what it does next is what the
first one would have done.

The snapshot is made without a list of what to keep: every attribute of the level is kept unless it is
named in ``DERIVED`` (made again when a level is built) or begins with ``_`` (a cache; ``KEPT`` excepted). New state is saved by default;
something that cannot be saved stops the save with the place where it is, and the tests do this for every
level after a whole game.

Values: ``None``, numbers, text and lists as they are; tuples, sets and dicts tagged (``$t``, ``$s``,
``$o`` for text keys, ``$m`` for others); the level's own objects (monsters, items, the player, shots,
grenades, squads: the kinds ``register``-ed) once each by ``$c`` and later by ``$r``; a cell by where it is (``$cell``); what comes from the
game's data (a monster's spec, a sprite) by its path (``$p``); a random generator by its state (``$rng``).

``digest(state)`` sums a snapshot up: two machines playing the same lines must come to the same digest.
"""
from __future__ import annotations

import hashlib
import json
import math
import random

VERSION = 1
# made again by building the level, or not state at all (caches, the screen, the game round it)
DERIVED = frozenset((
    "data", "id", "spec", "cfg", "audio", "console", "host", "dev", "sprites", "models", "tiles", "see_through",
    "floor_tile", "ceiling_tile", "sky_look", "land", "grid", "plate_cells", "held_cells", "pads", "lifts", "belts",
    "land_walls", "world", "cell", "_field", "_pad_links", "_pristine", "replaying", "loaded", "warp", "opening",
    "timed_cells", "heights", "terraced", "atmosphere", "step_up", "render",
    "journal", "start_player", "seed", "depth", "w", "h", "map_w", "map_h", "name", "par", "weapons", "moved",
    "queue", "pending_save"))
KEPT = frozenset(("_tags", "_ids"))   # names starting with _ are caches, but for these (the monsters' numbering)
# what a level has that older snapshots do not: made fresh when a snapshot lacks it (not left as the
# new level made it, which would point at things the snapshot has replaced)
LEVEL_DEFAULTS = {"squads": dict}
# only to look at: kept in a snapshot, left out of its digest (they may differ where nobody looks)
LOOKS = frozenset(("vrng", "decals", "holes"))
KINDS = {}                   # name -> class: the kinds of object a snapshot can hold (``register``)


def register(cls):
    """Let a snapshot hold objects of this class (once each, by reference). A class may name ``DEFAULTS``:
    values for fields a snapshot from an older engine does not have."""
    KINDS[cls.__name__] = cls
    return cls


class SnapshotError(ValueError):
    pass


def roots(lv):
    """Where the unchanging things a level's state points into are, by name."""
    from . import level as level_mod
    d = lv.data
    return {"monsters": d.monsters or {}, "items": d.items or {}, "weapons": getattr(d, "weapons", None) or {},
            "config": d.config or {}, "levels": d.levels or {}, "WEAPONS": level_mod.WEAPONS,
            "lvweapons": lv.weapons, "sprites": lv.sprites, "models": getattr(lv, "models", {}) or {}}


def statics(lv):
    """id of each unchanging dict, list or picture -> its path from a root."""
    out = {}

    def walk(obj, path, depth):
        if id(obj) in out:
            return
        if isinstance(obj, dict):
            out[id(obj)] = path
            if depth < 8:
                for k, v in obj.items():
                    if isinstance(k, str) and isinstance(v, (dict, list)):
                        walk(v, path + [k], depth + 1)
        elif isinstance(obj, list):
            out[id(obj)] = path
            if depth < 8:
                for i, v in enumerate(obj):
                    if isinstance(v, (dict, list)):
                        walk(v, path + [i], depth + 1)
    for name, root in roots(lv).items():
        if name in ("sprites", "models"):
            for k, v in root.items():
                out.setdefault(id(v), [name, k])
            continue
        walk(root, [name], 0)
    return out


def resolve(lv, path):
    obj = roots(lv)[path[0]]
    for k in path[1:]:
        obj = obj[k]
    return obj


class Dumper:
    def __init__(self, lv):
        self.static = statics(lv)
        self.ids = {}

    def enc(self, v, where):
        if v is None or isinstance(v, (bool, int, str)):
            return v
        if isinstance(v, float):
            return v if math.isfinite(v) else {"$f": repr(v)}
        path = self.static.get(id(v))
        if path is not None:
            return {"$p": path}
        if isinstance(v, list):
            return [self.enc(x, "%s[%d]" % (where, i)) for i, x in enumerate(v)]
        if isinstance(v, tuple):
            return {"$t": [self.enc(x, "%s[%d]" % (where, i)) for i, x in enumerate(v)]}
        if isinstance(v, (set, frozenset)):
            if v and all(type(x) is tuple and len(x) == 2 and type(x[0]) is int and type(x[1]) is int for x in v):
                flat = []                                # places (seen cells, checkpoints): x, y, x, y, ...
                for x, y in sorted(v):
                    flat += (x, y)
                return {"$xy": flat}
            items = [self.enc(x, where + "{}") for x in v]
            items.sort(key=lambda x: json.dumps(x, sort_keys=True))
            return {"$s": items}
        if isinstance(v, dict):
            if all(isinstance(k, str) for k in v):
                return {"$o": {k: self.enc(x, "%s.%s" % (where, k)) for k, x in v.items()}}
            return {"$m": [[self.enc(k, where + "<key>"), self.enc(x, "%s[%r]" % (where, k))] for k, x in v.items()]}
        if isinstance(v, random.Random):
            return {"$rng": self.enc(v.getstate(), where)}
        name = type(v).__name__
        if name == "Cell":
            return {"$cell": [v.x, v.y]}
        if name in KINDS:
            n = self.ids.get(id(v))
            if n is not None:
                return {"$r": n}
            n = self.ids[id(v)] = len(self.ids)
            fields = {k: self.enc(x, "%s.%s" % (where, k)) for k, x in vars(v).items()}
            return {"$c": name, "$id": n, "f": fields}
        raise SnapshotError("cannot save %s (a %s)" % (where, name))


class Loader:
    def __init__(self, lv):
        from . import level as level_mod  # noqa: F401  (registers the level's kinds)
        self.lv = lv
        self.classes = KINDS
        self.objs = {}

    def dec(self, v):
        if isinstance(v, list):
            return [self.dec(x) for x in v]
        if not isinstance(v, dict):
            return v
        if "$t" in v:
            return tuple(self.dec(x) for x in v["$t"])
        if "$s" in v:
            return set(self.dec(x) for x in v["$s"])
        if "$xy" in v:
            f = v["$xy"]
            return {(f[i], f[i + 1]) for i in range(0, len(f), 2)}
        if "$o" in v:
            return {k: self.dec(x) for k, x in v["$o"].items()}
        if "$m" in v:
            return {self.dec(k): self.dec(x) for k, x in v["$m"]}
        if "$p" in v:
            try:
                return resolve(self.lv, v["$p"])
            except (KeyError, IndexError, TypeError):
                raise SnapshotError("the game's data has no %s any more" % "/".join(map(str, v["$p"])))
        if "$r" in v:
            return self.objs[v["$r"]]
        if "$c" in v:
            cls = self.classes.get(v["$c"])
            if cls is None:
                raise SnapshotError("unknown kind of thing '%s'" % v["$c"])
            obj = cls.__new__(cls)
            self.objs[v["$id"]] = obj                    # before its fields: they may point back at it
            for k, x in getattr(cls, "DEFAULTS", {}).items():
                setattr(obj, k, x)                       # fields an older snapshot does not have
            for k, x in v["f"].items():
                setattr(obj, k, self.dec(x))
            return obj
        if "$cell" in v:
            return self.lv.cell(*v["$cell"])
        if "$rng" in v:
            r = random.Random()
            st = self.dec(v["$rng"])
            r.setstate(tuple(tuple(x) if isinstance(x, list) else x for x in st))
            return r
        if "$f" in v:
            return float(v["$f"])
        raise SnapshotError("cannot read %s" % json.dumps(v)[:60])


def cell_states(lv):
    """Every cell's changeable state, in the grid's order (a level that is built whole)."""
    from .level import cell_state
    return [cell_state(c) for row in lv.grid for c in row]


def capture(lv):
    """The level's state now, as plain data."""
    d = Dumper(lv)
    attrs = {}
    for k, v in vars(lv).items():
        if k in DERIVED or (k.startswith("_") and k not in KEPT):
            continue
        attrs[k] = d.enc(v, k)
    out = {"v": VERSION, "id": lv.id, "beat": lv.beat}
    if lv.world is None:
        pristine = getattr(lv, "_pristine", None)
        now = cell_states(lv)
        if pristine is None or len(pristine) != len(now):
            raise SnapshotError("the level's cells are not as it was built")
        w = lv.w
        out["cells"] = [[i % w, i // w, list(s)] for i, (s, p) in enumerate(zip(now, pristine)) if s != p]
    else:
        out["world"] = world_state(lv)
    out["attrs"] = attrs
    out["world_objects"] = d.enc(lv.world.sleepers, "world.sleepers") if lv.world is not None else None
    return out


def world_state(lv):
    from .chunks import _state
    W = lv.world
    changes = {k: dict(v) for k, v in W.changes.items()}
    for key, cells in W.loaded.items():
        sig = W.sigs[key]
        diff = {i: _state(c) for i, c in enumerate(cells) if _state(c) != sig[i]}
        if diff:
            changes[key] = diff
    return {"changes": [[list(k), [[i, list(s)] for i, s in sorted(v.items())]] for k, v in sorted(changes.items())],
            "awake": sorted(list(k) for k in W.awake), "spawned": sorted(list(k) for k in W.spawned),
            "counted": [[list(k), n] for k, n in sorted(W.counted.items())],
            "secret_chunks": sorted(list(k) for k in W.secret_chunks),
            "here": list(W.here) if W.here else None}


def restore(lv, snap):
    """Put a snapshot back on a level built afresh from the same seed (and depth)."""
    if not isinstance(snap, dict) or snap.get("v") != VERSION:
        raise SnapshotError("this save was made by another version of the engine")
    if snap.get("id") != lv.id:
        raise SnapshotError("this snapshot is of level '%s'" % snap.get("id"))
    from .level import CELL_STATE
    W = lv.world
    if W is not None:                                    # the chunks as they were: changes, woken, spawned
        ws = snap.get("world") or {}
        for key in sorted(W.loaded):
            W.evict(key)
        W.changes = {tuple(k): {i: tuple(s) for i, s in v} for k, v in ws.get("changes", [])}
        W.awake = {tuple(k) for k in ws.get("awake", [])}
        W.spawned = {tuple(k) for k in ws.get("spawned", [])}
        W.counted = {tuple(k): n for k, n in ws.get("counted", [])}
        W.secret_chunks = {tuple(k) for k in ws.get("secret_chunks", [])}
        W.here = tuple(ws["here"]) if ws.get("here") else None
        W.sleepers = {}
        for key in sorted(W.pinned | W.awake):
            W.load(key)
    else:
        for x, y, state in snap.get("cells", []):
            c = lv.cell(x, y)
            for name, v in zip(CELL_STATE, state):
                setattr(c, name, tuple(v) if isinstance(v, list) else v)
    ld = Loader(lv)
    attrs = snap.get("attrs", {})
    for k, v in attrs.items():
        if k in DERIVED or (k.startswith("_") and k not in KEPT):
            continue
        setattr(lv, k, ld.dec(v))
    for k, make in LEVEL_DEFAULTS.items():
        if k not in attrs:
            setattr(lv, k, make())                       # a snapshot from before the level had it
    if W is not None and snap.get("world_objects"):
        W.sleepers = ld.dec(snap["world_objects"])
    for k in ("_field", "_ai_fields"):
        lv.__dict__.pop(k, None)                         # ways to the player, worked out again as needed
    return lv


def pack(snap):
    """A snapshot for a save file: as it is when small, squeezed (zlib, base64) when big."""
    import base64
    import zlib
    text = json.dumps(snap, separators=(",", ":"))
    if len(text) < 200000:
        return snap
    return {"z": base64.b64encode(zlib.compress(text.encode("utf-8"), 6)).decode("ascii")}


def unpack(blob):
    import base64
    import zlib
    if isinstance(blob, dict) and set(blob) == {"z"}:
        try:
            return json.loads(zlib.decompress(base64.b64decode(blob["z"])).decode("utf-8"))
        except (ValueError, zlib.error) as e:
            raise SnapshotError("the snapshot is damaged (%s)" % e)
    return blob


def digest(snap):
    """A short sum of a snapshot's state (what only looks different left out)."""
    body = dict(snap)
    attrs = {k: v for k, v in (snap.get("attrs") or {}).items() if k not in LOOKS}
    body["attrs"] = attrs
    text = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
