# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The game: world + renderer + audio + parser, and the turn loop that binds them."""
from __future__ import annotations

import os
import re
import time

from . import __version__, automap, conditions, records
from .actions import Actions
from .art import ArtLibrary
from .audio import Audio
from .combat import ABILITIES, Battle
from .data import GameData
from .dialogue import run_dialogue
from .parser import Parser
from .quests import QuestLog
from .term import QuitGame, Term, pad_to, visible_len
from .theme import available_themes, load_theme
from .ui import UI
from .world import (World, list_saves, read_save, saves_dir, slot_path, write_save)

ENGINE_ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art")

# verbs that do not advance the world clock
FREE_VERBS = {"look", "examine", "inventory", "map", "journal", "stats", "help", "hint", "style",
              "sound", "speed", "art", "save", "load", "quit", "restart", "about", "again", "records", None}


class Game(Actions):
    def __init__(self, game_dir, term=None, audio=None, seed=None, settings=None, mode=None):
        self.data = GameData(game_dir)
        self.term = term or Term()
        self.settings = {"art": True, "hud": True, "brief": False}
        self.settings.update(self.data.config.get("settings", {}))
        self.settings.update(settings or {})
        self.ui = UI(self.term, load_theme(self.data.theme, self.data.dir))
        self.audio = audio if audio is not None else Audio(self.data.dir, self.data.songs, self.data.sounds)
        self.audio.game_dir = self.data.dir
        if not self.audio.songs:
            self.audio.songs = dict(self.data.songs)
        if not self.audio.sounds:
            self.audio.sounds = dict(self.data.sounds)
        self.ui.audio = self.audio
        self.art = ArtLibrary(self.data.art_dir, ENGINE_ART)
        self.parser = Parser(self.data.config.get("verbs"))
        self.abilities = {k: dict(v) for k, v in ABILITIES.items()}
        for aid, spec in (self.data.config.get("abilities") or {}).items():
            # a game may add skills, or change a few fields of a built-in one
            self.abilities.setdefault(aid, {}).update(spec)
        self.quests = QuestLog(self)
        self.over = None
        self.battle = None
        self.last_command = ""
        self.seed = seed
        self.mode_request = mode        # a game mode asked for up front (else the player is asked)
        self.started = False
        self.save_dir = None
        self._in_turn = False
        self.new_world(seed)

    # ------------------------------------------------------------------ #
    # setup
    # ------------------------------------------------------------------ #
    def new_world(self, seed=None):
        self.world = World(self.data, seed)
        self.over = None
        self.started = False
        self.battle = None
        if self.data.config.get("generator"):
            from . import maze
            maze.generate(self)

    @property
    def cfg(self):
        return self.data.config

    def saves(self):
        if self.save_dir is None:
            self.save_dir = saves_dir(self.data.id, self.data.dir)
        return self.save_dir

    # ------------------------------------------------------------------ #
    # game modes
    # ------------------------------------------------------------------ #
    @property
    def modes(self):
        """Ways to play, from ``"modes"`` in game.json (``{}`` for most games)."""
        m = self.cfg.get("modes")
        return m if isinstance(m, dict) else {}

    @property
    def mode(self):
        return self.world.vars.get("mode")

    @property
    def mode_spec(self):
        return self.modes.get(self.mode) or {}

    @property
    def permadeath(self):
        """One life: no loading back, and the save is erased when the run ends."""
        return bool(self.mode_spec.get("permadeath"))

    def mode_slot(self, mode=None):
        """The save slot a mode keeps its game in (the first mode uses plain "save")."""
        mode = self.mode if mode is None else mode
        spec = self.modes.get(mode) or {}
        if spec.get("slot"):
            return str(spec["slot"])
        ids = list(self.modes)
        return "save" if mode not in ids or mode == ids[0] else str(mode)

    @property
    def slot(self):
        return self.mode_slot()

    def set_mode(self, mid):
        w = self.world
        spec = self.modes.get(mid) or {}
        w.vars["mode"] = mid
        w.flags["mode_%s" % mid] = True
        for flag in ("permadeath", "endless"):
            if spec.get(flag):
                w.flags[flag] = True
        flags = spec.get("flags") or []
        for flag in ([flags] if isinstance(flags, str) else flags):
            w.flags[flag] = True

    def choose_mode(self):
        """Settle the game mode: the one asked for, the only one, or the player's pick."""
        modes = self.modes
        if not modes:
            return
        ids = list(modes)
        if self.mode_request in modes:
            mid = self.mode_request
        elif len(ids) == 1:
            mid = ids[0]
        else:
            ui = self.ui
            labels = ["{key}%s{/} {hint}%s{/} %s" % (modes[m].get("name", m), ui.g("dot"),
                                                     modes[m].get("description", "")) for m in ids]
            pick = ui.menu(labels, title=self.cfg.get("mode_prompt", "How will you play?"), cancel=False)
            mid = ids[pick or 0]
            self.audio.sfx("select")
        self.set_mode(mid)
        if modes[mid].get("text"):
            self.say(modes[mid]["text"], "story")

    # ------------------------------------------------------------------ #
    # text helpers
    # ------------------------------------------------------------------ #
    def subst(self, text):
        if isinstance(text, str) and "$" in text:
            p = self.world.player
            text = text.replace("$player", str(p.get("name", "You")))
            text = text.replace("$class", str(p.get("class_name", p.get("class") or "")))
            text = re.sub(r"\$var\.(\w+)", lambda m: str(self.world.vars.get(m.group(1), 0)), text)
        return text

    def say(self, text, role="default", **kw):
        if isinstance(text, dict):
            role = text.get("style", role)
            text = text.get("text", "")
        if isinstance(text, (list, tuple)):
            text = "\n\n".join(str(t) for t in text if t)
        if not text:
            return
        kw = {k: v for k, v in kw.items() if v is not None}
        self.ui.say(self.subst(str(text)), role, **kw)

    def text(self, key, default=None):
        """Look up a story text by key (a missing key returns the default)."""
        entry = self.data.texts.get(key) if isinstance(key, str) else None
        if isinstance(entry, dict):
            return entry.get("text", default)
        if isinstance(entry, str):
            return entry
        return default

    def story_text(self, key, role="story"):
        """Show a story text; entries marked ``show_once`` appear only once."""
        entry = self.data.texts.get(key) if isinstance(key, str) else None
        if entry is None:
            if isinstance(key, str) and (" " in key or len(key) > 40):
                self.say(key, role)             # literal text rather than a key
            return
        if isinstance(entry, dict):
            if entry.get("show_once"):
                if key in self.world.shown:
                    return
                self.world.shown.append(key)
            self.say(entry.get("text", ""), entry.get("style", role))
        else:
            self.say(entry, role)

    def art_lines(self, name, max_width=None, max_height=None):
        if not name or not self.settings.get("art", True) or not self.ui.theme.ui.get("art", True):
            return []
        art = self.art.get(name)
        if not art:
            return []
        return art.render(self.term, max_width if max_width is not None else self.ui.width - 4, max_height)

    def show_art(self, name):
        lines = self.art_lines(name)
        if lines:
            self.ui.gap()
            for l in lines:
                self.ui.line(pad_to(l, self.ui.width, "center").rstrip())
            self.ui.gap()

    def dialogue_box(self, speaker, text, portrait=None):
        """A line of speech, with a portrait beside it when there is room."""
        ui = self.ui
        text = self.subst(text if isinstance(text, str) else "\n\n".join(text))
        st = ui.theme.style("dialogue")
        if portrait:
            pw = max(visible_len(l) for l in portrait)
            pad = 1 if ui.narrow else min(2, st["padding"])
            framed = ui.frame_chars(st["frame"]) is not None
            inner = ui.width - (2 + 2 * pad if framed else 1)
            if inner - pw - 2 >= 24:
                body = ui.wrap(text, "dialogue", inner - pw - 2)
                ui.panel([("lines", ui.side_by_side(portrait, body))], "dialogue", title=speaker,
                         delay=0)
                return
        ui.say(text, "dialogue", title=speaker)

    # ------------------------------------------------------------------ #
    # the player's things
    # ------------------------------------------------------------------ #
    def item(self, iid):
        return self.world.items.get(iid, {"id": iid, "name": iid, "description": ""})

    def iname(self, iid):
        return "{item}%s{/}" % self.item(iid).get("name", iid)

    def cname(self, cid):
        return "{character}%s{/}" % self.world.characters.get(cid, {}).get("name", cid)

    def give_item(self, iid, quiet=False):
        if iid not in self.world.items:
            return False
        self.world.inventory.append(iid)
        if not quiet:
            self.audio.sfx("pickup")
            self.say("%s added to your inventory." % self.iname(iid), "item")
        return True

    def remove_item(self, iid, quiet=True):
        w = self.world
        if iid in w.inventory:
            w.inventory.remove(iid)
        elif iid in w.equipped:
            w.equipped.remove(iid)
            for stat, val in (self.item(iid).get("effect") or {}).items():
                if stat != "health":
                    w.stats[stat] = w.stats.get(stat, 0) - val
            w.stats["health"] = min(w.stats.get("health", 0), w.stats.get("max_health", 1))
        else:
            return False
        if not quiet:
            self.say("You no longer have the %s." % self.iname(iid), "system")
        return True

    def change_stat(self, name, delta, announce=True):
        st = self.world.stats
        before = st.get(name, 0)
        value = before + delta
        if name == "health":
            value = max(0, min(value, st.get("max_health", value)))
        st[name] = value
        if name == "max_health" and delta > 0:
            st["health"] = min(st["max_health"], st.get("health", 0) + delta)
        diff = value - before
        if announce and diff:
            if name == "health":
                if diff > 0:
                    self.say("{heal}+%d health{/} {hint}(%d/%d){/}" % (diff, value, st["max_health"]), "heal")
                else:
                    self.audio.sfx("hurt")
                    self.say("{damage}%d health{/} {hint}(%d/%d){/}" % (diff, value, st["max_health"]), "damage")
            else:
                self.say("%s %+d" % (name.replace("_", " ").title(), diff), "success" if diff > 0 else "warning")
        return diff

    def add_gold(self, n):
        p = self.world.player
        p["gold"] = max(0, p.get("gold", 0) + n)
        if n > 0:
            self.audio.sfx("coin")
            self.say("{quest}%s +%d %s{/}" % (self.ui.g("coin"), n, self.cfg.get("currency", "gold")), "quest")

    def xp_needed(self, level):
        return int(self.cfg.get("xp_base", 30)) * level + 10 * level * (level - 1)

    def add_xp(self, n):
        p = self.world.player
        if n <= 0 or not self.cfg.get("rpg", True):
            return
        p["xp"] = p.get("xp", 0) + n
        self.say("{hint}+%d experience{/}" % n, "system")
        while p["xp"] >= self.xp_needed(p.get("level", 1)):
            p["xp"] -= self.xp_needed(p["level"])
            p["level"] = p.get("level", 1) + 1
            growth = dict(self.cfg.get("level_growth", {"max_health": 10, "attack": 1, "defense": 1}))
            cls = (self.cfg.get("character_creation", {}).get("classes", {}) or {}).get(p.get("class") or "", {})
            growth.update(cls.get("growth", {}))
            st = self.world.stats
            for k, v in growth.items():
                st[k] = st.get(k, 0) + v
            st["health"] = st.get("max_health", st.get("health", 1))
            self.audio.sfx("levelup")
            gains = ", ".join("%s +%s" % (k.replace("_", " "), v) for k, v in growth.items())
            self.say("{quest}%s Level %d!{/} {hint}%s. Health restored.{/}" % (self.ui.g("star"), p["level"], gains),
                     "quest")
            for a in (cls.get("learn", {}) or {}).get(str(p["level"]), []):
                conditions.run({"learn": a}, self)

    # ------------------------------------------------------------------ #
    # characters
    # ------------------------------------------------------------------ #
    def is_defeated(self, cid):
        w = self.world
        if cid in w.defeated or w.flags.get("%s_defeated" % cid):
            return True
        ch = w.characters.get(cid)
        return bool(ch and ch.get("defeated"))

    def char_here(self, cid):
        chars = self.world.scene.get("characters", [])
        if cid in chars:
            return True
        return any(self.world.characters.get(c, {}).get("template") == cid for c in chars)

    def chars_here(self):
        return [c for c in self.world.scene.get("characters", []) if c in self.world.characters]

    def is_hostile(self, ch):
        return ch.get("type") in ("hostile", "aggressive")

    def resolve_char(self, ref):
        """A character id for ``ref``: someone here first (by id, then by template)."""
        w = self.world
        here = self.chars_here()
        if ref in here:
            return ref
        for cid in here:
            if w.characters[cid].get("template") == ref:
                return cid
        return ref if ref in w.characters else None

    def talk_to(self, ref):
        """Start a conversation with a character id (or run a dialogue tree by id)."""
        w = self.world
        cid = self.resolve_char(ref)
        ch = w.characters.get(cid) if cid else None
        if ch is None and ref in self.data.dialogues:
            ch = {"id": ref, "name": self.data.dialogues[ref].get("speaker", "?")}
            run_dialogue(self, ch, self.data.dialogues[ref])
            return
        if ch is not None:
            run_dialogue(self, ch)

    def fight_group(self, cid):
        """The enemy and every other hostile in the room: they fight together."""
        w = self.world
        ids = [cid]
        first = w.characters[cid]
        if self.cfg.get("group_fights", True) and not first.get("solo") and cid in self.chars_here():
            for other in self.chars_here():
                ch = w.characters[other]
                if other != cid and self.is_hostile(ch) and not ch.get("defeated") \
                        and not ch.get("solo") and ch.get("stats"):
                    ids.append(other)
        return ids[:max(1, int(self.cfg.get("max_enemies", 4)))]

    def start_fight(self, cid, can_flee=True):
        """Fight a character (and its allies in the room). Returns "win", "lose", "fled" or None."""
        w = self.world
        cid = self.resolve_char(cid)
        if cid is None:
            return None
        ids = self.fight_group(cid)
        battle = Battle(self, ids, can_flee)
        self.fight_started(ids)
        result = battle.run()
        self.fight_ended()
        if result != "lose":
            for dead in battle.fallen:          # also those brought down before running away
                self.on_defeat(dead, named=len(ids) > 1)
        if result == "lose":
            killer = battle.killer.char if battle.killer else w.characters[cid]
            self.end_game("lose", killer.get("lose_text") or "outro_lose")
        elif result == "fled":
            back = w.prev_scene
            if back and back in w.scenes and back != w.scene_id:
                self.enter_scene(back, quiet=False, fled=True)
        return result

    def on_defeat(self, cid, named=False):
        w = self.world
        ch = w.characters[cid]
        ch["defeated"] = True
        w.defeated.append(cid)
        w.flags["%s_defeated" % cid] = True
        tpl = ch.get("template")
        if tpl:
            w.flags["%s_defeated" % tpl] = True
            w.vars["kills"] = w.vars.get("kills", 0) + 1
        sid = w.char_scene(cid)
        if sid:
            sc = w.scenes[sid]
            sc["characters"].remove(cid)
            drops = list(ch.get("inventory", []) or [])
            for entry in ch.get("loot", []) or []:           # [item, chance]
                if isinstance(entry, (list, tuple)):
                    if w.rng.random() < float(entry[1]):
                        drops.append(entry[0])
                else:
                    drops.append(entry)
            drops = [d for d in drops if d in w.items]
            for d in drops:
                sc.setdefault("items", []).append(d)
            if drops:
                self.say("%s leaves behind: %s." % (self.cname(cid) if named else "It",
                                                    ", ".join(self.iname(d) for d in drops)), "loot")
        if ch.get("gold"):
            g = ch["gold"]
            if isinstance(g, (list, tuple)):
                g = w.rng.randint(int(g[0]), int(g[1]))
            self.add_gold(int(g))
        if ch.get("xp"):
            self.add_xp(int(ch["xp"]))
        if ch.get("on_defeat"):
            conditions.run(ch["on_defeat"], self)

    # ------------------------------------------------------------------ #
    # scenes
    # ------------------------------------------------------------------ #
    def exit_hidden(self, ex):
        if ex.get("hidden"):
            return True
        cond = ex.get("show_if")
        return cond is not None and not conditions.check(cond, self)

    def visible_exits(self, scene=None):
        sc = scene or self.world.scene
        return [ex for ex in sc.get("exits", []) if not self.exit_hidden(ex)]

    def positions(self):
        w = self.world
        if w.positions is None:
            w.positions = automap.layout(w.scenes, self.data.initial_scene or w.scene_id)
        return w.positions

    def exit_label(self, ex, with_dir=True):
        w = self.world
        name = ex.get("door_name") or ""
        dest = w.scenes.get(ex.get("scene_id"), {})
        if not name:
            name = dest.get("name", "?") if ex.get("scene_id") in w.visited else "a passage"
        d = automap.exit_dir(ex) if with_dir else None
        label = "{exit}%s{/}" % name
        if d and (ex.get("dir") or self.cfg.get("show_directions", not self.data.legacy)):
            label = "{key}%s{/} %s" % (automap.DIR_NAMES.get(d, d), label)
        if ex.get("locked"):
            label += " {hint}(locked){/}"
        elif ex.get("blocked") or self.exit_guard(ex):
            label += " {hint}(blocked){/}"
        return label

    def exit_guard(self, ex):
        """The living character guarding an exit, if any."""
        g = ex.get("guard")
        if not g:
            return None
        for cid in self.chars_here():
            ch = self.world.characters[cid]
            if cid == g or ch.get("template") == g:
                return cid
        return None

    def describe_scene(self, full=True, entering=False):
        w, ui = self.world, self.ui
        sc = w.scene
        first = entering and sc.get("_seen") is None
        show_art = full or first or not self.settings.get("brief")
        desc = sc.get("description", "")
        role = "description"
        if isinstance(desc, dict):
            role = desc.get("style", role)
            desc = desc.get("text", "")
        # a longer first-visit text (new: "first_visit"; legacy: "<id>_description" story text)
        if first:
            long_text = sc.get("first_visit")
            key = "%s_description" % sc["id"]
            if not long_text and self.data.legacy and key in self.data.texts and key not in w.shown:
                long_text = self.text(key)
                w.shown.append(key)
            if long_text:
                desc = long_text
        elif not full and sc.get("brief"):
            desc = sc["brief"]
        for extra in sc.get("extra", []) or []:
            if conditions.check(extra.get("if"), self) and extra.get("text"):
                if extra.get("replace"):
                    desc = extra["text"]
                else:
                    desc = (desc + " " + extra["text"]).strip()
        desc = self.subst(desc)
        art_name = self.scene_variant(sc, "art")
        art = self.art_lines(art_name, None, None) if show_art else []
        st = ui.theme.style("description")
        framed = ui.frame_chars(st["frame"]) is not None
        pad = min(st["padding"], 1 if ui.narrow else 2)
        inner = ui.width - (2 + 2 * pad if framed else 1)
        if art:
            aw = max(visible_len(l) for l in art)
            if aw > inner:
                art = self.art_lines(art_name, inner, None)
                aw = max((visible_len(l) for l in art), default=0)
        parts = []
        if art and inner - aw - 3 >= 30:
            body = ui.wrap(desc, role, inner - aw - 3)
            top = max(0, (len(art) - len(body)) // 2)
            parts.append(("lines", ui.side_by_side(art, [""] * top + body, gap=3)))
        else:
            if art:
                parts.append(("art", art))
                parts.append(("blank",))
            parts.append(("text", desc, role))
        title = sc.get("name", sc["id"])
        ui.panel(parts, "description", title=title, delay=st["character_delay"] if (first or full) else 0)
        sc["_seen"] = True

        # ambient flavour
        events = sc.get("random_events") or []
        if events and (full or w.rng.random() < 0.5):
            self.say(w.rng.choice(events), "ambient")

        m = " " * int(ui.theme.ui.get("margin", 1))
        items = [i for i in sc.get("items", []) if i in w.items]
        fixtures = [i for i in sc.get("passive_items", []) if i in w.items and not w.items[i].get("scenery")]
        if items:
            for l in ui.wrap("You see: " + self._name_list(items) + ".", "default", ui.width - 1, m, m + "  "):
                ui.line(l)
        if fixtures:
            for l in ui.wrap("You notice: " + self._name_list(fixtures) + ".", "default", ui.width - 1, m, m + "  "):
                ui.line(l)
        for cid in self.chars_here():
            ch = w.characters[cid]
            greet = ch.get("greeting") or ""
            if isinstance(ch.get("dialogue"), dict) and not greet:
                greet = ch["dialogue"].get("greet", "")
            if ch.get("ambush") and self.is_hostile(ch) and entering:
                greet = ""                      # it is about to introduce itself
            tag = " {error}(hostile){/}" if self.is_hostile(ch) and ch.get("show_hostile", True) else ""
            line = "%s%s%s" % (self.cname(cid), tag, (" {hint}%s{/} %s" % (ui.g("dot"), greet)) if greet else "")
            for l in ui.wrap(line, "greeting", ui.width - 1, m, m + "  "):
                ui.line(l)
            if full and ch.get("random_events") and w.rng.random() < 0.6:
                for l in ui.wrap(w.rng.choice(ch["random_events"]), "ambient", ui.width - 1, m + "  ", m + "  "):
                    ui.line(l)
        exits = self.visible_exits()
        if exits:
            self.positions()
            line = "Exits: " + ", ".join(self.exit_label(ex) for ex in exits) + "."
            for l in ui.wrap(line, "default", ui.width - 1, m, m + "  "):
                ui.line(l)
        ui._last = "text"

    def _name_list(self, ids):
        out, seen = [], {}
        for i in ids:
            seen[i] = seen.get(i, 0) + 1
        for i, n in seen.items():
            out.append(self.iname(i) + (" x%d" % n if n > 1 else ""))
        return ", ".join(out)

    def scene_variant(self, sc, key):
        """``art`` / ``music`` of a scene, honouring ``art_if`` / ``music_if`` overrides."""
        for entry in sc.get(key + "_if", []) or []:
            if conditions.check(entry.get("if"), self) and entry.get(key):
                return entry[key]
        return sc.get(key)

    def resume_music(self):
        sc = self.world.scene
        default = self.cfg.get("music") or {"generate": {"mood": sc.get("mood") or self.cfg.get("mood", "mystery"),
                                                         "seed": self.data.id}}
        track = self.scene_variant(sc, "music") or default
        self.audio.music(track, fallback=default)

    def play_music(self, track, raw=False):
        self.audio.music(track, fallback=None if raw else (self.cfg.get("music") or None))

    def enter_scene(self, sid, quiet=False, fled=False, first=False):
        w = self.world
        if sid not in w.scenes:
            self.say("That way leads nowhere.", "error")
            return False
        if not first:
            w.prev_scene = w.scene_id
        w.scene_id = sid
        sc = w.scene
        new = sid not in w.visited
        if new:
            w.visited.append(sid)
        if not first and not quiet:
            self.ui.transition()
            sfx = (sc.get("sound_effects") or {}).get("enter")
            self.audio.sfx(sfx or sc.get("enter_sfx") or "step", fallback=sc.get("enter_sfx") or "door")
        self.resume_music()
        if not quiet:
            self.describe_scene(full=new or not self.settings.get("brief"), entering=True)
        if new and sc.get("on_first_enter"):
            conditions.run(sc["on_first_enter"], self)
        if sc.get("on_enter") and not self.over and w.scene_id == sid:
            conditions.run(sc["on_enter"], self)
        # followers come along
        if not self.over and w.scene_id == sid:
            for cid, ch in w.characters.items():
                if ch.get("follow_player") and not ch.get("defeated") and cid not in sc["characters"]:
                    old = w.char_scene(cid)
                    if old:
                        w.scenes[old]["characters"].remove(cid)
                        sc["characters"].append(cid)
                        if not quiet:
                            self.say("%s follows you." % self.cname(cid), "ambient")
            for cid, ch in w.characters.items():
                if ch.get("movable") and ch.get("moves_on_scene_change") and not ch.get("follow_player"):
                    self.move_npc(cid)
            if not fled:
                self.check_ambush()
        return True

    def check_ambush(self):
        w = self.world
        for cid in list(self.chars_here()):
            ch = w.characters[cid]
            if ch.get("ambush") and self.is_hostile(ch) and not ch.get("defeated"):
                if ch.get("ambush_if") and not conditions.check(ch["ambush_if"], self):
                    continue
                self.say(ch.get("ambush_text") or "%s attacks!" % self.cname(cid), "combat")
                if self.start_fight(cid) != "win" or self.over:
                    return

    def move_npc(self, cid):
        """Move a wandering character through a random open exit."""
        w = self.world
        ch = w.characters[cid]
        here = w.char_scene(cid)
        if not here or ch.get("defeated"):
            return
        roam = ch.get("roam")
        options = [ex["scene_id"] for ex in w.scenes[here].get("exits", [])
                   if not ex.get("locked") and not ex.get("blocked") and not ex.get("hidden")
                   and ex.get("scene_id") in w.scenes and (not roam or ex["scene_id"] in roam)]
        if not options:
            return
        dest = w.rng.choice(options)
        w.scenes[here]["characters"].remove(cid)
        w.scenes[dest].setdefault("characters", []).append(cid)
        if here == w.scene_id:
            self.say("%s leaves." % self.cname(cid), "ambient")
        elif dest == w.scene_id:
            self.say("%s enters." % self.cname(cid), "ambient")
            if ch.get("ambush") and self.is_hostile(ch):
                self.check_ambush()

    # ------------------------------------------------------------------ #
    # the turn
    # ------------------------------------------------------------------ #
    def end_turn(self):
        w = self.world
        if self.over:
            return
        w.turn += 1
        for cid, ch in list(w.characters.items()):
            if self.over:
                return
            if not ch.get("movable") or ch.get("follow_player") or ch.get("defeated"):
                continue
            every = int(ch.get("moves_after_commands", 0) or 0)
            if every > 0:
                ch["_moves"] = ch.get("_moves", 0) + 1
                if ch["_moves"] >= every:
                    ch["_moves"] = 0
                    self.move_npc(cid)
        self.run_triggers()
        self.quests.update()
        self.legacy_conditions()
        if not self.over and w.stats.get("health", 1) <= 0:
            self.end_game("lose", "outro_lose")

    def run_triggers(self):
        w = self.world
        for i, trig in enumerate(self.data.triggers):
            if self.over:
                return
            tid = trig.get("id") or "trigger_%d" % i
            once = trig.get("once", True)
            if once and tid in w.fired:
                continue
            every = trig.get("every")
            if every and w.turn % int(every):
                continue
            if conditions.check(trig.get("when", trig.get("if")), self):
                if once:
                    w.fired.append(tid)
                conditions.run(trig.get("do"), self)

    def legacy_conditions(self):
        """The original ``story_texts.json`` "conditions" block."""
        conds = self.data.texts.get("conditions")
        if not isinstance(conds, dict):
            return
        w = self.world
        for kind, entries in conds.items():
            for name, info in (entries or {}).items():
                key = "cond:%s:%s" % (kind, name)
                if key in w.shown or not isinstance(info, dict):
                    continue
                low = str(name).lower()
                hit = False
                if kind == "item_in_inventory":
                    hit = any(i == name or self.item(i).get("name", "").lower() == low
                              for i in w.inventory + w.equipped)
                elif kind == "enemy_defeated":
                    hit = any(c == name or w.characters.get(c, {}).get("name", "").lower() == low
                              for c in w.defeated)
                if hit:
                    if info.get("show_once", True):
                        w.shown.append(key)
                    self.say(info.get("text", ""), "story")

    def execute(self, line):
        """Run one line of player input."""
        for part in [p for p in re.split(r"\s*;\s*|\s+then\s+", line) if p.strip()] or [""]:
            if self.over:
                return
            self._execute_one(part)

    def _execute_one(self, line):
        cmd = self.parser.parse(line)
        if cmd.verb is None:
            return
        if cmd.verb == "again":
            if not self.last_command:
                self.say("There is nothing to repeat yet.", "error")
                return
            cmd = self.parser.parse(self.last_command)
        else:
            self.last_command = line
        handler = getattr(self, "do_" + cmd.verb, None)
        if handler is None:
            self.say("I don't know how to do that.", "error")
            return
        took_turn = handler(cmd)
        if cmd.verb in FREE_VERBS or took_turn is False:
            return
        self.end_turn()

    def show_hud(self):
        if not self.settings.get("hud", True) or not self.ui.theme.ui.get("hud", True):
            self.ui.gap()
            return
        if not (self.term.interactive or self.settings.get("force_hud")):
            self.ui.gap()
            return
        w, ui = self.world, self.ui
        st = w.stats
        hp, mx = st.get("health", 0), st.get("max_health", 1)
        spec = "green" if hp > mx * 0.5 else ("yellow" if hp > mx * 0.25 else "red")
        parts = [ui.term.paint("%s %d/%d" % (ui.g("heart"), hp, mx), spec)]
        if not ui.narrow:
            parts[0] += " " + ui.bar(hp, mx, 8, spec)
        parts.append(ui.c(w.scene.get("name", ""), "key"))
        if self.cfg.get("rpg") and w.player.get("level"):
            parts.append(ui.c("Lv %d" % w.player["level"], "hud"))
        if w.player.get("gold"):
            parts.append(ui.term.paint("%s %d" % (ui.g("coin"), w.player["gold"]), "gold"))
        parts.append(ui.c("turn %d" % w.turn, "hud"))
        right = ui.c(ui.g("note"), "hud") if (self.audio.enabled and self.audio.music_on and self.audio.playing) else ""
        ui.hud(parts, right)

    def run(self):
        """Play until the game ends or the player quits."""
        try:
            self.term.set_title("CLIo - " + self.data.title)
            self.start()
            while True:
                while not self.over:
                    self.show_hud()
                    line = self.ui.prompt()
                    try:
                        self.execute(line)
                    except KeyboardInterrupt:
                        self.ui.line("")
                        self.say("(interrupted)", "system")
                if self.over == "quit" or not self.after_game():
                    break
        except QuitGame:
            self.suspend()
        except KeyboardInterrupt:
            self.ui.line("")
            self.suspend()
        finally:
            self.audio.shutdown()
            self.term.hide_cursor(False)
            self.term.write(self.term.reset)
            self.term.flush()
        return self.over

    # ------------------------------------------------------------------ #
    # beginning and end
    # ------------------------------------------------------------------ #
    def start(self):
        ui, cfg = self.ui, self.cfg
        ui.clear()
        self.audio.music(cfg.get("title_music") or cfg.get("music")
                         or {"generate": {"mood": cfg.get("mood", "mystery"), "seed": self.data.id}})
        if not self.data.legacy or self.art.get("title"):
            art = self.art_lines("title") or self.art_lines("clio_logo")
            ui.title_screen(art, self.data.title if not art or cfg.get("show_title", True) else "",
                            cfg.get("subtitle", ""),
                            ("by %s" % cfg["author"]) if cfg.get("author") else "")
        else:
            ui.title_screen(self.art_lines("clio_logo"), self.data.title, "CLIo %s" % __version__)
        if self.term.interactive and self.offer_continue():
            return
        if self.term.interactive:
            ui.pause("[Enter to begin]" if not ui.narrow else "[Enter]")
        self.begin_story()

    def resumable(self):
        """Saved games the title screen can offer: ``[(slot, label), ...]``."""
        slots = [self.mode_slot(m) for m in self.modes] or ["save"]
        found = []
        for slot in dict.fromkeys(slots):
            path = slot_path(self.saves(), slot)
            if not os.path.isfile(path):
                continue
            label = ""
            try:
                blob = read_save(path)
                mode = (blob.get("vars") or {}).get("mode")
                bits = [self.modes[mode].get("name", mode)] if mode in self.modes else []
                who = (blob.get("player") or {}).get("name")
                if who and self.cfg.get("character_creation"):
                    bits.append(str(who))
                bits.append("turn %d" % int(blob.get("turn", 0)))
                label = ", ".join(bits)
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            found.append((slot, label))
        return found

    def offer_continue(self):
        """Ask whether to go on with a saved game. True if one was loaded."""
        ui = self.ui
        found = self.resumable()
        if not found:
            return False
        if len(found) == 1:
            slot, label = found[0]
            if ui.confirm("A saved game exists%s. Continue it?" % ((" (%s)" % label) if label else "")):
                return bool(self.load_slot(slot))
            return False
        pick = ui.menu(["Continue {hint}%s{/}" % label for _slot, label in found] + ["New game"],
                       title="Saved games", cancel=False)
        if pick is None or pick >= len(found):
            return False
        return bool(self.load_slot(found[pick][0]))

    def begin_story(self):
        cfg = self.cfg
        self.choose_mode()
        cc = cfg.get("character_creation")
        if cc:
            self.create_character(cc)
        intro = self.mode_spec.get("intro") or cfg.get("intro", "intro")
        self.story_text(intro)
        self.started = True
        if cfg.get("on_start"):
            conditions.run(cfg["on_start"], self)
        if self.mode_spec.get("on_start"):
            conditions.run(self.mode_spec["on_start"], self)
        self.quests.update()
        if not self.over:
            self.enter_scene(self.world.scene_id, first=True)
            self.run_triggers()
            self.quests.update()

    def create_character(self, cc):
        ui, w = self.ui, self.world
        p = w.player
        if cc.get("intro"):
            self.say(cc["intro"], "story")
        if cc.get("ask_name", True):
            name = ui.ask(cc.get("name_prompt", "What is your name?"))
            name = re.sub(r"[{}\x00-\x1f]", "", name).strip()[:20]
            p["name"] = name or cc.get("default_name", "Wanderer")
        classes = cc.get("classes") or {}
        if classes:
            ids = list(classes)
            labels = []
            for cid in ids:
                c = classes[cid]
                labels.append("{key}%s{/} {hint}%s{/} %s" % (c.get("name", cid), ui.g("dot"), c.get("description", "")))
            pick = None
            while pick is None:
                pick = ui.menu(labels, title=cc.get("class_prompt", "Choose your path:"), cancel=False)
                if pick is None:
                    pick = 0
            cid = ids[pick]
            c = classes[cid]
            p["class"] = cid
            p["class_name"] = c.get("name", cid)
            for k, v in (c.get("stats") or {}).items():
                w.stats[k] = v
            w.stats["max_health"] = w.stats.get("max_health", w.stats.get("health", 100))
            w.stats["health"] = w.stats["max_health"]
            for iid in c.get("items", []):
                if iid in w.items:
                    w.inventory.append(iid)
            for iid in c.get("equipped", []):
                if iid in w.items:
                    w.inventory.append(iid)
                    self.equip(iid, quiet=True)
            for a in c.get("abilities", []):
                if a not in p["abilities"]:
                    p["abilities"].append(a)
            p["gold"] = p.get("gold", 0) + int(c.get("gold", 0))
            if "focus_start" in c:
                p["focus_start"] = int(c["focus_start"])
            self.audio.sfx("select")
            if c.get("text"):
                self.say(c["text"], "story")

    def end_game(self, kind, text=None):
        if self.over:
            return
        w, ui = self.world, self.ui
        self.over = kind
        if kind == "win":
            w.flags["game_won"] = True
            for qid, q in self.data.quests.items():      # the story quest ends with the story
                if q.get("complete_on_win") and w.quests.get(qid, {}).get("status") == "active":
                    w.quests[qid]["status"] = "done"
        self.audio.music({"generate": {"mood": "victory" if kind == "win" else "defeat", "seed": self.data.id,
                                       "bars": 8}})
        self.audio.sfx("win" if kind == "win" else "lose")
        body = self.text(text) if isinstance(text, str) else None
        if body is None and isinstance(text, str) and (" " in text):
            body = text
        if body is None and kind == "lose":
            body = self.text("outro_lose", "Your adventure ends here.")
        if body is None and kind == "win":
            body = self.text("outro_win", "You have won.")
        ui.gap()
        art = self.art_lines("win" if kind == "win" else "lose")
        if art:
            self.show_art("win" if kind == "win" else "lose")
        self.say(body, "story", title="THE END" if kind == "win" else "GAME OVER")
        mins = max(1, int((time.time() - w.started) / 60))
        facts = ["%d turns" % w.turn, "%d of %d places seen" % (len(w.visited), len(w.scenes))]
        if w.vars.get("depth") and self.cfg.get("generator"):
            facts.insert(0, "depth %d" % int(w.vars["depth"]))
        done = sum(1 for q in w.quests.values() if q.get("status") == "done")
        if self.data.quests:
            facts.append("%d of %d quests" % (done, len(self.data.quests)))
        if w.hints_used:
            facts.append("%d hints" % w.hints_used)
        if self.term.interactive:
            facts.append("%d min" % mins)
        self.say((" %s " % ui.g("dot")).join(facts), "hint")
        self.finish_run(kind)

    def run_note(self, kind):
        """How a run ended, in a few words (for the records table)."""
        w = self.world
        floor = w.scene.get("floor")
        where = (" on floor %d" % floor) if floor else ""
        if kind == "win":
            return "won"
        killer = getattr(self.battle, "killer", None) if self.battle else None
        if killer is not None and self.battle.result == "lose":
            return "slain by %s%s" % (killer.char.get("name", killer.name), where)
        return "died%s" % where

    def finish_run(self, kind):
        """Score the run, file it in the records, and burn a permadeath save."""
        w = self.world
        if isinstance(self.cfg.get("score"), dict):
            pts = records.score(self)
            p = w.player
            entry = {"score": pts, "name": p.get("name", ""), "class": p.get("class_name", ""),
                     "level": p.get("level", 0) if self.cfg.get("rpg") else 0,
                     "depth": int(w.vars.get("depth", 0) or 0), "turns": w.turn,
                     "result": kind, "note": self.run_note(kind), "seed": w.seed}
            place = None
            try:
                place = records.add(self.saves(), self.mode or "game", entry)
            except (OSError, ValueError, TypeError):
                pass
            line = "{quest}%s Score: %d{/}" % (self.ui.g("star"), pts)
            if place == 1:
                line += " {success}- a new record!{/}"
            elif place:
                line += " {hint}- number %d in the records{/}" % place
            self.say(line, "quest")
        if self.permadeath:
            self.burn_save()

    def burn_save(self):
        try:
            os.remove(slot_path(self.saves(), self.slot))
        except OSError:
            pass

    def after_game(self):
        """Offer to load / restart. Returns True if play continues."""
        if not self.term.interactive:
            return False
        ui = self.ui
        options, actions = [], []
        if self.over == "lose" and not self.permadeath and os.path.isfile(slot_path(self.saves(), self.slot)):
            options.append("Load your last save")
            actions.append("load")
        options.append("Start a new game")
        actions.append("new")
        options.append("Quit")
        actions.append("quit")
        pick = ui.menu(options, cancel=False)
        act = actions[pick] if pick is not None else "quit"
        if act == "load":
            self.over = None
            return bool(self.load_slot())
        if act == "new":
            self.new_world(self.seed)
            ui.clear()
            self.begin_story()
            return True
        return False

    # ------------------------------------------------------------------ #
    # save / load
    # ------------------------------------------------------------------ #
    def save_slot(self, slot=None, quiet=False):
        slot = slot or self.slot
        try:
            path = slot_path(self.saves(), slot)
            write_save(path, self.world.to_save())
        except (OSError, TypeError, ValueError) as e:
            self.say("Could not save: %s" % e, "error")
            return False
        if not quiet:
            self.audio.sfx("save")
            self.say("Game saved%s." % ("" if slot in ("", "save", self.slot) else " as '%s'" % slot), "success")
        return True

    def load_slot(self, slot=None):
        slot = slot or self.slot
        path = slot_path(self.saves(), slot)
        if not os.path.isfile(path):
            self.say("There is no saved game%s." % ("" if slot in ("", "save") else " called '%s'" % slot), "error")
            names = [s[0] for s in list_saves(self.saves())]
            if names:
                self.say("Saved games: " + ", ".join(names), "system")
            return False
        try:
            self.world.load_save(read_save(path))
        except (OSError, ValueError, KeyError) as e:
            self.say("Could not load that save: %s" % e, "error")
            return False
        self.over = None
        self.started = True
        self.battle = None
        self.audio.sfx("save")
        self.say("Game loaded.", "success")
        self.resume_music()
        self.describe_scene(full=True)
        self.resume_fight()
        return True

    # ------------------------------------------------------------------ #
    # permadeath: the run is saved as it goes
    # ------------------------------------------------------------------ #
    def fight_started(self, ids):
        """A battle is about to begin: a one-life run is saved with the fight pending."""
        if self.permadeath and self.started:
            self.world.vars["_fight"] = list(ids)
            self.save_slot(quiet=True)

    def fight_ended(self):
        self.world.vars.pop("_fight", None)

    def resume_fight(self):
        """A run that was left in the middle of a battle goes straight back into it."""
        w = self.world
        pending = w.vars.pop("_fight", None)
        if not pending:
            return
        here = [c for c in pending if c in self.chars_here() and not w.characters[c].get("defeated")]
        if here:
            self.say("There is no slipping out of a fight. It is still waiting for you.", "combat")
            self.start_fight(here[0])

    def suspend(self):
        """The player left a one-life run without saying so: keep it for next time."""
        if self.permadeath and self.started and not self.over and not self.world.vars.get("_fight"):
            self.save_slot(quiet=True)
