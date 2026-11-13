"""Tactical turn-based combat.

Each round the enemy *telegraphs* what it is about to do, and the player
answers:

    Strike   reliable hit
    Heavy    big damage, may miss, leaves you open
    Guard    halve incoming damage (and counter a charged blow), +1 focus
    Focus    skip the attack; your next one cannot miss and is critical
    Skills   abilities from your class or gear, paid for with focus
    Item     use something from the pack
    Flee     try to get away

Reading the tell - guard against the wind-up, strike while it recovers, focus
while it braces - is what wins fights against stronger enemies.

Enemy moves come from the character's ``moves`` list::

    {"type": "attack", "name": "Claw", "weight": 3}
    {"type": "heavy", "name": "Overload", "mult": 2.4, "tell": "Its servos whine..."}
    {"type": "guard", "name": "Raise plating"}
    {"type": "status", "name": "Venom bite", "status": "poison", "turns": 3, "power": 3}
    {"type": "heal", "name": "Self-repair", "amount": 15}
    {"type": "drain", "name": "Leech", "mult": 0.8}
"""
from __future__ import annotations

from . import conditions
from .sprite import Sprite, generate
from .term import truncate

DEFAULT_MOVES = [
    {"type": "attack", "name": "Attack", "weight": 4},
    {"type": "heavy", "name": "Heavy blow", "weight": 1, "mult": 2.2},
    {"type": "guard", "name": "Guard", "weight": 1},
]

ABILITIES = {
    "shield_bash": {"name": "Shield Bash", "cost": 2, "kind": "attack", "mult": 0.8,
                    "status": {"name": "stun", "turns": 1},
                    "text": "You slam into {enemy}, leaving it reeling."},
    "cleave": {"name": "Cleave", "cost": 3, "kind": "attack", "mult": 2.0, "sure": True,
               "text": "You put your whole weight behind one sweeping cut."},
    "backstab": {"name": "Backstab", "cost": 2, "kind": "attack", "mult": 1.5,
                 "status": {"name": "bleed", "turns": 3, "power": 4},
                 "text": "You slip past its guard and strike where it hurts."},
    "smoke": {"name": "Smoke Bomb", "cost": 2, "kind": "debuff",
              "status": {"name": "blind", "turns": 3},
              "text": "Smoke billows. {enemy} swings at shadows."},
    "firebolt": {"name": "Firebolt", "cost": 2, "kind": "attack", "flat": 18, "per_level": 5,
                 "ignore_defense": True, "sure": True,
                 "status": {"name": "burn", "turns": 2, "power": 4},
                 "text": "Fire leaps from your hand."},
    "mend": {"name": "Mend", "cost": 2, "kind": "heal", "heal_pct": 0.35,
             "text": "Warmth knits your wounds together."},
    "overcharge": {"name": "Overcharge", "cost": 2, "kind": "attack", "mult": 1.8,
                   "ignore_defense": True,
                   "text": "You thumb the regulator to maximum and cut loose."},
    "override": {"name": "Remote Override", "cost": 2, "kind": "debuff", "tag": "machine",
                 "status": {"name": "stun", "turns": 2},
                 "text": "You jab the remote. {enemy} locks up mid-motion."},
}

STATUS_INFO = {
    "poison": ("poisoned", "green"), "burn": ("burning", "orange"), "bleed": ("bleeding", "red"),
    "stun": ("stunned", "yellow"), "blind": ("blinded", "gray"), "weak": ("weakened", "purple"),
    "exposed": ("exposed", "pink"),
}


def _mid(name):
    """A move name for the middle of a sentence ("The overload" -> "the overload")."""
    name = str(name or "")
    if len(name) > 1 and name[0].isupper() and not name[1].isupper():
        return name[0].lower() + name[1:]
    return name


class Fighter:
    """Battle-time view of the player or an enemy."""

    def __init__(self, name, stats, is_player=False):
        self.name = name
        self.stats = stats
        self.is_player = is_player
        self.status = {}        # name -> {"turns": n, "power": p}
        self.guarding = False
        self.focused = False
        self.open = False       # off balance after a heavy swing
        self.charged = None     # enemy: heavy move being wound up

    @property
    def hp(self):
        return self.stats.get("health", 0)

    @hp.setter
    def hp(self, v):
        self.stats["health"] = max(0, min(int(v), self.stats.get("max_health", int(v))))

    @property
    def max_hp(self):
        return self.stats.get("max_health", self.stats.get("health", 1))

    def has(self, status):
        return status in self.status

    def add_status(self, name, turns=2, power=0):
        cur = self.status.get(name)
        if cur:
            cur["turns"] = max(cur["turns"], turns)
            cur["power"] = max(cur.get("power", 0), power)
        else:
            self.status[name] = {"turns": turns, "power": power}


class Battle:
    def __init__(self, game, enemy_id, can_flee=True):
        self.g = game
        self.ui = game.ui
        self.rng = game.world.rng
        self.enemy_id = enemy_id
        self.char = game.world.characters[enemy_id]
        st = self.char.setdefault("stats", {})
        st.setdefault("health", 20)
        st.setdefault("max_health", st["health"])
        st.setdefault("attack", 5)
        st.setdefault("defense", 0)
        self.enemy = Fighter(self.char.get("name", "Enemy"), st)
        pst = game.world.stats
        pst.setdefault("max_health", pst.get("health", 100))
        self.player = Fighter(game.world.player.get("name", "You"), pst, is_player=True)
        self.can_flee = can_flee and not self.char.get("no_flee")
        self.focus = int(game.world.player.get("focus_start", 1))
        self.max_focus = 5
        self.round = 0
        self.moves = self.char.get("moves") or DEFAULT_MOVES
        self.last_move_type = None
        self.result = None
        self.intent = None
        self.sprite = self._sprite()
        game.battle = self

    # ------------------------------------------------------------------ #
    def _sprite(self):
        ref = self.char.get("sprite")
        if ref in (None, False, "none"):
            return None
        data = self.g.data.sprites.get(ref) if isinstance(ref, str) else ref
        if isinstance(data, dict) and data.get("pixels"):
            return Sprite.from_data(data, str(ref))
        seed = self.char.get("sprite_seed") or self.char.get("template") or self.char.get("name")
        return generate(seed, int(self.char.get("sprite_size", 12)))

    def say(self, text, role="combat", **kw):
        text = text.replace("{enemy}", "{character}%s{/}" % self.enemy.name)
        self.g.say(text, role, **kw)

    # ------------------------------------------------------------------ #
    # damage
    # ------------------------------------------------------------------ #
    def roll_damage(self, attacker, defender, mult=1.0, ignore_defense=False, flat=None):
        base = flat if flat is not None else (6 + attacker.stats.get("attack", 0))
        raw = base * mult * self.rng.uniform(0.85, 1.15)
        if attacker.has("weak"):
            raw *= 0.7
        if defender.has("exposed") or defender.open:
            raw *= 1.3
        if not ignore_defense:
            raw -= defender.stats.get("defense", 0) * 0.5
        dmg = max(1, int(round(raw)))
        if defender.guarding:
            dmg = max(1, dmg // 2)
        return dmg

    def crit_chance(self, attacker):
        return float(attacker.stats.get("critical_hit_chance", 0.05))

    # ------------------------------------------------------------------ #
    # presentation
    # ------------------------------------------------------------------ #
    def show_enemy(self, tint=None):
        if not self.sprite or not self.g.settings.get("art", True):
            return
        lines = self.sprite.render(self.ui.term, tint=tint)
        if self.ui.width < self.sprite.width + 4:
            return
        self.ui.gap()
        pad = " " * max(1, (min(self.ui.width, 60) - self.sprite.width) // 2)
        for l in lines:
            self.ui.line(pad + l)
        self.ui._last = "text"

    def hit_flash(self):
        """Blink the sprite white - only on an interactive terminal."""
        ui = self.ui
        if not (self.sprite and ui.animated and self.g.settings.get("art", True)):
            return
        if ui.width < self.sprite.width + 4:
            return
        try:
            pad = " " * max(1, (min(ui.width, 60) - self.sprite.width) // 2)
            frames = [self.sprite.render(ui.term, tint="flash"), self.sprite.render(ui.term, tint="hurt")]
            n = len(frames[0])
            for i, fr in enumerate(frames):
                if i:
                    ui.term.cursor_up(n)
                ui.term.write("\n".join(pad + l for l in fr) + "\n")
                ui.term.sleep(0.07)
            ui.term.cursor_up(n)
            for _ in range(n):
                ui.term.write("\x1b[2K\n")
            ui.term.cursor_up(n)
        except KeyboardInterrupt:
            ui._skip = True

    def status_line(self, f):
        tags = []
        for name, st in f.status.items():
            label, color = STATUS_INFO.get(name, (name, "gray"))
            tags.append("{%s}%s{/}" % (color, label))
        return (" " + " ".join(tags)) if tags else ""

    def show_status(self):
        ui = self.ui
        w = 10 if ui.narrow else 16
        e, p = self.enemy, self.player
        name_w = min(max(len(e.name), len(p.name)), 10 if ui.narrow else 16)
        ui.gap()
        for f, spec in ((e, "red"), (p, "green")):
            nm = f.name if len(f.name) <= name_w else f.name[:name_w - 1] + "."
            line = " %s %s %s%s" % (
                ui.c(nm.ljust(name_w), "character" if not f.is_player else "key"),
                ui.bar(f.hp, f.max_hp, w, spec),
                ui.c("%d/%d" % (f.hp, f.max_hp), "system"),
                ui.fmt(self.status_line(f), "system"))
            ui.line(truncate(line, ui.width))
        ui.line(" " + ui.c("Focus ", "system")
                + ui.term.paint(ui.g("star") * self.focus, "byellow")
                + ui.term.paint(ui.g("dot") * (self.max_focus - self.focus), "darkgray"))
        ui._last = "text"

    # ------------------------------------------------------------------ #
    # enemy AI
    # ------------------------------------------------------------------ #
    def choose_intent(self):
        e = self.enemy
        if e.has("stun"):
            return {"type": "stunned"}
        if e.charged:
            move = dict(e.charged)
            move["type"] = "release"
            return move
        options = []
        for m in self.moves:
            t = m.get("type", "attack")
            if t == "heavy" and self.last_move_type in ("heavy", "release"):
                continue
            if t == "guard" and self.last_move_type == "guard":
                continue
            if t == "heal" and e.hp > e.max_hp * 0.6:
                continue
            if m.get("if") and not conditions.check(m["if"], self.g):
                continue
            if m.get("below") and e.hp > e.max_hp * float(m["below"]):
                continue
            options.append(m)
        if not options:
            options = [{"type": "attack", "name": "Attack"}]
        total = sum(float(m.get("weight", 1)) for m in options)
        r = self.rng.uniform(0, total)
        for m in options:
            r -= float(m.get("weight", 1))
            if r <= 0:
                return m
        return options[-1]

    def describe_intent(self, intent):
        t = intent.get("type", "attack")
        name = intent.get("name", "")
        ui = self.ui
        if t == "stunned":
            return "{intent}%s{/} {enemy} is stunned and cannot act." % ui.g("dot")
        if t == "heavy":
            tell = intent.get("tell") or "{enemy} draws back, gathering strength for %s." % (name or "a heavy blow")
            return "{intent}%s{/} %s {hint}(it is winding up - a free moment){/}" % (ui.g("arrow"), tell)
        if t == "release":
            return "{error}%s %s is coming!{/} {hint}(Guard to blunt it){/}" % (ui.g("star"), name or "The heavy blow")
        if t == "guard":
            return "{intent}%s{/} {enemy} braces%s. {hint}(your hits will be halved){/}" % (
                ui.g("shield"), (" - " + name) if name and name != "Guard" else "")
        if t == "heal":
            return "{intent}%s{/} {enemy} is about to %s." % (ui.g("arrow"), (name or "recover").lower())
        if t == "status":
            return "{intent}%s{/} {enemy} readies %s." % (ui.g("arrow"), name or "something nasty")
        if t == "drain":
            return "{intent}%s{/} {enemy} prepares to %s." % (ui.g("arrow"), (name or "drain you").lower())
        if intent.get("intent"):
            return "{intent}%s{/} %s" % (ui.g("arrow"), intent["intent"])
        return "{intent}%s{/} {enemy} is about to %s." % (ui.g("arrow"), ("use " + _mid(name)) if name else "attack")

    def enemy_act(self, intent):
        e, p = self.enemy, self.player
        t = intent.get("type", "attack")
        self.last_move_type = t
        if e.has("stun"):                       # stunned before or during this round
            if t != "stunned":
                self.say("{enemy} is stunned and loses its turn.")
            e.charged = None
            self.spend_stun(e)
            return
        if t == "stunned":
            return
        if t == "heavy":
            e.charged = intent
            return
        if t == "guard":
            return                              # the brace already applied this round
        if t == "heal":
            amount = int(intent.get("amount", e.max_hp * 0.2))
            e.hp = e.hp + amount
            self.say(intent.get("text") or "{enemy} recovers {heal}%d{/} health." % amount)
            self.g.audio.sfx("heal")
            return
        mult = float(intent.get("mult", 1.0))
        name = intent.get("name")
        hit = 0.9
        if t == "release":
            e.charged = None
            mult = float(intent.get("mult", 2.2))
            hit = 1.0
        if e.has("blind"):
            hit -= 0.4
        hit -= float(p.stats.get("evasion", 0))
        if self.rng.random() > hit:
            self.say("{enemy} %s - and misses." % ("lunges" if t != "release" else "unleashes its blow"))
            self.g.audio.sfx("miss")
            return
        dmg = self.roll_damage(e, p, mult)
        crit = t != "release" and self.rng.random() < self.crit_chance(e)
        if crit:
            dmg *= 2
        if p.guarding and t == "release":
            dmg = max(1, dmg // 2)              # a guarded heavy blow is quartered in total
        p.hp = p.hp - dmg
        verb = intent.get("text") or ("{enemy} hits you with %s" % _mid(name) if name else "{enemy} hits you")
        self.say("%s%s for {damage}%d{/}.%s" % (verb.rstrip("."), " - a critical hit -" if crit else "", dmg,
                                                " Your guard absorbs most of it." if p.guarding else ""))
        self.g.audio.sfx("hurt")
        if t == "drain" and dmg > 0:
            e.hp = e.hp + max(1, dmg // 2)
        if t == "status" or intent.get("status"):
            sname = intent.get("status", "poison")
            if isinstance(sname, dict):
                sname, turns, power = sname.get("name", "poison"), sname.get("turns", 2), sname.get("power", 3)
            else:
                turns, power = int(intent.get("turns", 3)), int(intent.get("power", 3))
            if not p.guarding or self.rng.random() < 0.5:
                p.add_status(sname, turns, power)
                self.say("You are {%s}%s{/}." % (STATUS_INFO.get(sname, ("", "gray"))[1],
                                                STATUS_INFO.get(sname, (sname,))[0]))
        if p.guarding and t == "release" and p.hp > 0:
            counter = self.roll_damage(p, e, 0.6)
            e.hp = e.hp - counter
            self.say("You turn the blow aside and counter for {damage}%d{/}." % counter)

    # ------------------------------------------------------------------ #
    # player actions
    # ------------------------------------------------------------------ #
    def available_abilities(self):
        w = self.g.world
        ids = list(w.player.get("abilities", []))
        for iid in list(w.equipped) + list(w.inventory):
            for a in w.items.get(iid, {}).get("abilities", []) or []:
                if a not in ids:
                    ids.append(a)
        out = []
        for a in ids:
            spec = self.g.abilities.get(a)
            if spec:
                out.append((a, spec))
        return out

    def usable_items(self):
        w = self.g.world
        seen, out = set(), []
        for iid in w.inventory:
            it = w.items.get(iid, {})
            if iid in seen:
                continue
            if it.get("combat") or (it.get("usable") and "health" in (it.get("effect") or {})):
                seen.add(iid)
                out.append(iid)
        return out

    def player_attack(self, mult=1.0, hit=0.92, ignore_defense=False, flat=None, sure=False, label=None):
        p, e = self.player, self.enemy
        crit = False
        if p.focused:
            sure, crit = True, True
            p.focused = False
        if p.has("blind"):
            hit -= 0.3
        if not sure and self.rng.random() > hit:
            self.say("You swing%s and miss." % (" wide" if mult > 1.2 else ""))
            self.g.audio.sfx("miss")
            return 0
        dmg = self.roll_damage(p, e, mult, ignore_defense, flat)
        if not crit and self.rng.random() < self.crit_chance(p):
            crit = True
        if crit:
            dmg *= 2
        e.hp = e.hp - dmg
        self.hit_flash()
        self.say("%s {enemy} for {damage}%d{/}%s%s" % (
            label or "You hit", dmg, " - critical!" if crit else ".",
            " It was braced." if e.guarding else ""))
        self.g.audio.sfx("crit" if crit else "hit")
        return dmg

    def do_ability(self, aid, spec):
        p, e = self.player, self.enemy
        cost = int(spec.get("cost", 1))
        if self.focus < cost:
            self.say("Not enough focus for %s (needs %d)." % (spec.get("name", aid), cost), "error")
            return False
        tag = spec.get("tag")
        if tag and tag not in (self.char.get("tags") or []):
            self.say("%s has no effect on {enemy}." % spec.get("name", aid), "error")
            return False
        self.focus -= cost
        self.g.audio.sfx(spec.get("sfx", "special"))
        if spec.get("text"):
            self.say(spec["text"])
        kind = spec.get("kind", "attack")
        landed = True
        if kind == "attack":
            flat = None
            if "flat" in spec:
                flat = spec["flat"] + spec.get("per_level", 0) * (self.g.world.player.get("level", 1) - 1)
            landed = self.player_attack(float(spec.get("mult", 1.0)), 0.92, bool(spec.get("ignore_defense")),
                                        flat, bool(spec.get("sure"))) > 0
        elif kind == "heal":
            amount = int(spec.get("heal", 0) + p.max_hp * float(spec.get("heal_pct", 0)))
            before = p.hp
            p.hp = p.hp + amount
            self.say("You recover {heal}%d{/} health." % (p.hp - before))
        st = spec.get("status")
        if st and landed and e.hp > 0:
            if st["name"] in (self.char.get("immune") or []):
                self.say("{enemy} shrugs it off.")
            else:
                e.add_status(st["name"], int(st.get("turns", 2)), int(st.get("power", 0)))
                self.say("{enemy} is {%s}%s{/}." % (STATUS_INFO.get(st["name"], ("", "gray"))[1],
                                                   STATUS_INFO.get(st["name"], (st["name"],))[0]))
        return True

    def do_item(self):
        w = self.g.world
        ids = self.usable_items()
        if not ids:
            self.say("Nothing in your pack will help right now.", "error")
            return False
        labels = []
        for iid in ids:
            it = w.items[iid]
            n = w.inventory.count(iid)
            labels.append("{item}%s{/}%s" % (it["name"], " x%d" % n if n > 1 else ""))
        pick = self.ui.menu(labels, title="Use which item?", cancel_label="Back")
        if pick is None:
            return False
        iid = ids[pick]
        it = w.items[iid]
        combat = it.get("combat")
        if combat:
            w.inventory.remove(iid)
            self.g.audio.sfx(combat.get("sfx", "use"))
            if combat.get("text"):
                self.say(combat["text"])
            if combat.get("damage"):
                dmg = int(combat["damage"])
                self.enemy.hp = self.enemy.hp - dmg
                self.hit_flash()
                self.say("It deals {damage}%d{/} to {enemy}." % dmg)
            if combat.get("heal"):
                before = self.player.hp
                self.player.hp = self.player.hp + int(combat["heal"])
                self.say("You recover {heal}%d{/} health." % (self.player.hp - before))
            st = combat.get("status")
            if st and self.enemy.hp > 0:
                self.enemy.add_status(st["name"], int(st.get("turns", 2)), int(st.get("power", 0)))
                self.say("{enemy} is %s." % STATUS_INFO.get(st["name"], (st["name"],))[0])
            if combat.get("cure"):
                for s in list(self.player.status):
                    if combat["cure"] is True or s in combat["cure"]:
                        self.player.status.pop(s)
            if combat.get("focus"):
                self.focus = min(self.max_focus, self.focus + int(combat["focus"]))
            return True
        return self.g.use_consumable(iid)

    def try_flee(self):
        if not self.can_flee:
            self.say("There is nowhere to run.", "error")
            return False
        chance = 0.55 + 0.1 * (1 if self.enemy.has("stun") or self.enemy.has("blind") else 0)
        if self.rng.random() < chance:
            self.g.audio.sfx("flee")
            self.say("You break away and run.", "system")
            self.result = "fled"
        else:
            self.say("You try to run, but {enemy} cuts you off.")
        return True

    def player_turn(self):
        """Ask for an action until one actually uses the turn."""
        p = self.player
        if p.has("stun"):
            self.say("You are stunned and lose your turn.", "error")
            self.spend_stun(p)
            return
        abilities = self.available_abilities()
        while True:
            options = [("strike", "Strike"), ("heavy", "Heavy blow {hint}(big, may miss){/}"),
                       ("guard", "Guard {hint}(halve damage, +1 focus){/}"),
                       ("focus", "Focus {hint}(next hit is critical){/}")]
            for aid, spec in abilities:
                tag = "{hint}(%d focus){/}" % spec.get("cost", 1)
                options.append(("ability:" + aid, "%s %s" % (spec.get("name", aid), tag)))
            if self.usable_items():
                options.append(("item", "Item"))
            if self.can_flee:
                options.append(("flee", "Flee"))
            compact = self.round > 1
            if self.ui.narrow or compact:
                labels = [self.ui.term.strip_markup(l).split(" (")[0] for _k, l in options]
            else:
                labels = [l for _k, l in options]
            aliases = {"attack": 0, "a": 0, "hit": 0, "s": 0, "h": 1, "defend": 2, "block": 2,
                       "d": 2, "g": 2, "f": 3, "aim": 3, "run": len(options) - 1 if self.can_flee else 0,
                       "use": [k for k, _l in options].index("item") if self.usable_items() else 0}
            pick = self.ui.menu(labels, cancel=False, prompt="Action> ", aliases=aliases, compact=compact)
            if pick is None:
                # no usable answer (or input ended): do the sensible default
                key = "strike"
            else:
                key = options[pick][0]
            if key == "strike":
                self.player_attack()
                return
            if key == "heavy":
                self.player_attack(1.8, 0.7, label="Your heavy blow lands on")
                p.open = True
                return
            if key == "guard":
                p.guarding = True
                self.focus = min(self.max_focus, self.focus + 1)
                self.say("You set your feet and raise your guard.", "system")
                self.g.audio.sfx("guard")
                return
            if key == "focus":
                p.focused = True
                self.focus = min(self.max_focus, self.focus + 1)
                self.say("You steady your breathing and pick your spot.", "system")
                self.g.audio.sfx("focus")
                return
            if key == "item":
                if self.do_item():
                    return
                continue
            if key == "flee":
                if self.try_flee():
                    return
                continue
            if key.startswith("ability:"):
                aid = key.split(":", 1)[1]
                if self.do_ability(aid, self.g.abilities[aid]):
                    return
                continue

    # ------------------------------------------------------------------ #
    @staticmethod
    def spend_stun(f):
        """A stun lasts for a number of the victim's own lost turns."""
        st = f.status.get("stun")
        if st:
            st["turns"] -= 1
            if st["turns"] <= 0:
                del f.status["stun"]

    def tick_statuses(self, f):
        for name in list(f.status):
            if name == "stun":
                continue                        # counted in lost turns, not rounds
            st = f.status[name]
            if name in ("poison", "burn", "bleed") and f.hp > 0:
                dmg = max(1, int(st.get("power", 2)))
                f.hp = f.hp - dmg
                who = "You take" if f.is_player else "{enemy} takes"
                self.say("%s {damage}%d{/} from %s." % (who, dmg, {"poison": "poison", "burn": "the flames",
                                                                  "bleed": "bleeding"}[name]))
            st["turns"] -= 1
            if st["turns"] <= 0:
                del f.status[name]

    def run(self):
        """Fight to the end. Returns "win", "lose" or "fled"."""
        g, ui = self.g, self.ui
        e, p = self.enemy, self.player
        g.audio.sfx("encounter")
        g.play_music(self.char.get("battle_music") or g.data.config.get("battle_music")
                     or {"generate": {"mood": "battle", "seed": self.char.get("template") or self.enemy_id}},
                     raw=True)
        ui.rule("%s  %s" % (ui.g("sword"), e.name))
        self.show_enemy()
        intro = self.char.get("battle_intro")
        if intro:
            self.say(intro, "story")
        while e.hp > 0 and p.hp > 0 and self.result is None:
            self.round += 1
            intent = self.intent = self.choose_intent()
            e.guarding = intent.get("type") == "guard"
            self.show_status()
            self.say(self.describe_intent(intent), "default")
            p.guarding = False
            self.player_turn()
            if self.result or e.hp <= 0 or p.hp <= 0:
                break
            self.enemy_act(intent)
            p.open = False
            self.tick_statuses(e)
            if e.hp <= 0 or p.hp <= 0:
                break
            self.tick_statuses(p)
        e.guarding = p.guarding = False
        if self.result is None:
            self.result = "win" if e.hp <= 0 and p.hp > 0 else "lose"
        if self.result == "win":
            g.audio.sfx("enemy_down")
            self.show_enemy(tint="dark")
            self.say(self.char.get("defeat_text") or "{enemy} is defeated.", "success")
        elif self.result == "lose":
            self.say(self.char.get("victory_text") or "{enemy} has beaten you.", "error")
        if self.result == "lose":
            g.audio.music(None)
        else:
            g.resume_music()                    # back to the scene's music
        ui.rule()
        return self.result
