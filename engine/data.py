# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Loading game data.

A game is a folder of JSON files.  CLIo 2 reads the original CLIo layout
(``config.json`` pointing at scenes / items / characters / story texts) and
the extended layout (``game.json`` plus optional dialogues, quests, triggers,
music, sounds, sprites and an ``art/`` folder).  Everything is normalised into
one predictable shape so the rest of the engine never has to care which
flavour it was written in.
"""
from __future__ import annotations

import copy
import json
import os

from .automap import norm_dir


class GameDataError(Exception):
    pass


def read_json(path, default=None):
    if not path or not os.path.isfile(path):
        if default is not None:
            return default
        raise GameDataError("Missing game file: %s" % path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except ValueError as e:
        raise GameDataError("%s is not valid JSON: %s" % (path, e))


def find_games(root):
    """Game folders under ``root``: ``[(path, title, description)]``."""
    found = []
    candidates = []
    games_dir = os.path.join(root, "games")
    if os.path.isdir(games_dir):
        candidates += [os.path.join(games_dir, d) for d in sorted(os.listdir(games_dir))]
    candidates.append(os.path.join(root, "game_files"))
    for path in candidates:
        cfg = config_path(path)
        if cfg:
            try:
                data = read_json(cfg)
            except GameDataError:
                continue
            title = data.get("title") or os.path.basename(path).replace("_", " ").title()
            found.append((path, title, data.get("description", "")))
    found.sort(key=lambda g: read_json(config_path(g[0])).get("order", 50))
    return found


def config_path(game_dir):
    for name in ("game.json", "config.json"):
        p = os.path.join(game_dir, name)
        if os.path.isfile(p):
            return p
    return None


class GameData:
    """Static definition of a game, as loaded from disk."""

    def __init__(self, game_dir):
        self.dir = os.path.abspath(game_dir)
        cfg_file = config_path(self.dir)
        if not cfg_file:
            raise GameDataError("No game.json or config.json in %s" % game_dir)
        self.config = cfg = read_json(cfg_file)
        self.legacy = os.path.basename(cfg_file) == "config.json"      # original CLIo layout
        self.id = cfg.get("id") or os.path.basename(self.dir)
        self.title = cfg.get("title") or self.id.replace("_", " ").title()

        files = dict(cfg.get("files", {}))
        legacy_keys = {"scenes": "scenes_file", "items": "items_file",
                       "characters": "characters_file", "texts": "story_texts_file"}
        for key, old in legacy_keys.items():
            if old in cfg and key not in files:
                files[key] = cfg[old]
        defaults = {"scenes": "scenes.json", "items": "items.json", "characters": "characters.json",
                    "texts": "texts.json", "dialogues": "dialogues.json", "quests": "quests.json",
                    "triggers": "triggers.json", "music": "music.json", "sounds": "sounds.json",
                    "sprites": "sprites.json", "dungeon": "dungeon.json"}

        def load(key, required=False):
            name = files.get(key, defaults[key])
            for base in (self.dir, os.getcwd(), os.path.dirname(self.dir)):
                p = name if os.path.isabs(name) else os.path.join(base, name)
                if os.path.isfile(p):
                    return read_json(p)
            if required:
                raise GameDataError("%s: cannot find the %s file (%s)" % (self.title, key, name))
            return {}

        self.scenes = self._norm_scenes(load("scenes", required="generator" not in cfg))
        self.items = self._norm_items(load("items", required=True))
        self.characters = self._norm_characters(load("characters"))
        self.texts = load("texts") or {}
        self.dialogues = load("dialogues") or {}
        self.quests = load("quests") or {}
        triggers = load("triggers") or []
        self.triggers = triggers if isinstance(triggers, list) else list(triggers.values())
        self.songs = load("music") or {}
        self.sounds = load("sounds") or {}
        self.sprites = load("sprites") or {}
        self.dungeon = load("dungeon") or {}
        self.art_dir = os.path.join(self.dir, cfg.get("art_dir", "art"))

        self.theme = cfg.get("style") or cfg.get("style_config") or "default"
        self.initial_scene = cfg.get("initial_scene") or (next(iter(self.scenes)) if self.scenes else None)
        self.player_stats = dict(cfg.get("player_stats", {"health": 100, "attack": 5, "defense": 5}))
        self.max_hints = int(cfg.get("max_hints", 5))
        self._legacy_fixups()

    # ------------------------------------------------------------------ #
    def _norm_scenes(self, raw):
        scenes = {}
        if isinstance(raw, dict) and "scenes" in raw and isinstance(raw["scenes"], (list, dict)):
            raw = raw["scenes"]
        entries = raw.items() if isinstance(raw, dict) else ((s.get("id"), s) for s in raw or [])
        for sid, sc in entries:
            if not isinstance(sc, dict):
                continue
            sc = copy.deepcopy(sc)
            sc["id"] = sid = sc.get("id") or sid
            if not sid:
                continue
            sc.setdefault("name", sid)
            for key in ("items", "passive_items", "characters", "exits"):
                if not isinstance(sc.get(key), list):
                    sc[key] = []
            sc["exits"] = [self._norm_exit(e) for e in sc["exits"] if isinstance(e, dict)]
            scenes[sid] = sc
        return scenes

    @staticmethod
    def _norm_exit(ex):
        ex = dict(ex)
        if "to" in ex and "scene_id" not in ex:
            ex["scene_id"] = ex.pop("to")
        if "name" in ex and "door_name" not in ex:
            ex["door_name"] = ex.pop("name")
        d = norm_dir(ex.get("dir"))
        if d:
            ex["dir"] = d
        else:
            ex.pop("dir", None)
        ex.setdefault("door_name", "")
        if not ex.get("required_item"):
            ex.pop("required_item", None)
        return ex

    @staticmethod
    def _norm_items(raw):
        items = {}
        for iid, it in (raw or {}).items():
            if not isinstance(it, dict):
                continue
            it = copy.deepcopy(it)
            it["id"] = iid
            it.setdefault("name", iid.replace("_", " ").title())
            it.setdefault("description", "")
            if "states" in it and "current_state" not in it:
                it["current_state"] = next(iter(it["states"]))
            items[iid] = it
        return items

    @staticmethod
    def _norm_characters(raw):
        chars = {}
        for cid, ch in (raw or {}).items():
            if not isinstance(ch, dict):
                continue
            ch = copy.deepcopy(ch)
            ch["id"] = cid                       # the key is authoritative
            ch.setdefault("name", cid.replace("_", " ").title())
            ch.setdefault("type", "neutral")
            ch.setdefault("description", "")
            chars[cid] = ch
        return chars

    def _legacy_fixups(self):
        """Carry the original engine's hard-coded conventions over as data."""
        # the old engine let a 'bent_wire' pick any lock that had no passcode
        if not any(it.get("lockpick") for it in self.items.values()) and "bent_wire" in self.items:
            self.items["bent_wire"]["lockpick"] = True
        # characters listed in a scene but placed by 'initial_scene'
        for cid, ch in self.characters.items():
            if ch.get("movable") and ch.get("initial_scene") in self.scenes:
                here = self.scenes[ch["initial_scene"]]["characters"]
                if not any(cid in sc["characters"] for sc in self.scenes.values()):
                    here.append(cid)
        # drop references to things that do not exist (the old engine crashed on these)
        for sc in self.scenes.values():
            sc["items"] = [i for i in sc["items"] if i in self.items]
            sc["passive_items"] = [i for i in sc["passive_items"] if i in self.items]
            sc["characters"] = [c for c in sc["characters"] if c in self.characters]

    # ------------------------------------------------------------------ #
    def validate(self):
        """Return a list of human-readable problems found in the data."""
        problems = []
        if self.scenes and self.initial_scene not in self.scenes:
            problems.append("initial_scene '%s' does not exist" % self.initial_scene)
        for sid, sc in self.scenes.items():
            for ex in sc["exits"]:
                if str(ex.get("scene_id", "")).startswith("@"):
                    continue                    # filled in by the dungeon generator
                if ex.get("scene_id") not in self.scenes:
                    problems.append("scene '%s': exit '%s' leads to unknown scene '%s'"
                                    % (sid, ex.get("door_name"), ex.get("scene_id")))
                req = ex.get("required_item")
                if req and req != "passcode" and req not in self.items:
                    problems.append("scene '%s': exit needs unknown item '%s'" % (sid, req))
        for iid, it in self.items.items():
            for comp in it.get("components", []) or []:
                if comp not in self.items:
                    problems.append("item '%s': unknown component '%s'" % (iid, comp))
            for c in it.get("contents", []) or []:
                if c not in self.items:
                    problems.append("item '%s': unknown content '%s'" % (iid, c))
            st = it.get("states")
            if st and it.get("current_state") not in st:
                problems.append("item '%s': current_state '%s' is not a state" % (iid, it.get("current_state")))
        for cid, ch in self.characters.items():
            for i in ch.get("inventory", []) or []:
                if i not in self.items:
                    problems.append("character '%s': unknown inventory item '%s'" % (cid, i))
            dlg = ch.get("dialogue_tree")
            if dlg and dlg not in self.dialogues:
                problems.append("character '%s': unknown dialogue '%s'" % (cid, dlg))
        for did, dlg in self.dialogues.items():
            nodes = dlg.get("nodes", {})
            for nid, node in nodes.items():
                for ch in node.get("choices", []) or []:
                    g = ch.get("goto")
                    if g and g not in nodes and g not in ("end", "back"):
                        problems.append("dialogue '%s': node '%s' goes to unknown node '%s'" % (did, nid, g))
        problems += self._validate_modes()
        problems += self._validate_dungeon()
        return problems

    def _validate_modes(self):
        problems = []
        modes = self.config.get("modes")
        if modes is not None:
            if not isinstance(modes, dict) or not modes:
                problems.append("modes: must be an object of {id: {name, description, ...}}")
            else:
                for mid, spec in modes.items():
                    if not isinstance(spec, dict):
                        problems.append("mode '%s': must be an object" % mid)
                    elif spec.get("endless") and not self.config.get("generator"):
                        problems.append("mode '%s': 'endless' needs a dungeon generator" % mid)
        score = self.config.get("score")
        if score is not None:
            if not isinstance(score, dict):
                problems.append("score: must be an object of {name: weight}")
            else:
                for name, weight in score.items():
                    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                        problems.append("score: the weight of '%s' is not a number" % name)
        return problems

    def _validate_dungeon(self):
        problems = []
        floors = self.dungeon.get("floors") or []

        def values(table):
            out = []
            for t in table or []:
                weighted = isinstance(t, (list, tuple)) and len(t) == 2 \
                    and isinstance(t[1], (int, float)) and not isinstance(t[1], bool)
                out.append(t[0] if weighted else t)
            return out

        def check_floor(where, fl):
            for mid in values(fl.get("monsters")):
                if mid not in self.characters:
                    problems.append("%s: unknown monster '%s'" % (where, mid))
            for group in values(fl.get("packs")):
                if not isinstance(group, (list, tuple)) or not group:
                    problems.append("%s: a pack must be a list of monsters with a weight, "
                                    "like [[\"rat\", \"rat\"], 2]" % where)
                    continue
                for mid in group:
                    if mid not in self.characters:
                        problems.append("%s: unknown monster '%s' in a pack" % (where, mid))
            for key in ("elite", "boss", "wanderer", "merchant"):
                ref = fl.get(key)
                if isinstance(ref, str) and ref not in self.characters:
                    problems.append("%s: unknown %s '%s'" % (where, key, ref))
            for key in ("loot", "chest_loot"):
                for iid in values(fl.get(key)):
                    if iid not in self.items:
                        problems.append("%s: unknown item '%s' in %s" % (where, iid, key))

        for n, fl in enumerate(floors, 1):
            check_floor("dungeon floor %d" % n, fl)
        endless = self.dungeon.get("endless")
        if isinstance(endless, dict):
            check_floor("dungeon endless.floor", endless.get("floor") or {})
            for i in endless.get("cycle") or []:
                if not isinstance(i, int) or not 0 <= i < len(floors):
                    problems.append("dungeon endless.cycle: there is no floor with index %r" % (i,))
        return problems
