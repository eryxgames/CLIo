# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The mutable state of a game in progress, and saving / loading it."""
from __future__ import annotations

import copy
import json
import os
import random
import time

SAVE_VERSION = 2


class World:
    def __init__(self, data, seed=None):
        self.data = data
        self.scenes = copy.deepcopy(data.scenes)
        self.items = copy.deepcopy(data.items)
        self.characters = copy.deepcopy(data.characters)
        stats = dict(data.player_stats)
        stats.pop("equipment", None)
        stats.setdefault("health", 100)
        stats.setdefault("max_health", stats["health"])
        stats.setdefault("attack", 5)
        stats.setdefault("defense", 5)
        self.player = {
            "name": "You", "class": None, "stats": stats, "inventory": [], "equipped": [],
            "gold": int(data.config.get("starting_gold", 0)), "xp": 0, "level": 1,
            "abilities": list(data.config.get("abilities_start", [])), "status": {},
        }
        for iid in data.config.get("starting_items", []):
            if iid in self.items:
                self.player["inventory"].append(iid)
        self.scene_id = data.initial_scene
        self.prev_scene = None
        self.flags = {}
        self.vars = {}
        self.visited = []
        self.turn = 0
        self.hints_used = 0
        self.quests = {}
        self.fired = []
        self.shown = []
        self.crafting = {}
        self.defeated = []
        self.counter = 0
        self.seed = seed if seed is not None else random.randrange(1, 10 ** 9)
        self.rng = random.Random(self.seed)
        self.positions = None          # map layout cache (rebuilt on demand, never saved)
        self.started = time.time()

    # -- convenience ------------------------------------------------------- #
    @property
    def scene(self):
        return self.scenes[self.scene_id]

    @property
    def stats(self):
        return self.player["stats"]

    @property
    def inventory(self):
        return self.player["inventory"]

    @property
    def equipped(self):
        return self.player["equipped"]

    def has(self, item_id):
        return item_id in self.player["inventory"] or item_id in self.player["equipped"]

    def flag(self, name):
        return self.flags.get(name)

    def char_scene(self, char_id):
        for sid, sc in self.scenes.items():
            if char_id in sc.get("characters", []):
                return sid
        return None

    def item_scene(self, item_id):
        for sid, sc in self.scenes.items():
            if item_id in sc.get("items", []) or item_id in sc.get("passive_items", []):
                return sid
        return None

    def spawn(self, template_id, scene_id=None, overrides=None):
        """Create a fresh copy of a character and put it in a scene."""
        base = self.characters.get(template_id) or self.data.characters.get(template_id)
        if base is None:
            return None
        self.counter += 1
        new_id = "%s#%d" % (template_id.split("#")[0], self.counter)
        ch = copy.deepcopy(self.data.characters.get(template_id.split("#")[0], base))
        ch["id"] = new_id
        ch["template"] = template_id.split("#")[0]
        ch.pop("defeated", None)
        if overrides:
            for k, v in overrides.items():
                if isinstance(v, dict) and isinstance(ch.get(k), dict):
                    ch[k].update(v)
                else:
                    ch[k] = v
        self.characters[new_id] = ch
        sid = scene_id or self.scene_id
        if sid in self.scenes:
            self.scenes[sid].setdefault("characters", []).append(new_id)
        return new_id

    def clone_item(self, template_id, overrides=None):
        """A private copy of an item (for fixtures that keep their own state)."""
        base = self.data.items.get(template_id) or self.items.get(template_id)
        if base is None:
            return None
        self.counter += 1
        new_id = "%s#%d" % (template_id, self.counter)
        it = copy.deepcopy(base)
        it["id"] = new_id
        it["template"] = template_id
        if overrides:
            it.update(copy.deepcopy(overrides))
        self.items[new_id] = it
        return new_id

    # -- persistence ------------------------------------------------------- #
    def to_save(self):
        state = self.rng.getstate()
        return {
            "version": SAVE_VERSION, "game": self.data.id, "title": self.data.title,
            "saved_at": time.strftime("%Y-%m-%d %H:%M"),
            "scenes": self.scenes, "items": self.items, "characters": self.characters,
            "player": self.player, "scene_id": self.scene_id, "prev_scene": self.prev_scene,
            "flags": self.flags, "vars": self.vars, "visited": self.visited, "turn": self.turn,
            "hints_used": self.hints_used, "quests": self.quests, "fired": self.fired,
            "shown": self.shown, "crafting": self.crafting, "defeated": self.defeated,
            "counter": self.counter, "seed": self.seed,
            "rng": [state[0], list(state[1]), state[2]],
        }

    def load_save(self, blob):
        if blob.get("game") != self.data.id:
            raise ValueError("That save belongs to a different game (%s)." % blob.get("title", blob.get("game")))
        if blob.get("version") != SAVE_VERSION:
            raise ValueError("That save was made by an incompatible version of CLIo.")
        for key in ("scenes", "items", "characters", "player", "scene_id", "prev_scene", "flags",
                    "vars", "visited", "turn", "hints_used", "quests", "fired", "shown", "crafting",
                    "defeated", "counter", "seed"):
            setattr(self, key, blob[key])
        if self.scene_id not in self.scenes:
            raise ValueError("The save is damaged (unknown location).")
        r = blob.get("rng")
        if r:
            try:
                self.rng.setstate((r[0], tuple(r[1]), r[2]))
            except (TypeError, ValueError):
                self.rng = random.Random(self.seed + self.turn)
        self.positions = None


def saves_dir(game_id, game_dir=None, env=None):
    env = os.environ if env is None else env
    base = env.get("CLIO_SAVES")
    if not base:
        if os.name == "nt":
            root = env.get("APPDATA") or os.path.expanduser("~")
        else:
            root = env.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
        base = os.path.join(root, "clio", "saves")
    path = os.path.join(base, game_id)
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        path = os.path.join(game_dir or os.getcwd(), "saves")
        os.makedirs(path, exist_ok=True)
        return path


def slot_path(folder, slot):
    safe = "".join(c for c in (slot or "save").lower() if c.isalnum() or c in "-_") or "save"
    return os.path.join(folder, safe + ".json")


def write_save(path, blob):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(blob, f)
    os.replace(tmp, path)


def read_save(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_saves(folder):
    out = []
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder)):
            if f.endswith(".json"):
                p = os.path.join(folder, f)
                try:
                    blob = read_save(p)
                    out.append((f[:-5], blob.get("saved_at", ""), blob.get("turn", 0)))
                except (OSError, ValueError):
                    continue
    return out
