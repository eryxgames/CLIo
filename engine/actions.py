# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Everything the player can do: one ``do_<verb>`` method per command."""
from __future__ import annotations

from . import __author__, __url__, __version__, automap, conditions
from .term import pad_to
from .theme import available_themes, load_theme

NOT_HERE = [
    "You don't see that here.", "No such thing in sight.", "That isn't within reach.",
    "You look around, but can't find that.",
]
UNCLEAR = ["Be more specific.", "You'll have to say what.", "That needs a target."]


class Actions:
    # ------------------------------------------------------------------ #
    # finding things by name
    # ------------------------------------------------------------------ #
    def _names(self, kind, ref):
        w = self.world
        if kind == "exit":
            ex = ref
            names = [ex.get("door_name", "")]
            d = automap.exit_dir(ex)
            if d:
                names += [d, automap.DIR_NAMES.get(d, d)]
            dest = w.scenes.get(ex.get("scene_id"), {})
            if ex.get("scene_id") in w.visited or not ex.get("door_name"):
                names.append(dest.get("name", ""))
            names += list(ex.get("aliases", []) or [])
            return [n.lower() for n in names if n]
        obj = w.items.get(ref) if kind == "item" else w.characters.get(ref)
        if not obj:
            return []
        names = [obj.get("name", ""), str(ref).split("#")[0].replace("_", " ")]
        names += list(obj.get("aliases", []) or [])
        return [n.lower() for n in names if n]

    @staticmethod
    def _score(query, names):
        best = 0
        qwords = query.split()
        for n in names:
            if n == query:
                return 100
            nwords = n.split()
            if all(q in nwords for q in qwords):
                s = 85 if nwords and nwords[-1] == qwords[-1] else 80
            elif all(any(nw.startswith(q) for nw in nwords) for q in qwords):
                s = 70
            elif query in n:
                s = 50
            else:
                s = 0
            best = max(best, s)
        return best

    def candidates(self, pools):
        w = self.world
        sc = w.scene
        out = []
        for pool in pools:
            if pool == "inv":
                out += [("item", i, "inv") for i in w.inventory + w.equipped]
            elif pool == "items":
                out += [("item", i, "items") for i in sc.get("items", [])]
            elif pool == "fixtures":
                out += [("item", i, "fixtures") for i in sc.get("passive_items", [])]
            elif pool == "chars":
                out += [("char", c, "chars") for c in self.chars_here()]
            elif pool == "exits":
                out += [("exit", ex, "exits") for ex in self.visible_exits()]
        return out

    def find(self, name, pools, ask=True):
        """Resolve a typed name to ``(kind, ref, pool)`` or None."""
        name = (name or "").strip().lower()
        if not name:
            return None
        scored = []
        seen = set()
        for kind, ref, pool in self.candidates(pools):
            key = (kind, id(ref) if kind == "exit" else ref)
            if key in seen:
                continue
            seen.add(key)
            names = self._names(kind, ref)
            if kind == "exit" and ref.get("door_name"):
                # a door's own name outranks the name of the room behind it
                own = [n for n in names if n != self.world.scenes.get(ref.get("scene_id"), {}).get("name", "").lower()]
                s = max(self._score(name, own), self._score(name, names) - 10)
            else:
                s = self._score(name, names)
            if s > 0:
                scored.append((s, kind, ref, pool))
        if not scored:
            return None
        top = max(s[0] for s in scored)
        best = [s for s in scored if s[0] == top]
        if len(best) == 1 or not ask:
            return best[0][1:]
        labels = []
        for _s, kind, ref, _pool in best:
            if kind == "item":
                labels.append(self.iname(ref))
            elif kind == "char":
                labels.append(self.cname(ref))
            else:
                labels.append(self.exit_label(ref))
        pick = self.ui.menu(labels, title="Which do you mean?")
        if pick is None:
            return False                      # the player backed out
        return best[pick][1:]

    def _missing(self, what=None):
        self.say(self.world.rng.choice(NOT_HERE), "error")

    def _need(self, text):
        self.say(text, "error")
        return False

    # ------------------------------------------------------------------ #
    # looking
    # ------------------------------------------------------------------ #
    def do_look(self, cmd):
        self.describe_scene(full=True)

    def do_examine(self, cmd):
        w = self.world
        hit = self.find(cmd.obj, ["chars", "items", "fixtures", "inv", "exits"])
        if hit is False:
            return
        if hit is None:
            return self._missing()
        kind, ref, _pool = hit
        if kind == "char":
            ch = w.characters[ref]
            portrait = self.art_lines(ch.get("portrait"), 30, 12)
            parts = []
            if portrait:
                parts += [("art", portrait), ("blank",)]
            parts.append(("text", self.subst(ch.get("description") or "Nothing remarkable."), "description"))
            self.ui.panel(parts, "description", title=ch.get("name"))
            if self.is_hostile(ch):
                st = ch.get("stats", {})
                self.say("It looks dangerous. {hint}(health %s, attack %s, defense %s){/}"
                         % (st.get("health", "?"), st.get("attack", "?"), st.get("defense", "?")), "warning")
            return
        if kind == "exit":
            ex = ref
            text = ex.get("description") or (ex.get("lock_text") if ex.get("locked") else None) \
                or (ex.get("block_text") if ex.get("blocked") else None) or "It leads onward."
            self.say(text, "description")
            return
        it = w.items[ref]
        art = self.art_lines(it.get("art"), None, 12)
        desc = it.get("description") or "Nothing special."
        states = it.get("states") or {}
        cur = states.get(it.get("current_state"), {})
        if cur.get("description"):
            desc = (desc + " " + cur["description"]) if it.get("describe_both", True) and desc != cur["description"] \
                else cur["description"]
        parts = []
        if art:
            parts += [("art", art), ("blank",)]
        parts.append(("text", self.subst(desc), "description"))
        self.ui.panel(parts, "description", title=it.get("name"))
        extras = []
        eff = it.get("effect") or {}
        if eff and (it.get("equippable") or it.get("usable")):
            extras.append(", ".join("%s %+d" % (k.replace("_", " "), v) for k, v in eff.items()))
        if it.get("readable_item") or it.get("text"):
            extras.append("can be read")
        if it.get("equippable"):
            extras.append("equipped" if ref in w.equipped else "can be equipped")
        if extras:
            self.say("(%s)" % "; ".join(extras), "hint")
        if it.get("on_examine"):
            conditions.run(it["on_examine"], self)

    def do_inventory(self, cmd):
        w, ui = self.world, self.ui
        if not w.inventory and not w.equipped:
            self.say("You are carrying nothing.", "system")
            return
        counts = {}
        for i in w.inventory:
            counts[i] = counts.get(i, 0) + 1
        lines = [self.iname(i) + (" x%d" % n if n > 1 else "") for i, n in counts.items()]
        if lines:
            ui.bullets(lines, "default", title="You are carrying:")
        if w.equipped:
            ui.bullets([self.iname(i) for i in w.equipped], "default", title="Equipped:")
        if w.player.get("gold"):
            self.say("%s %d %s" % (ui.g("coin"), w.player["gold"], self.cfg.get("currency", "gold")), "quest")

    def do_stats(self, cmd):
        w, ui = self.world, self.ui
        st, p = w.stats, w.player
        hp, mx = st.get("health", 0), st.get("max_health", 1)
        title = p.get("name", "You")
        if p.get("class_name"):
            title += " the " + p["class_name"]
        if self.cfg.get("rpg"):
            title += " %s level %d" % (ui.g("dot"), p.get("level", 1))
        rows = [["Health", "%s %d/%d" % (ui.bar(hp, mx, 12, "green" if hp > mx / 2 else "red"), hp, mx)]]
        for key in ("attack", "defense", "strength"):
            if key in st:
                rows.append([key.title(), str(st[key])])
        for key, val in st.items():
            if key not in ("health", "max_health", "attack", "defense", "strength", "equipment") \
                    and isinstance(val, (int, float)) and val:
                shown = "%d%%" % round(val * 100) if isinstance(val, float) and val < 1 else str(val)
                rows.append([key.replace("_", " ").title(), shown])
        if self.cfg.get("rpg"):
            rows.append(["Experience", "%d / %d" % (p.get("xp", 0), self.xp_needed(p.get("level", 1)))])
        if p.get("gold") or self.cfg.get("rpg"):
            rows.append([self.cfg.get("currency", "gold").title(), str(p.get("gold", 0))])
        ui.gap()
        ui.rule(title)
        ui.table(rows)
        if w.equipped:
            self.say("Equipped: " + ", ".join(self.iname(i) for i in w.equipped), "default")
        abil = [self.abilities[a].get("name", a) for a in p.get("abilities", []) if a in self.abilities]
        if abil:
            self.say("Skills: " + ", ".join(abil), "default")
        if hp >= mx * 0.75:
            mood = "You are feeling great."
        elif hp >= mx * 0.5:
            mood = "You are slightly injured."
        elif hp >= mx * 0.25:
            mood = "You are moderately injured."
        elif hp >= mx * 0.1:
            mood = "You are heavily injured."
        else:
            mood = "You are critically injured."
        self.say(mood, "hint")

    # ------------------------------------------------------------------ #
    # taking and dropping
    # ------------------------------------------------------------------ #
    def _take(self, iid):
        w = self.world
        sc = w.scene
        it = w.items[iid]
        if it.get("takeable") is False or it.get("fixed"):
            self.say(it.get("take_text") or "You can't take that.", "error")
            return False
        if it.get("take_if") is not None and not conditions.check(it["take_if"], self):
            self.say(it.get("take_text") or "You can't take that yet.", "error")
            return False
        sc["items"].remove(iid)
        w.inventory.append(iid)
        self.audio.sfx("pickup")
        self.say("You take the %s." % self.iname(iid), "item")
        # containers that have been emptied move on to their "empty" state
        for fid in sc.get("passive_items", []):
            fx = w.items.get(fid, {})
            if iid in (fx.get("contents") or []):
                left = [c for c in fx["contents"] if c in sc["items"]]
                cur = (fx.get("states") or {}).get(fx.get("current_state"), {})
                if not left and cur.get("action") == "take" and cur.get("next_state"):
                    fx["current_state"] = cur["next_state"]
        if it.get("on_take"):
            conditions.run(it["on_take"], self)
            it.pop("on_take", None)
        return True

    def do_take(self, cmd):
        w = self.world
        if not cmd.obj:
            return self._need("Take what?")
        if cmd.obj == "all":
            ids = [i for i in list(w.scene.get("items", [])) if w.items.get(i, {}).get("takeable") is not False]
            if not ids:
                return self._need("There is nothing here to take.")
            for i in ids:
                if i in w.scene["items"]:
                    self._take(i)
            return
        hit = self.find(cmd.obj, ["items"])
        if hit is False:
            return False
        if hit is None:
            # maybe it sits in an open container, or is a fixture, or is already carried
            fx = self.find(cmd.obj, ["fixtures"], ask=False)
            if fx:
                it = w.items[fx[1]]
                cur = (it.get("states") or {}).get(it.get("current_state"), {})
                if cur.get("action") == "take" and cur.get("reward") in w.scene.get("items", []):
                    return self._take(cur["reward"])
                return self._need(it.get("take_text") or "The %s stays where it is." % it["name"])
            if self.find(cmd.obj, ["inv"], ask=False):
                return self._need("You already have that.")
            if self.find(cmd.obj, ["chars"], ask=False):
                return self._need("They would object to that.")
            self._missing()
            return False
        return self._take(hit[1])

    def do_drop(self, cmd):
        w = self.world
        if not cmd.obj:
            return self._need("Drop what?")
        hit = self.find(cmd.obj, ["inv"])
        if hit is False:
            return False
        if hit is None:
            return self._need("You aren't carrying that.")
        iid = hit[1]
        if w.items[iid].get("droppable") is False:
            return self._need("Better hold on to that.")
        if iid in w.equipped:
            self.unequip(iid, quiet=True)
        w.inventory.remove(iid)
        w.scene.setdefault("items", []).append(iid)
        self.audio.sfx("drop")
        self.say("You drop the %s." % self.iname(iid), "item")

    # ------------------------------------------------------------------ #
    # state machines: open / close / unlock / custom verbs
    # ------------------------------------------------------------------ #
    def _state(self, it):
        return (it.get("states") or {}).get(it.get("current_state"), {})

    def _advance(self, it, state):
        """Leave ``state``: run its effects and move to the next one."""
        if state.get("text"):
            self.say(state["text"], "default")
        nxt = state.get("next_state")
        if nxt and nxt in (it.get("states") or {}):
            it["current_state"] = nxt
            entered = it["states"][nxt]
            if entered.get("on_enter"):
                conditions.run(entered["on_enter"], self)
        if state.get("do"):
            conditions.run(state["do"], self)

    def _reveal_contents(self, it):
        w = self.world
        found = []
        for c in list(it.get("contents") or []):
            if c in w.items and not it.get("_revealed"):
                w.scene.setdefault("items", []).append(c)
                found.append(c)
        if it.get("contents") is not None:
            it["_revealed"] = True
        if found:
            self.say("Inside you find: %s." % ", ".join(self.iname(c) for c in found), "item")
        return found

    def _try_unlock(self, it, with_item=None, verbose=True):
        """Unlock a fixture/item whose current state wants "unlock". True on success."""
        w, ui = self.world, self.ui
        state = self._state(it)
        req = it.get("unlock_required_item") or it.get("key")
        name = "{item}%s{/}" % it["name"]
        if req == "passcode" or (it.get("passcode") and not req):
            code = ui.ask("Enter the code for the %s (or press Enter to stop):" % it["name"])
            if not code:
                self.say("You leave it alone.", "system")
                return False
            if code.strip().lower() == str(it.get("passcode", "")).strip().lower():
                self.audio.sfx("unlock")
                self.say(it.get("unlock_text") or "The code is accepted. The %s unlocks." % name, "success")
                it["locked"] = False
                self._advance(it, state)
                return True
            self.audio.sfx("error")
            self.say("Wrong code. The %s stays locked." % name, "error")
            return False
        if req and req in w.items:
            if w.has(req) and (with_item in (None, req)):
                self.audio.sfx("unlock")
                self.say(it.get("unlock_text") or "You unlock the %s with the %s." % (name, self.iname(req)), "success")
                if w.items[req].get("consumable"):
                    self.remove_item(req)
                it["locked"] = False
                self._advance(it, state)
                return True
            if verbose:
                self.audio.sfx("locked")
                self.say(it.get("lock_text") or "The %s is locked. You need the right key." % name, "error")
            return False
        # no particular key: any lockpick will do
        picks = [i for i in w.inventory + w.equipped if w.items.get(i, {}).get("lockpick")]
        if with_item and with_item not in picks:
            self.say("That won't open the %s." % name, "error")
            return False
        if picks and it.get("pickable", True):
            self.audio.sfx("unlock")
            self.say(it.get("unlock_text") or "You work the %s into the lock of the %s. It clicks open."
                     % (self.iname(picks[0]), name), "success")
            it["locked"] = False
            self._advance(it, state)
            return True
        if verbose:
            self.audio.sfx("locked")
            self.say(it.get("lock_text") or "The %s is locked. You need something to pick the lock." % name, "error")
        return False

    def _find_object(self, name, pools=("fixtures", "items", "inv", "chars")):
        hit = self.find(name, list(pools))
        return hit

    def do_open(self, cmd):
        w = self.world
        if not cmd.obj:
            return self._need("Open what?")
        hit = self.find(cmd.obj, ["fixtures", "items", "inv", "exits"])
        if hit is False:
            return False
        if hit is None:
            self._missing()
            return False
        kind, ref, _pool = hit
        if kind == "exit":
            return self.attempt_exit(ref)
        it = w.items[ref]
        with_item = None
        if cmd.target:
            wi = self.find(cmd.target, ["inv"])
            if not wi:
                return self._need("You don't have that.")
            with_item = wi[1]
        if self._custom_action("open", ref, it):
            return
        state = self._state(it)
        action = state.get("action")
        if action == "unlock":
            if not self._try_unlock(it, with_item):
                return
            state = self._state(it)
            action = state.get("action")
        if action == "open":
            self._open_container(ref, it)
            return
        if action == "take":
            left = [c for c in (it.get("contents") or []) if c in w.scene.get("items", [])]
            if left:
                self.say("The %s is already open: %s." % (it["name"], ", ".join(self.iname(c) for c in left)),
                         "default")
            else:
                self.say("The %s is already open." % it["name"], "default")
            return
        if state.get("description") and it.get("states"):
            self.say(state["description"], "default")
            return
        self.say("You can't open that.", "error")
        return False

    def _open_container(self, ref, it):
        self.audio.sfx("open")
        self.say("You open the %s." % self.iname(ref), "default")
        self._advance(it, self._state(it))
        self._reveal_contents(it)

    def do_close(self, cmd):
        if not cmd.obj:
            return self._need("Close what?")
        hit = self.find(cmd.obj, ["fixtures", "items", "inv"])
        if not hit:
            if hit is None:
                self._missing()
            return False
        it = self.world.items[hit[1]]
        if self._custom_action("close", hit[1], it):
            return
        self.say("There's no need to close the %s." % it["name"], "default")
        return False

    def do_unlock(self, cmd):
        w = self.world
        if not cmd.obj:
            return self._need("Unlock what?")
        hit = self.find(cmd.obj, ["fixtures", "items", "exits", "inv"])
        if hit is False:
            return False
        if hit is None:
            self._missing()
            return False
        kind, ref, _pool = hit
        with_item = None
        if cmd.target:
            wi = self.find(cmd.target, ["inv"])
            if not wi:
                return self._need("You don't have that.")
            with_item = wi[1]
        if kind == "exit":
            if not ref.get("locked"):
                return self._need("It isn't locked.")
            return self.attempt_exit(ref, go_through=False, with_item=with_item)
        it = w.items[ref]
        if self._custom_action("unlock", ref, it):
            return
        if self._state(it).get("action") != "unlock":
            return self._need("The %s isn't locked." % it["name"])
        if self._try_unlock(it, with_item) and self._state(it).get("action") == "open":
            self._open_container(ref, it)       # no reason to make the player ask twice

    def _custom_action(self, verb, ref, obj, target=None):
        """Game-defined verbs on items and characters. True if one handled it."""
        actions = obj.get("actions") or {}
        spec = actions.get(verb)
        if spec is None and obj.get("states"):
            state = self._state(obj)
            sa = state.get("actions") or {}
            if verb in sa:
                spec = sa[verb]
            elif state.get("action") == verb and verb not in ("open", "unlock", "take", "enter_code"):
                self._advance(obj, state)
                return True
        if spec is None:
            return False
        if isinstance(spec, str):
            self.say(spec, "default")
            return True
        if isinstance(spec, list):
            for option in spec:               # first matching variant wins
                if conditions.check(option.get("if"), self):
                    spec = option
                    break
            else:
                return False
        elif spec.get("if") is not None and not conditions.check(spec["if"], self):
            self.say(spec.get("else") or "Nothing happens.", "default")
            return True
        if spec.get("text"):
            self.say(spec["text"], spec.get("style", "default"))
        if spec.get("sfx"):
            self.audio.sfx(spec["sfx"])
        if spec.get("next_state") and spec["next_state"] in (obj.get("states") or {}):
            obj["current_state"] = spec["next_state"]
        if spec.get("do"):
            conditions.run(spec["do"], self)
        if spec.get("once"):
            (obj.get("actions") or {}).pop(verb, None)
        return True

    def do_custom(self, cmd):
        """A verb the engine does not know: let the things in scope handle it."""
        w = self.world
        verb = cmd.word
        if cmd.obj:
            hit = self.find(cmd.obj, ["fixtures", "items", "inv", "chars"])
            if hit is False:
                return False
            if hit:
                kind, ref, _pool = hit
                obj = w.items[ref] if kind == "item" else w.characters[ref]
                if self._custom_action(verb, ref, obj):
                    return
                self.say("You can't %s the %s." % (verb, obj.get("name", "that")), "error")
                return False
        # a verb without an object may belong to the scene ("pray", "jump", "shout")
        spec = (w.scene.get("actions") or {}).get(verb) or (self.cfg.get("actions") or {}).get(verb)
        if spec is not None:
            holder = {"actions": {verb: spec}}
            if self._custom_action(verb, None, holder):
                if isinstance(spec, dict) and spec.get("once"):
                    (w.scene.get("actions") or {}).pop(verb, None)
                return
        if not cmd.obj:
            for kind, ref, _pool in self.candidates(["fixtures", "items", "chars"]):
                obj = w.items[ref] if kind == "item" else w.characters[ref]
                state = self._state(obj) if kind == "item" else {}
                if verb in (obj.get("actions") or {}) or state.get("action") == verb \
                        or verb in (state.get("actions") or {}):
                    if self._custom_action(verb, ref, obj):
                        return
        self.say(cmd.error or "I don't understand that.", "error")
        return False

    # ------------------------------------------------------------------ #
    # using things
    # ------------------------------------------------------------------ #
    def use_consumable(self, iid):
        """Apply an item's ``effect`` (stat changes). True if it did something."""
        w = self.world
        it = w.items[iid]
        eff = it.get("effect") or {}
        if not eff:
            return False
        st = w.stats
        if set(eff) == {"health"} and eff["health"] > 0 and st.get("health", 0) >= st.get("max_health", 0):
            self.say("You are already at full health.", "system")
            return False
        self.audio.sfx("heal" if eff.get("health", 0) > 0 else "use")
        self.say(it.get("use_text") or "You use the %s." % self.iname(iid), "default")
        for stat, val in eff.items():
            self.change_stat(stat, val)
        if it.get("consumable", True):
            w.inventory.remove(iid)
        return True

    def do_use(self, cmd):
        w = self.world
        if not cmd.obj:
            return self._need("Use what?")
        hit = self.find(cmd.obj, ["inv", "items", "fixtures"])
        if hit is False:
            return False
        if hit is None:
            self._missing()
            return False
        _kind, iid, pool = hit
        it = w.items[iid]
        if cmd.target:
            tgt = self.find(cmd.target, ["fixtures", "items", "chars", "inv", "exits"])
            if tgt is False:
                return False
            if tgt is None:
                self._missing()
                return False
            tkind, tref, _tp = tgt
            if tkind == "exit":
                if tref.get("locked"):
                    return self.attempt_exit(tref, go_through=False, with_item=iid)
                return self._need("That doesn't need it.")
            if tkind == "char":
                return self._give(iid, tref)
            return self._use_on(iid, tref)
        if pool != "inv" and not it.get("states") and not it.get("on_use") and not it.get("use_here"):
            if it.get("takeable") is not False and iid in w.scene.get("items", []):
                return self._need("You'd need to pick it up first.")
        if self._custom_action("use", iid, it):
            return
        if it.get("on_use"):
            spec = it["on_use"]
            if isinstance(spec, dict) and ("do" in spec or "text" in spec or "if" in spec):
                if spec.get("if") is not None and not conditions.check(spec["if"], self):
                    self.say(spec.get("else") or "Nothing happens.", "default")
                    return
                self.audio.sfx(spec.get("sfx", "use"))
                if spec.get("text"):
                    self.say(spec["text"], "default")
                conditions.run(spec.get("do"), self)
                if spec.get("consume") and iid in w.inventory:
                    w.inventory.remove(iid)
            else:
                self.audio.sfx("use")
                conditions.run(spec, self)
            return
        if it.get("states"):
            state = self._state(it)
            act = state.get("action")
            if act == "open" or act == "unlock":
                return self.do_open(cmd)
            if act == "enter_code":
                return self._enter_code(it, state)
            if act and act not in ("take",):
                self._advance(it, state)
                return
        if it.get("usable") and it.get("effect") and pool == "inv":
            return self.use_consumable(iid)
        if it.get("equippable") and pool == "inv":
            return self.equip(iid)
        if it.get("readable_item") or it.get("text"):
            return self._read(iid)
        self.say(it.get("use_text") or "You can't think of a way to use the %s on its own." % it["name"], "default")
        return False

    def _enter_code(self, it, state):
        code = self.ui.ask("Enter the access code (or press Enter to stop):")
        if not code:
            return False
        if code.strip().lower() == str(it.get("passcode", it.get("access_code", ""))).lower():
            self.audio.sfx("computer")
            self.say(it.get("unlock_text") or "Access granted.", "success")
            self._advance(it, state)
            return True
        self.audio.sfx("error")
        self.say("Access denied.", "error")
        return True

    def _use_on(self, iid, tid):
        """``use X on Y`` for two items."""
        w = self.world
        it, tgt = w.items[iid], w.items[tid]
        spec = (it.get("use_on") or {}).get(tid) or (tgt.get("use_with") or {}).get(iid)
        if spec is None:
            # unlocking with a key / lockpick
            if self._state(tgt).get("action") == "unlock":
                return self._try_unlock(tgt, with_item=iid)
            # repairing with a tool
            if tgt.get("repairable") and tgt.get("repair_item") == iid:
                return self._repair(tid)
            if it.get("repairable") and it.get("repair_item") == tid:
                return self._repair(iid)
            # combining
            if self._combine(iid, tid, quiet=True):
                return True
            self.say("Using the %s on the %s does nothing." % (it["name"], tgt["name"]), "default")
            return False
        if isinstance(spec, str):
            self.say(spec, "default")
            return True
        if spec.get("if") is not None and not conditions.check(spec["if"], self):
            self.say(spec.get("else") or "That doesn't work - not yet, anyway.", "default")
            return True
        self.audio.sfx(spec.get("sfx", "use"))
        if spec.get("text"):
            self.say(spec["text"], spec.get("style", "default"))
        if spec.get("consume", False):
            self.remove_item(iid)
        if spec.get("next_state") and spec["next_state"] in (tgt.get("states") or {}):
            tgt["current_state"] = spec["next_state"]
        conditions.run(spec.get("do"), self)
        return True

    def _read(self, iid):
        it = self.world.items[iid]
        text = it.get("readable_item") or it.get("text")
        if not text:
            self.say("There is nothing to read on the %s." % it["name"], "default")
            return False
        self.audio.sfx("read")
        self.ui.say(self.subst(text), "reading", title=it.get("name"))
        if it.get("on_read"):
            conditions.run(it["on_read"], self)
            if it.get("on_read_once", True):
                it.pop("on_read", None)
        return True

    def do_read(self, cmd):
        if not cmd.obj:
            return self._need("Read what?")
        hit = self.find(cmd.obj, ["inv", "items", "fixtures"])
        if hit is False:
            return False
        if hit is None:
            self._missing()
            return False
        return self._read(hit[1])

    # ------------------------------------------------------------------ #
    # equipment
    # ------------------------------------------------------------------ #
    def equip(self, iid, quiet=False):
        w = self.world
        it = w.items[iid]
        if iid not in w.inventory:
            return self._need("You aren't carrying that.")
        if not it.get("equippable"):
            return self._need("The %s can't be equipped." % it["name"])
        slot = it.get("slot")
        if slot:
            for other in list(w.equipped):
                if w.items[other].get("slot") == slot:
                    self.unequip(other, quiet=True)
        w.inventory.remove(iid)
        w.equipped.append(iid)
        for stat, val in (it.get("effect") or {}).items():
            if stat != "health":
                w.stats[stat] = w.stats.get(stat, 0) + val
        if not quiet:
            self.audio.sfx("use")
            eff = ", ".join("%s %+d" % (k.replace("_", " "), v) for k, v in (it.get("effect") or {}).items()
                            if k != "health")
            self.say("You equip the %s.%s" % (self.iname(iid), (" {hint}(%s){/}" % eff) if eff else ""), "default")
        return True

    def unequip(self, iid, quiet=False):
        w = self.world
        if iid not in w.equipped:
            return self._need("That isn't equipped.")
        it = w.items[iid]
        w.equipped.remove(iid)
        w.inventory.append(iid)
        for stat, val in (it.get("effect") or {}).items():
            if stat != "health":
                w.stats[stat] = w.stats.get(stat, 0) - val
        w.stats["health"] = min(w.stats.get("health", 0), w.stats.get("max_health", 1))
        if not quiet:
            self.say("You put away the %s." % self.iname(iid), "default")
        return True

    def do_equip(self, cmd):
        if not cmd.obj:
            return self._need("Equip what?")
        hit = self.find(cmd.obj, ["inv"])
        if hit is False:
            return False
        if hit is None:
            if self.find(cmd.obj, ["items"], ask=False):
                return self._need("Pick it up first.")
            return self._need("You aren't carrying that.")
        if hit[1] in self.world.equipped:
            return self._need("It is already equipped.")
        return self.equip(hit[1])

    def do_unequip(self, cmd):
        if not cmd.obj:
            return self._need("Unequip what?")
        w = self.world
        saved = list(w.inventory)
        w.player["inventory"] = []                  # search equipped items only
        try:
            hit = self.find(cmd.obj, ["inv"])
        finally:
            w.player["inventory"] = saved
        if not hit:
            return self._need("That isn't equipped.")
        return self.unequip(hit[1])

    # ------------------------------------------------------------------ #
    # making things
    # ------------------------------------------------------------------ #
    def _combine(self, a, b, quiet=False):
        w = self.world
        for rid, result in w.items.items():
            comps = result.get("components")
            if comps and len(comps) == 2 and sorted(comps) == sorted([a, b]):
                if result.get("combine_if") is not None and not conditions.check(result["combine_if"], self):
                    self.say(result.get("combine_fail") or "That almost works. Something is missing.", "default")
                    return True
                for c in (a, b):
                    if not w.items[c].get("tool"):
                        self.remove_item(c)
                self.audio.sfx("craft")
                self.say(result.get("combine_text") or "You combine the %s and the %s into: %s."
                         % (self.iname(a), self.iname(b), self.iname(rid)), "success")
                w.inventory.append(rid)
                if result.get("on_craft"):
                    conditions.run(result["on_craft"], self)
                return True
        if not quiet:
            self.say("Those don't fit together.", "default")
        return False

    def do_combine(self, cmd):
        if not cmd.obj or not cmd.target:
            return self._need("Combine what with what? Try: combine wire with battery")
        a = self.find(cmd.obj, ["inv"])
        b = self.find(cmd.target, ["inv"])
        if a is False or b is False:
            return False
        if not a or not b:
            return self._need("You need to be carrying both things.")
        if a[1] == b[1] and self.world.inventory.count(a[1]) < 2:
            return self._need("You only have one of those.")
        return self._combine(a[1], b[1])

    def do_craft(self, cmd):
        w = self.world
        if not cmd.obj:
            recipes = [r for r in w.items.values() if r.get("components") and r.get("craft_listed", True)
                       and any(c in w.inventory + w.equipped for c in r["components"])]
            if not recipes:
                return self._need("Craft what? You don't have the makings of anything.")
            self.ui.bullets(["%s {hint}%s %s{/}" % (self.iname(r["id"]), self.ui.g("dot"),
                                                    " + ".join(self.item(c)["name"] for c in r["components"]))
                             for r in recipes], title="You could make:")
            return False
        name = cmd.obj.lower()
        for rid, r in w.items.items():
            if r.get("components") and self._score(name, self._names("item", rid)):
                missing = [c for c in r["components"] if not w.has(c)]
                if missing:
                    return self._need("To make the %s you still need: %s."
                                      % (r["name"], ", ".join(self.item(c)["name"] for c in missing)))
                if len(r["components"]) == 1:
                    return self._repair(r["components"][0])
                if len(r["components"]) == 2:
                    return self._combine(r["components"][0], r["components"][1])
                for c in r["components"]:
                    if not w.items[c].get("tool"):
                        self.remove_item(c)
                self.audio.sfx("craft")
                w.inventory.append(rid)
                self.say("You put together: %s." % self.iname(rid), "success")
                return True
        return self._need("You don't know how to make that.")

    def _repair(self, iid, tool=None):
        w = self.world
        it = w.items[iid]
        if not it.get("repairable"):
            return self._need("The %s doesn't need repairing." % it["name"])
        need = it.get("repair_item")
        if need and not w.has(need):
            return self._need("You need a %s to repair the %s." % (self.item(need)["name"], it["name"]))
        if tool and need and tool != need:
            return self._need("That is the wrong tool for the job.")
        fixed = it.get("repaired_item")
        if not fixed:
            for rid, r in w.items.items():
                if r.get("components") == [iid]:
                    fixed = rid
                    break
        if not fixed and iid.startswith("broken_"):         # naming convention: broken_x -> fixed_x
            for prefix in ("fixed_", "repaired_", "working_"):
                if prefix + iid[len("broken_"):] in w.items:
                    fixed = prefix + iid[len("broken_"):]
                    break
        if not fixed or fixed not in w.items:
            return self._need("You can't work out how to fix the %s." % it["name"])
        self.remove_item(iid)
        if need and (w.items[need].get("consumable") or it.get("repair_consumes")):
            self.remove_item(need)
        w.inventory.append(fixed)
        self.audio.sfx("craft")
        self.say(it.get("repair_text") or "You repair the %s%s. You now have: %s."
                 % (it["name"], (" with the " + self.item(need)["name"]) if need else "", self.iname(fixed)),
                 "success")
        if it.get("on_repair"):
            conditions.run(it["on_repair"], self)
        return True

    def do_repair(self, cmd):
        if not cmd.obj:
            return self._need("Repair what?")
        hit = self.find(cmd.obj, ["inv", "fixtures", "items"])
        if hit is False:
            return False
        if hit is None:
            self._missing()
            return False
        iid = hit[1]
        tool = None
        if cmd.target:
            t = self.find(cmd.target, ["inv"])
            if not t:
                return self._need("You don't have that.")
            tool = t[1]
        it = self.world.items[iid]
        if self._custom_action("repair", iid, it):
            return
        if tool and ((it.get("use_with") or {}).get(tool) or (self.world.items[tool].get("use_on") or {}).get(iid)):
            return self._use_on(tool, iid)
        if hit[2] != "inv":
            return self._need(it.get("repair_hint") or "You'd need the right part or tool. Try: use [item] on %s"
                              % it["name"].lower())
        return self._repair(iid, tool)

    # ------------------------------------------------------------------ #
    # characters
    # ------------------------------------------------------------------ #
    def do_talk(self, cmd):
        w = self.world
        chars = self.chars_here()
        if not cmd.obj:
            if len(chars) == 1:
                hit = ("char", chars[0], "chars")
            elif not chars:
                return self._need("There is nobody here to talk to.")
            else:
                return self._need("Talk to whom?")
        else:
            hit = self.find(cmd.obj, ["chars"])
        if hit is False:
            return False
        if hit is None:
            return self._need("There is nobody like that here.")
        ch = w.characters[hit[1]]
        if ch.get("ambush") and self.is_hostile(ch):
            self.say("%s is in no mood to talk." % self.cname(hit[1]), "warning")
            self.start_fight(hit[1])
            return
        self.talk_to(hit[1])

    def _give(self, iid, cid):
        w = self.world
        it, ch = w.items[iid], w.characters[cid]
        key = ch.get("template") or cid
        if iid not in w.inventory and iid in w.equipped:
            self.unequip(iid, quiet=True)
        inter = (ch.get("item_interactions") or {}).get(iid) or (ch.get("gives") or {}).get(iid)
        if inter:
            if inter.get("if") is not None and not conditions.check(inter["if"], self):
                self.dialogue_box(ch["name"], inter.get("else") or "Not now.")
                return True
            kind = inter.get("type", "")
            text = inter.get("response") or inter.get("text")
            if text:
                self.audio.voice(ch.get("voice", {}).get("pitch", 220), ch.get("voice", {}).get("wave", "square"), 3)
                self.dialogue_box(ch["name"], text)
            if inter.get("sfx"):
                self.audio.sfx(inter["sfx"])
            consume = inter.get("consume_item", inter.get("consume", kind in ("trade", "replicate")))
            if consume:
                self.remove_item(iid)
            for flag_key in ("story_flag", "quest_flag", "flag"):
                if inter.get(flag_key):
                    w.flags[inter[flag_key]] = True
            if inter.get("reward_item"):
                self.give_item(inter["reward_item"])
            if kind == "passage" and inter.get("unlock_scene") is not None:
                target = inter["unlock_scene"]
                exits = w.scene.get("exits", [])
                if isinstance(target, int) and 0 <= target < len(exits):
                    exits[target]["blocked"] = exits[target]["locked"] = False
                else:
                    conditions.run({"unlock": target}, self)
            if inter.get("do"):
                conditions.run(inter["do"], self)
            return True
        # crafting characters collect ingredients (legacy "npc_craftable")
        wanted = {}
        for rid, r in w.items.items():
            nc = r.get("npc_craftable")
            if nc and nc.get("crafter") in (cid, key):
                wanted[rid] = nc
        needed = set(i for nc in wanted.values() for i in nc.get("required_items", []))
        if iid in needed:
            pile = w.crafting.setdefault(key, [])
            pile.append(iid)
            self.remove_item(iid)
            self.say("%s takes the %s." % (self.cname(cid), self.iname(iid)), "default")
            for rid, nc in wanted.items():
                req = list(nc.get("required_items", []))
                if all(r in pile for r in req):
                    for r in req:
                        pile.remove(r)
                    self.audio.sfx("craft")
                    self.say(nc.get("success_message") or "%s gets to work." % ch["name"], "success")
                    if nc.get("dialogue_response"):
                        self.dialogue_box(ch["name"], nc["dialogue_response"])
                    self.give_item(rid)
                    return True
            missing = set()
            for nc in wanted.values():
                if iid in nc.get("required_items", []):
                    missing |= set(r for r in nc["required_items"] if r not in pile)
            if missing:
                self.say("%s still needs: %s." % (self.cname(cid), ", ".join(self.item(m)["name"] for m in sorted(missing))),
                         "default")
            return True
        self.say(ch.get("refuse_text") or "%s has no use for the %s." % (self.cname(cid), it["name"]), "default")
        return False

    def do_give(self, cmd):
        if not cmd.obj:
            return self._need("Give what, and to whom?")
        chars = self.chars_here()
        item = self.find(cmd.obj, ["inv"])
        if item is False:
            return False
        if item is None:
            # "give robot the cells" - try the words the other way round
            words = cmd.obj.split()
            for cut in range(1, len(words)):
                who = self.find(" ".join(words[:cut]), ["chars"], ask=False)
                what = self.find(" ".join(words[cut:]), ["inv"], ask=False)
                if who and what:
                    return self._give(what[1], who[1])
            return self._need("You aren't carrying that.")
        if not cmd.target:
            if len(chars) == 1:
                return self._give(item[1], chars[0])
            return self._need("Give it to whom?")
        who = self.find(cmd.target, ["chars"])
        if who is False:
            return False
        if who is None:
            fx = self.find(cmd.target, ["fixtures", "items"], ask=False)
            if fx:
                return self._use_on(item[1], fx[1])
            return self._need("There is nobody like that here.")
        return self._give(item[1], who[1])

    def do_fight(self, cmd):
        w = self.world
        chars = self.chars_here()
        if not cmd.obj:
            hostile = [c for c in chars if self.is_hostile(w.characters[c])]
            if len(hostile) == 1:
                hit = ("char", hostile[0], "chars")
            else:
                return self._need("Fight whom?")
        else:
            hit = self.find(cmd.obj, ["chars"])
        if hit is False:
            return False
        if hit is None:
            if self.find(cmd.obj, ["fixtures", "items", "inv"], ask=False):
                return self._need("Violence won't solve that one.")
            return self._need("There is nobody like that here.")
        ch = w.characters[hit[1]]
        if ch.get("type") == "friendly" or ch.get("invulnerable") or not ch.get("stats"):
            self.say(ch.get("no_fight_text") or "%s is no enemy of yours." % self.cname(hit[1]), "default")
            return False
        if ch.get("type") == "neutral" and self.term.interactive:
            if not self.ui.confirm("Attack %s? They have done you no harm." % ch["name"]):
                return False
        self.start_fight(hit[1])

    # ------------------------------------------------------------------ #
    # movement
    # ------------------------------------------------------------------ #
    def attempt_exit(self, ex, go_through=True, with_item=None):
        """Try to pass (or just unlock) an exit. Legacy lock/block rules apply."""
        w, ui = self.world, self.ui
        guard = self.exit_guard(ex)
        if guard:
            self.audio.sfx("locked")
            self.say(ex.get("guard_text") or ex.get("block_text")
                     or "%s blocks the way." % self.cname(guard), "error")
            return False
        if ex.get("blocked"):
            cond = ex.get("required_condition")
            stat = ex.get("required_stat")
            ok = False
            if ex.get("unblock_if") is not None:
                ok = conditions.check(ex["unblock_if"], self)
            elif cond and w.flags.get(cond):
                ok = True
            elif stat and w.stats.get(stat, 0) >= ex.get("required_value", 0):
                ok = True
            if not ok:
                self.audio.sfx("locked")
                self.say(ex.get("block_text") or "The way is blocked.", "error")
                return False
            self.say(ex.get("unblock_text") or "The way is clear now.", "success")
            ex["blocked"] = False
        if ex.get("locked"):
            req = ex.get("required_item")
            if req == "passcode" or (ex.get("passcode") and not req):
                code = ui.ask("Enter the passcode (or press Enter to stop):")
                if not code:
                    self.say("You step back from the keypad.", "system")
                    return False
                if code.strip().lower() != str(ex.get("passcode", "")).strip().lower():
                    self.audio.sfx("error")
                    self.say("Incorrect passcode. It stays locked.", "error")
                    return True
                self.audio.sfx("unlock")
                self.say(ex.get("unlock_text") or "The passcode is accepted.", "success")
                ex["locked"] = False
            elif req and w.has(req) and with_item in (None, req):
                self.audio.sfx("unlock")
                self.say(ex.get("unlock_text") or "You unlock it with the %s." % self.iname(req), "success")
                if w.items.get(req, {}).get("consumable"):
                    self.remove_item(req)
                ex["locked"] = False
            elif not req and ex.get("pickable") and any(
                    w.items.get(i, {}).get("lockpick") for i in w.inventory + w.equipped):
                self.audio.sfx("unlock")
                self.say(ex.get("unlock_text") or "You pick the lock.", "success")
                ex["locked"] = False
            else:
                self.audio.sfx("locked")
                self.say(ex.get("lock_text") or "It is locked.", "error")
                return False
            # unlock the same door from the other side
            for back in w.scenes.get(ex.get("scene_id"), {}).get("exits", []):
                if back.get("scene_id") == w.scene_id and back.get("locked") \
                        and back.get("required_item") == ex.get("required_item"):
                    back["locked"] = False
            if ex.get("on_unlock"):
                conditions.run(ex["on_unlock"], self)
        if not go_through:
            return True
        if ex.get("leave_if") is not None and not conditions.check(ex["leave_if"], self):
            self.say(ex.get("leave_text") or "You can't go that way yet.", "error")
            return False
        if ex.get("do"):
            conditions.run(ex["do"], self)
            if self.over:
                return True
        return self.enter_scene(ex["scene_id"])

    def do_go(self, cmd):
        w = self.world
        exits = self.visible_exits()
        if not exits:
            return self._need("There is no way out of here.")
        self.positions()                        # make sure auto-directions exist
        if not cmd.obj:
            if len(exits) == 1 and not self.data.legacy:
                return self.attempt_exit(exits[0])
            pick = self.ui.menu([self.exit_label(ex) for ex in exits], title="Where to?", cancel_label="Stay here")
            if pick is None:
                self.say("You stay where you are.", "system")
                return False
            return self.attempt_exit(exits[pick])
        d = automap.norm_dir(cmd.obj)
        if d:
            for ex in exits:
                if automap.exit_dir(ex) == d:
                    return self.attempt_exit(ex)
            if cmd.obj in ("back",) and w.prev_scene:
                for ex in exits:
                    if ex.get("scene_id") == w.prev_scene:
                        return self.attempt_exit(ex)
            return self._need("You can't go %s from here." % automap.DIR_NAMES.get(d, cmd.obj))
        if cmd.obj in ("back", "return") and w.prev_scene:
            for ex in exits:
                if ex.get("scene_id") == w.prev_scene:
                    return self.attempt_exit(ex)
        hit = self.find(cmd.obj, ["exits"])
        if hit is False:
            return False
        if hit is None:
            if cmd.obj.isdigit() and 1 <= int(cmd.obj) <= len(exits):
                return self.attempt_exit(exits[int(cmd.obj) - 1])
            # "enter pod", "climb ladder": a thing rather than an exit
            thing = self.find(cmd.obj, ["fixtures", "items", "chars"], ask=False)
            if thing:
                kind, ref, _pool = thing
                obj = w.items[ref] if kind == "item" else w.characters[ref]
                for verb in (cmd.word.split()[0], "enter", "use"):
                    if self._custom_action(verb, ref, obj):
                        return
                return self._need("You can't go into that.")
            return self._need("You can't see a way to '%s' from here." % cmd.obj)
        return self.attempt_exit(hit[1])

    def do_wait(self, cmd):
        sc = self.world.scene
        events = sc.get("random_events") or []
        self.say("Time passes.", "system")
        if events:
            self.say(self.world.rng.choice(events), "ambient")

    # ------------------------------------------------------------------ #
    # trade
    # ------------------------------------------------------------------ #
    def _shopkeeper(self, name=None):
        w = self.world
        for cid in self.chars_here():
            ch = w.characters[cid]
            if ch.get("shop") and (not name or self._score(name, self._names("char", cid))):
                return cid
        return None

    def open_shop(self, cid=None):
        w, ui = self.world, self.ui
        cid = self.resolve_char(cid) if cid else None
        if not cid or not w.characters.get(cid, {}).get("shop") or cid not in self.chars_here():
            cid = self._shopkeeper()
        if not cid:
            return self._need("There is nobody here to trade with.")
        ch = w.characters[cid]
        shop = ch["shop"]
        rate = float(shop.get("buy_rate", 0.5))
        cur = self.cfg.get("currency", "gold")
        if shop.get("greeting"):
            self.dialogue_box(ch["name"], shop["greeting"])
        while not self.over:
            stock = [i for i in shop.get("sells", []) if i in w.items]
            mine = [i for i in dict.fromkeys(w.inventory) if w.items[i].get("value", 0) > 0
                    and not w.items[i].get("quest_item")]
            self.say("You have %s %d %s." % (ui.g("coin"), w.player.get("gold", 0), cur), "quest")
            options = ["Buy", "Sell"]
            pick = ui.menu(options, cancel_label="Leave")
            if pick is None:
                break
            if pick == 0:
                if not stock:
                    self.say("Nothing left to buy.", "system")
                    continue
                labels = []
                for i in stock:
                    note = self._short_desc(i)
                    labels.append("%s {hint}%s{/} {quest}%d{/}%s" % (
                        self.iname(i), ui.g("dot"), self._price(i, shop),
                        (" {hint}%s %s{/}" % (ui.g("dot"), note)) if note else ""))
                n = ui.menu(labels, title="For sale:", cancel_label="Back")
                if n is None:
                    continue
                iid = stock[n]
                price = self._price(iid, shop)
                if w.player.get("gold", 0) < price:
                    self.audio.sfx("error")
                    self.say("You can't afford that.", "error")
                    continue
                w.player["gold"] -= price
                w.inventory.append(iid)
                if not shop.get("unlimited", True) or w.items[iid].get("unique"):
                    shop["sells"].remove(iid)
                self.audio.sfx("coin")
                self.say("You buy the %s for %d %s." % (self.iname(iid), price, cur), "success")
            else:
                if not mine:
                    self.say("You have nothing worth selling.", "system")
                    continue
                labels = ["%s {hint}%s{/} {quest}%d{/}" % (self.iname(i), ui.g("dot"),
                                                          max(1, int(w.items[i]["value"] * rate))) for i in mine]
                n = ui.menu(labels, title="Sell what?", cancel_label="Back")
                if n is None:
                    continue
                iid = mine[n]
                price = max(1, int(w.items[iid]["value"] * rate))
                w.inventory.remove(iid)
                w.player["gold"] = w.player.get("gold", 0) + price
                self.audio.sfx("coin")
                self.say("You sell the %s for %d %s." % (self.iname(iid), price, cur), "success")
        if shop.get("farewell"):
            self.dialogue_box(ch["name"], shop["farewell"])
        return True

    def _price(self, iid, shop):
        return max(1, int(round(self.world.items[iid].get("value", 1) * float(shop.get("sell_rate", 1.0)))))

    def _short_desc(self, iid):
        it = self.world.items[iid]
        eff = it.get("effect") or {}
        if eff:
            return ", ".join("%s %+d" % (k.replace("_", " "), v) for k, v in eff.items())
        return it.get("short") or ""

    def do_shop(self, cmd):
        return self.open_shop()

    def do_buy(self, cmd):
        return self.open_shop()

    def do_sell(self, cmd):
        return self.open_shop()

    # ------------------------------------------------------------------ #
    # information
    # ------------------------------------------------------------------ #
    def do_map(self, cmd):
        w, ui = self.world, self.ui
        if self.cfg.get("map") is False:
            return self._need("You have no map of this place.")
        pos = self.positions()
        lines, legend = automap.render(ui, w.scenes, pos, w.scene_id, set(w.visited),
                                       max_width=ui.width - 6, max_height=min(21, max(7, self.term.rows - 10)),
                                       hidden_fn=lambda sid, ex: self.exit_hidden(ex))
        if not lines:
            return self._need("There is nothing to map yet.")
        self.audio.sfx("map")
        area = w.scene.get("area") or self.cfg.get("map_title") or "Map"
        parts = [("art", lines), ("blank",), ("text", "  ".join(legend), "hint")]
        frame = ui.theme.style("description")["frame"]
        ui.panel(parts, "system", title="%s %s %s" % (area, ui.g("dot"), w.scene.get("name", "")),
                 frame=frame if frame != "NONE" else "SINGLE", effect="none")

    def do_journal(self, cmd):
        self.quests.show()

    def do_hint(self, cmd):
        w = self.world
        hint = w.scene.get("hint")
        if isinstance(hint, list):
            chosen = None
            for h in hint:
                if isinstance(h, str):
                    chosen = h
                    break
                if conditions.check(h.get("if"), self):
                    chosen = h.get("text")
                    break
            hint = chosen
        if not hint:
            hint = self.cfg.get("default_hint")
        if not hint:
            self.say("No hint comes to mind here.", "system")
            return
        left = self.data.max_hints - w.hints_used
        if left <= 0:
            self.say("You have used all your hints.", "error")
            return
        w.hints_used += 1
        self.say("%s {hint}(%d left){/}" % (hint, left - 1), "hint", title="Hint")

    def do_help(self, cmd):
        ui = self.ui
        topic = (cmd.obj or "").strip().lower()
        topics = {
            "move": ("Getting around", [
                "{key}go north{/}, or just {key}n{/} / {key}s{/} / {key}e{/} / {key}w{/} / {key}up{/} / {key}down{/}",
                "{key}go [door name]{/} to use a named exit; {key}exit{/} lists the ways out",
                "{key}map{/} draws what you have explored", "{key}back{/} returns the way you came"]),
            "items": ("Things", [
                "{key}take [item]{/}, {key}take all{/}, {key}drop [item]{/}, {key}inventory{/} ({key}i{/})",
                "{key}examine [thing]{/} ({key}x{/}), {key}read [item]{/}",
                "{key}open{/} / {key}unlock [thing]{/} ({key}unlock door with key{/})",
                "{key}use [item]{/}, {key}use [item] on [thing]{/}",
                "{key}equip{/} / {key}unequip [item]{/}",
                "{key}combine [a] with [b]{/}, {key}repair [item]{/}, {key}craft{/} lists what you could make"]),
            "people": ("People and creatures", [
                "{key}talk to [name]{/}; pick replies by number",
                "{key}give [item] to [name]{/}", "{key}fight [name]{/}", "{key}trade{/} with a merchant"]),
            "fight": ("Combat", [
                "Each round your enemy shows what it is about to do.",
                "{key}Strike{/} is reliable. {key}Heavy{/} hits hard but can miss and leaves you open.",
                "{key}Guard{/} halves damage and counters a charged blow; it also builds focus.",
                "{key}Focus{/} skips your attack so the next one is a sure critical.",
                "Skills cost focus. {key}Item{/} uses something from your pack. {key}Flee{/} may get you out."]),
            "game": ("The game itself", [
                "{key}save{/} / {key}load{/} (add a name for extra slots: {key}save before-boss{/})",
                "{key}journal{/} ({key}j{/}) shows quests; {key}stats{/} shows your condition; {key}hint{/}",
                "{key}style [name]{/} changes the look; {key}sound{/}, {key}music off{/}, {key}volume 40{/}",
                "{key}speed fast{/}|{key}normal{/}|{key}slow{/}|{key}off{/} sets text animation; {key}art off{/}",
                "{key}again{/} ({key}g{/}) repeats; {key}quit{/} leaves. Ctrl-C skips an animation."]),
        }
        alias = {"go": "move", "movement": "move", "walk": "move", "map": "move", "look": "items",
                 "inventory": "items", "take": "items", "use": "items", "combine": "items", "talk": "people",
                 "give": "people", "combat": "fight", "battle": "fight", "attack": "fight", "save": "game",
                 "sound": "game", "style": "game", "settings": "game", "trade": "people"}
        topic = alias.get(topic, topic)
        if topic in topics:
            title, lines = topics[topic]
            ui.heading(title.upper())
            ui.bullets(lines)
            return
        ui.heading("HELP")
        for key in ("move", "items", "people", "game"):
            title, lines = topics[key]
            ui.bullets(lines[:3] if ui.narrow else lines, title=title)
        extra = self.cfg.get("help")
        if extra:
            self.say(extra, "hint")
        self.say("More: {key}help move{/}, {key}help items{/}, {key}help people{/}, {key}help fight{/}, "
                 "{key}help game{/}", "hint")

    def do_about(self, cmd):
        cfg = self.cfg
        lines = ["{key}%s{/}%s" % (self.data.title, (" %s" % cfg["version"]) if cfg.get("version") else "")]
        if cfg.get("author"):
            lines.append("by %s%s" % (cfg["author"], (" {hint}%s %s{/}" % (self.ui.g("dot"), cfg["website"]))
                                      if cfg.get("website") else ""))
        if cfg.get("about"):
            lines.append(cfg["about"])
        if cfg.get("license"):
            lines.append("{hint}Licence: %s{/}" % cfg["license"])
        lines.append("{hint}Made with CLIo %s - the stylish command-line game engine.{/}" % __version__)
        lines.append("{hint}CLIo by %s %s %s{/}" % (__author__, self.ui.g("dot"), __url__.split("//")[-1]))
        for l in lines:
            self.say(l, "default")

    # ------------------------------------------------------------------ #
    # settings
    # ------------------------------------------------------------------ #
    def do_style(self, cmd):
        names = available_themes(self.data.dir)
        want = (cmd.obj or "").strip().lower()
        cur = self.ui.theme.name
        if want in ("list", "?"):
            for n in names:
                t = load_theme(n, self.data.dir)
                self.say("%s{key}%s{/} {hint}%s{/}" % ("> " if n == cur else "  ", n, t.description), "default")
            return
        if not want or want == "next":
            want = names[(names.index(cur) + 1) % len(names)] if cur in names else names[0]
        if want not in names:
            near = [n for n in names if n.startswith(want)]
            if len(near) != 1:
                self.say("No style called '%s'. Available: %s" % (want, ", ".join(names)), "error")
                return
            want = near[0]
        self.ui.apply_theme(load_theme(want, self.data.dir))
        self.audio.sfx("select")
        self.say("Style: {key}%s{/}. {hint}%s{/}" % (want, self.ui.theme.description), "success")

    def do_sound(self, cmd):
        a = self.audio
        words = (cmd.obj or "").lower().split()

        def flag(default=None):
            for wd in words:
                if wd in ("on", "yes", "1", "enable"):
                    return True
                if wd in ("off", "no", "0", "disable", "mute"):
                    return False
            return default

        def number():
            for wd in words:
                wd = wd.rstrip("%")
                if wd.isdigit():
                    return max(0, min(100, int(wd))) / 100.0
            return None

        if not words or words == ["status"]:
            for l in a.status():
                self.say(l, "system")
            self.say("{hint}Try: music off, sfx off, volume 50, sound test{/}", "hint")
            return
        if "test" in words:
            ok = a.sfx("quest_done")
            self.say("Played a test sound." if ok else "No sound could be played. %s" % a.note, "system")
            return
        head = words[0]
        if head == "mute":
            a.set_music(False)
            a.set_sfx(False)
            self.say("Sound muted.", "system")
        elif head == "unmute":
            a.set_music(True)
            a.set_sfx(True)
            self.resume_music()
            self.say("Sound on.", "system")
        elif head == "volume":
            v = number()
            if v is None:
                return self._need("Volume takes a number from 0 to 100.")
            if "music" in words:
                a.set_volume(music=v)
            elif "sfx" in words or "effects" in words:
                a.set_volume(sfx=v)
            else:
                a.set_volume(music=v * 0.75, sfx=v)
            self.say("Volume set to %d%%." % round(v * 100), "system")
        elif head == "music":
            v = number()
            if v is not None:
                a.set_volume(music=v)
                self.say("Music volume %d%%." % round(v * 100), "system")
            else:
                on = flag(not a.music_on)
                a.set_music(on)
                if on:
                    self.resume_music()
                self.say("Music %s." % ("on" if on else "off"), "system")
        elif head in ("sfx", "effects"):
            v = number()
            if v is not None:
                a.set_volume(sfx=v)
                self.say("Effects volume %d%%." % round(v * 100), "system")
            else:
                on = flag(not a.sfx_on)
                a.set_sfx(on)
                self.say("Sound effects %s." % ("on" if on else "off"), "system")
        else:
            on = flag()
            if on is None:
                return self._need("Try: sound on, sound off, music off, sfx off, volume 50, sound test")
            a.set_music(on)
            a.set_sfx(on)
            if on:
                self.resume_music()
            self.say("Sound %s." % ("on" if on else "off"), "system")

    def do_speed(self, cmd):
        table = {"off": 0.0, "instant": 0.0, "none": 0.0, "fast": 0.4, "normal": 1.0, "slow": 2.0}
        want = (cmd.obj or "").strip().lower()
        if want not in table:
            cur = [k for k, v in table.items() if v == self.term.speed]
            self.say("Text speed is {key}%s{/}. Choose: off, fast, normal, slow." % (cur[-1] if cur else "custom"),
                     "system")
            return
        self.term.speed = table[want]
        self.say("Text speed: {key}%s{/}." % want, "system")

    def do_art(self, cmd):
        want = (cmd.obj or "").strip().lower()
        on = {"on": True, "off": False}.get(want, not self.settings.get("art", True))
        self.settings["art"] = on
        self.say("Art %s." % ("on" if on else "off"), "system")

    # ------------------------------------------------------------------ #
    # session
    # ------------------------------------------------------------------ #
    def do_save(self, cmd):
        self.save_slot(cmd.obj.strip() or "save")

    def do_load(self, cmd):
        self.load_slot(cmd.obj.strip() or "save")

    def do_quit(self, cmd):
        if self.term.interactive:
            if not self.ui.confirm("Quit the game? Unsaved progress will be lost."):
                self.say("On with the adventure.", "system")
                return
        self.say("Thank you for playing. Goodbye!", "system")
        self.over = "quit"

    def do_restart(self, cmd):
        if self.term.interactive and not self.ui.confirm("Start over from the beginning?"):
            return
        self.new_world(self.seed)
        self.ui.clear()
        self.begin_story()

    def do_again(self, cmd):
        pass
