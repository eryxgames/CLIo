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
import re

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
                    "sprites": "sprites.json", "dungeon": "dungeon.json", "levels": "levels.json",
                    "monsters": "monsters.json", "tiles": "tiles.json", "weapons": "weapons.json",
                    "models": "models.json", "cards": "cards.json", "stages": "stages.json",
                    "skirmishes": "skirmishes.json", "sims": "sims.json", "realms": "realms.json",
                    "demo": "demo.json", "menus": "menus.json", "planets": "planets.json"}

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
        self.sound_sets = self._sound_sets(cfg)        # name -> sounds played instead (sounds.<name>.json)
        self.sprites = load("sprites") or {}
        self.dungeon = load("dungeon") or {}
        self.levels = load("levels") or {}             # first-person levels (engine/level.py)
        self.monsters = load("monsters") or {}
        self.tiles = load("tiles") or {}               # walls, floors and ceilings of levels, over the engine's
        self.weapons = load("weapons") or {}           # weapons in levels, over game.json's first_person ones
        self.models = load("models") or {}             # low-poly 3D models for levels (engine/model.py)
        self.cards = load("cards") or {}               # cards for card battles (engine/cards.py)
        self.stages = load("stages") or {}             # arcade stages played in real time (engine/arcade.py)
        self.skirmishes = load("skirmishes") or {}     # real-time strategy on a map (engine/rts.py)
        self.sims = load("sims") or {}                 # vehicles and systems in fixed steps (engine/sim.py)
        self.realms = load("realms") or {}             # turn-based strategy, a season at a time (engine/realm.py)
        self.demo = load("demo") or {}                 # clips that play themselves (engine/demo.py)
        self.menus = load("menus") or {}               # the game's own menus (engine/menu.py)
        self.planets = load("planets") or {}           # worlds to look at (engine/viewer.py)
        if cfg.get("console") is not None:             # one name for how its consoles look, under what it says itself
            from . import panels
            panels.apply_console(cfg, self.sims)
        self.art_dir = os.path.join(self.dir, cfg.get("art_dir", "art"))

        self.theme = cfg.get("style") or cfg.get("style_config") or "default"
        self.initial_scene = cfg.get("initial_scene") or (next(iter(self.scenes)) if self.scenes else None)
        self.player_stats = dict(cfg.get("player_stats", {"health": 100, "attack": 5, "defense": 5}))
        self.max_hints = int(cfg.get("max_hints", 5))
        self._legacy_fixups()

    # ------------------------------------------------------------------ #
    def _sound_sets(self, cfg):
        """Other sets of sound effects, to play instead of the game's own: every ``sounds.<name>.json`` in the
        game's folder, and those game.json lists under ``"sound_sets"`` (name -> file)."""
        found = {}
        try:
            names = sorted(os.listdir(self.dir))
        except OSError:
            names = []
        for fn in names:
            m = re.match(r"sounds\.([A-Za-z0-9_-]+)\.json$", fn)
            if m:
                found[m.group(1).lower()] = fn
        listed = cfg.get("sound_sets")
        if isinstance(listed, dict):
            for name, fn in listed.items():
                if isinstance(fn, str):
                    found[str(name).lower()] = fn
        self._missing_sets = []
        sets = {}
        for name, fn in found.items():
            p = fn if os.path.isabs(fn) else os.path.join(self.dir, fn)
            if os.path.isfile(p):
                blob = read_json(p)
                sets[name] = blob if isinstance(blob, dict) else {}
            else:
                self._missing_sets.append((name, fn))
        return sets

    def _validate_sounds(self):
        """Sound sets, and the Ballistic sounds in them and in sounds.json."""
        problems = []
        for name, fn in getattr(self, "_missing_sets", []):
            problems.append("game.json: sound set '%s' has no file %s" % (name, fn))
        want = self.config.get("sound_set")
        if want and str(want).lower() not in ("default", "none") and str(want).lower() not in self.sound_sets:
            problems.append("game.json: unknown sound_set '%s' (there are: %s)"
                            % (want, ", ".join(["default"] + sorted(self.sound_sets))))
        try:
            from .audio import ballistic
        except ImportError:                         # an engine without its audio package (the editor in a browser)
            return problems
        tables = [("sounds.json", self.sounds)] + [("sounds.%s.json" % n, s) for n, s in sorted(self.sound_sets.items())]
        for where, table in tables:
            for sid, spec in (table or {}).items():
                if ballistic.is_spec(spec):
                    problems += ballistic.problems(spec, "%s: sound '%s'" % (where, sid))
        return problems

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
        problems += self._validate_looks()
        problems += self._validate_sounds()
        if self.levels or self.monsters or self.tiles or self.weapons:
            from . import level
            problems += level.validate(self)
            problems += level.duel_problems(self)
            for sid, sc in self.scenes.items():
                if sc.get("level") and sc["level"] not in self.levels:
                    problems.append("scene '%s': unknown level '%s'" % (sid, sc["level"]))
        if self.cards or self.config.get("cards") or self.config.get("battle") \
                or any(isinstance(m, dict) and m.get("battle") for m in (self.config.get("modes") or {}).values()) \
                or any(isinstance(c, dict) and (c.get("deck") or c.get("battle")) for c in self.characters.values()):
            from . import cards
            problems += cards.problems(self)
        if self.stages or self.config.get("arcade") or any(sc.get("stage") for sc in self.scenes.values()):
            from . import arcade
            problems += arcade.problems(self)
        if self.skirmishes or self.config.get("rts") or any(sc.get("skirmish") for sc in self.scenes.values()):
            from . import rts
            problems += rts.problems(self)
        if self.sims or any(sc.get("sim") for sc in self.scenes.values()):
            from . import sim
            problems += sim.problems(self)
        for name, song in self.songs.items():            # a song's own rules for its cue sheet
            if isinstance(song, dict) and "cues" in song:
                from . import cues
                problems += cues.problems(song["cues"], "song '%s' cues" % name)
        if self.realms or any(sc.get("realm") for sc in self.scenes.values()):
            from . import realm
            problems += realm.problems(self)
        if self.demo:
            from . import demo
            problems += demo.problems(self.demo, self)
        if self.planets:
            from . import viewer
            problems += viewer.planet_problems(self)
            problems += viewer.look_problems(self)
        if self.config.get("console") is not None:
            from . import panels
            problems += panels.console_problems(self.config)
        if self.menus or self.config.get("menu_look") or self.config.get("menu_border"):
            from . import menu
            problems += menu.problems(self)
        return problems

    def _validate_looks(self):
        """The logo, banners and animations game.json asks for."""
        from . import banner, fx
        from .art import LOGO_ALIASES, logo_names
        problems = []
        cfg = self.config
        logo = cfg.get("logo")
        if logo and logo not in logo_names() + list(LOGO_ALIASES):
            problems.append("game.json: unknown logo '%s' (there are: %s)" % (logo, ", ".join(logo_names())))
        if not fx.known(cfg.get("title_effect")):
            problems.append("game.json: unknown title_effect '%s' (there are: %s)"
                            % (cfg.get("title_effect"), ", ".join(fx.NAMES)))
        own = cfg.get("palettes") or {}
        if not isinstance(own, dict):
            problems.append("game.json: palettes should be names, each with a list of colours")
            own = {}
        for name, value in own.items():
            if not banner.own_palette(value):
                problems.append("game.json: palette '%s' has no colours (a list of #rrggbb, or "
                                "{\"colors\": [...], \"accent\": [...]})" % name)
        from .pixels import STYLES as PICTURE_STYLES
        for name, sp in (self.sprites or {}).items():
            if not isinstance(sp, dict):
                continue
            where = "sprites.json: %s" % name
            if sp.get("style") and sp["style"] not in PICTURE_STYLES:
                problems.append("%s has an unknown style '%s' (there are: %s)"
                                % (where, sp["style"], ", ".join(PICTURE_STYLES)))
            if not fx.known(sp.get("effect")):
                problems.append("%s has an unknown effect '%s'" % (where, sp.get("effect")))
            frames = sp.get("frames")
            if frames is not None and not (isinstance(frames, list)
                                           and all(isinstance(f, list) and all(isinstance(r, str) for r in f)
                                                   for f in frames)):
                problems.append("%s: frames should be drawings like pixels (lists of rows)" % where)
            elif frames:
                letters = set("".join(sp.get("pixels") or [])) | set(sp.get("palette") or {}) | {".", " "}
                odd = sorted(set("".join(r for f in frames for r in f)) - letters)
                if odd:
                    problems.append("%s: frames use letters with no colour: %s" % (where, " ".join(odd)))
        for key in ("banner_defaults", "title_banner", "win_banner", "lose_banner"):
            spec = cfg.get(key)
            if not spec or isinstance(spec, str):
                continue
            if not isinstance(spec, dict):
                problems.append("game.json: %s should be a text or an object" % key)
                continue
            style, pal = spec.get("style"), spec.get("palette")
            if style and style not in banner.STYLES:
                problems.append("game.json: %s has an unknown style '%s' (there are: %s)"
                                % (key, style, ", ".join(banner.STYLES)))
            if isinstance(pal, str) and pal not in banner.PALETTES and pal not in own:
                problems.append("game.json: %s has an unknown palette '%s' (there are: %s)"
                                % (key, pal, ", ".join(list(own) + list(banner.PALETTES))))
            if not fx.known(spec.get("effect")):
                problems.append("game.json: %s has an unknown effect '%s'" % (key, spec.get("effect")))
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
