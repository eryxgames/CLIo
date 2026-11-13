# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Tactical turn-based combat.

Each round every enemy *telegraphs* what it is about to do, and the player
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

A fight may be against a group.  Then each enemy shows its own intent, the
player picks a target ("strike 2" does it in one go), and skills or items
marked ``"area": true`` reach everyone (``"splash": 0.6`` gives the others a
share of a blow aimed at one of them).

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
    "cleave": {"name": "Cleave", "cost": 3, "kind": "attack", "mult": 2.0, "sure": True, "splash": 0.6,
               "text": "You put your whole weight behind one sweeping cut."},
    "backstab": {"name": "Backstab", "cost": 2, "kind": "attack", "mult": 1.5,
                 "status": {"name": "bleed", "turns": 3, "power": 4},
                 "text": "You slip past its guard and strike where it hurts."},
    "smoke": {"name": "Smoke Bomb", "cost": 2, "kind": "debuff", "area": True,
              "status": {"name": "blind", "turns": 3},
              "text": "Smoke billows through the room."},
    "firebolt": {"name": "Firebolt", "cost": 2, "kind": "attack", "flat": 18, "per_level": 5,
                 "ignore_defense": True, "sure": True,
                 "status": {"name": "burn", "turns": 2, "power": 4},
                 "text": "Fire leaps from your hand."},
    "nova": {"name": "Nova", "cost": 3, "kind": "attack", "flat": 11, "per_level": 3, "area": True,
             "ignore_defense": True, "sure": True,
             "text": "You open both hands and the fire goes everywhere at once."},
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


LETTERS = "ABCDEFGH"


def _mid(name):
    """A move name for the middle of a sentence ("The overload" -> "the overload")."""
    name = str(name or "")
    if len(name) > 1 and name[0].isupper() and not name[1].isupper():
        return name[0].lower() + name[1:]
    return name


class Fighter:
    """Battle-time view of the player or an enemy."""

    def __init__(self, name, stats, is_player=False, cid=None, char=None):
        self.name = name
        self.stats = stats
        self.is_player = is_player
        self.cid = cid
        self.char = char or {}
        self.status = {}        # name -> {"turns": n, "power": p}
        self.guarding = False
        self.focused = False
        self.open = False       # off balance after a heavy swing
        self.charged = None     # enemy: heavy move being wound up
        self.moves = self.char.get("moves") or DEFAULT_MOVES
        self.intent = None      # enemy: what it will do this round
        self.last_move_type = None
        self.sprite = None
        self.fell = False       # its defeat has been announced

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
    """One fight: the player against one enemy or a group of them."""

    def __init__(self, game, enemy_ids, can_flee=True):
        self.g = game
        self.ui = game.ui
        self.rng = game.world.rng
        ids = [enemy_ids] if isinstance(enemy_ids, str) else list(enemy_ids)
        self.enemies = []
        for cid in ids:
            char = game.world.characters[cid]
            st = char.setdefault("stats", {})
            st.setdefault("health", 20)
            st.setdefault("max_health", st["health"])
            st.setdefault("attack", 5)
            st.setdefault("defense", 0)
            f = Fighter(char.get("name", "Enemy"), st, cid=cid, char=char)
            f.sprite = self._sprite(char)
            self.enemies.append(f)
        names = [f.name for f in self.enemies]
        for name in set(names):                 # two Bone Rats become "Bone Rat A" and "Bone Rat B"
            same = [f for f in self.enemies if f.name == name]
            if len(same) > 1:
                for i, f in enumerate(same):
                    f.name = "%s %s" % (name, LETTERS[i % len(LETTERS)])
        pst = game.world.stats
        pst.setdefault("max_health", pst.get("health", 100))
        self.player = Fighter(game.world.player.get("name", "You"), pst, is_player=True)
        self.can_flee = can_flee and not any(f.char.get("no_flee") for f in self.enemies)
        self.focus = int(game.world.player.get("focus_start", 1))
        self.max_focus = 5
        self.round = 0
        self.result = None
        self.target = None      # the enemy the player last aimed at
        self.actor = None       # the enemy acting right now (for "{enemy}" in messages)
        self.last_fallen = None
        self.killer = None      # who struck the player down
        game.battle = self

    # ------------------------------------------------------------------ #
    # who is who
    # ------------------------------------------------------------------ #
    @property
    def alive(self):
        return [f for f in self.enemies if f.hp > 0]

    @property
    def fallen(self):
        """Ids of the enemies that are down."""
        return [f.cid for f in self.enemies if f.hp <= 0]

    @property
    def group(self):
        return len(self.enemies) > 1

    @property
    def enemy(self):
        """The enemy in focus: the current target, else the first one standing."""
        if self.target is not None and self.target.hp > 0:
            return self.target
        alive = self.alive
        if alive:
            return alive[0]
        return self.last_fallen or self.target or self.enemies[0]

    @property
    def intent(self):
        return self.enemy.intent

    @property
    def char(self):
        return self.enemy.char

    @property
    def enemy_id(self):
        return self.enemies[0].cid

    @property
    def sprite(self):
        return self.enemies[0].sprite

    # ------------------------------------------------------------------ #
    def _sprite(self, char):
        ref = char.get("sprite")
        if ref in (None, False, "none"):
            return None
        data = self.g.data.sprites.get(ref) if isinstance(ref, str) else ref
        if isinstance(data, dict) and data.get("pixels"):
            return Sprite.from_data(data, str(ref))
        seed = char.get("sprite_seed") or char.get("template") or char.get("name")
        return generate(seed, int(char.get("sprite_size", 12)))

    def say(self, text, role="combat", who=None, **kw):
        who = who or self.actor or self.enemy
        text = text.replace("{enemy}", "{character}%s{/}" % who.name)
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

    def check_fall(self, e):
        """Announce an enemy going down while others still stand."""
        if e.hp > 0 or e.fell:
            return
        e.fell = True
        e.charged = None
        self.last_fallen = e
        if self.target is e:
            self.target = None
        if self.alive:
            self.g.audio.sfx("enemy_down")
            self.say(e.char.get("defeat_text") or "{enemy} falls.", "success", who=e)

    # ------------------------------------------------------------------ #
    # presentation
    # ------------------------------------------------------------------ #
    def show_enemy(self, tint=None):
        ui = self.ui
        if not self.g.settings.get("art", True):
            return
        if not self.group:
            sprites = [self.enemies[0].sprite]
        elif tint:
            return                              # a group does not get a closing picture
        else:
            sprites = [f.sprite for f in self.enemies]
        if not sprites or any(s is None for s in sprites):
            return
        total = sum(s.width for s in sprites) + 3 * (len(sprites) - 1)
        if ui.width < total + 4:
            return
        lines = []
        for s in sprites:
            block = s.render(ui.term, tint=tint)
            lines = ui.side_by_side(lines, block, 3) if lines else block
        ui.gap()
        pad = " " * max(1, (min(ui.width, 60) - total) // 2)
        for l in lines:
            ui.line(pad + l)
        ui._last = "text"

    def hit_flash(self):
        """Blink the sprite white - only on an interactive terminal, one on one."""
        ui = self.ui
        sprite = self.enemies[0].sprite
        if self.group or not (sprite and ui.animated and self.g.settings.get("art", True)):
            return
        if ui.width < sprite.width + 4:
            return
        try:
            pad = " " * max(1, (min(ui.width, 60) - sprite.width) // 2)
            frames = [sprite.render(ui.term, tint="flash"), sprite.render(ui.term, tint="hurt")]
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

    def _bar_line(self, f, name_w, bar_w, lead=" "):
        ui = self.ui
        nm = f.name
        if len(nm) > name_w:
            if len(nm) > 2 and nm[-2] == " " and nm[-1] in LETTERS and name_w > 4:
                nm = nm[:name_w - 2] + "." + nm[-1]         # keep the letter that tells two of a kind apart
            else:
                nm = nm[:name_w - 1] + "."
        return "%s%s %s %s" % (lead, ui.c(nm.ljust(name_w), "character" if not f.is_player else "key"),
                               ui.bar(f.hp, f.max_hp, bar_w, "green" if f.is_player else "red"),
                               ui.c("%d/%d" % (f.hp, f.max_hp), "system"))

    def show_status(self):
        ui = self.ui
        p = self.player
        alive = self.alive
        ui.gap()
        if not self.group:
            e = self.enemies[0]
            w = 10 if ui.narrow else 16
            name_w = min(max(len(e.name), len(p.name)), 10 if ui.narrow else 16)
            for f in (e, p):
                ui.line(truncate(self._bar_line(f, name_w, w) + ui.fmt(self.status_line(f), "system"), ui.width))
        else:
            # one numbered line per enemy, with a short note on what it is about to do
            wide = ui.width >= 64
            w = 5 if ui.width < 40 else (8 if ui.narrow else 12)
            room = ui.width - w - 13                     # the number, the bar and "123/123" take the rest
            name_w = max(6, min(max(len(f.name) for f in alive + [p]), room, 18))
            for i, f in enumerate(alive, 1):
                line = self._bar_line(f, name_w, w, " %s " % ui.c(str(i), "key"))
                note = "%s%s" % (self.intent_tag(f), ui.fmt(self.status_line(f), "system"))
                if wide:
                    ui.line(truncate(line + "  " + note, ui.width))
                else:
                    ui.line(truncate(line, ui.width))
                    ui.line(truncate("     " + note, ui.width))
            ui.line(truncate(self._bar_line(p, name_w, w, "   ") + ui.fmt(self.status_line(p), "system"), ui.width))
        ui.line(" " + ui.c("Focus ", "system")
                + ui.term.paint(ui.g("star") * self.focus, "byellow")
                + ui.term.paint(ui.g("dot") * (self.max_focus - self.focus), "darkgray"))
        ui._last = "text"

    # ------------------------------------------------------------------ #
    # enemy AI
    # ------------------------------------------------------------------ #
    def choose_intent(self, e=None):
        e = e or self.enemy
        if e.has("stun"):
            return {"type": "stunned"}
        if e.charged:
            move = dict(e.charged)
            move["type"] = "release"
            return move
        options = []
        for m in e.moves:
            t = m.get("type", "attack")
            if t == "heavy" and e.last_move_type in ("heavy", "release"):
                continue
            if t == "guard" and e.last_move_type == "guard":
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

    def intent_tag(self, e):
        """A few words on what one enemy of a group is about to do."""
        ui = self.ui
        intent = e.intent or {}
        t = intent.get("type", "attack")
        name = _mid(intent.get("name") or "")
        if t == "stunned":
            return ui.fmt("{intent}%s{/} {hint}stunned{/}" % ui.g("dot"))
        if t == "heavy":
            return ui.fmt("{intent}%s{/} winding up" % ui.g("arrow"))
        if t == "release":
            return ui.fmt("{error}%s %s!{/}" % (ui.g("star"), name or "heavy blow"))
        if t == "guard":
            return ui.fmt("{intent}%s{/} braced" % ui.g("shield"))
        if t == "heal":
            return ui.fmt("{intent}%s{/} healing" % ui.g("arrow"))
        return ui.fmt("{intent}%s{/} %s" % (ui.g("arrow"), name or "attack"))

    def enemy_act(self, e=None, intent=None):
        if e is not None and not isinstance(e, Fighter):    # old call style: enemy_act(intent)
            e, intent = None, e
        e = e or self.enemy
        intent = intent or e.intent or {"type": "attack"}
        p = self.player
        self.actor = e
        t = intent.get("type", "attack")
        e.last_move_type = t
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
            self.check_fall(e)

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

    def pick_target(self, number=None):
        """The enemy to aim at: the only one, the numbered one, or ask. None = changed their mind."""
        alive = self.alive
        if not alive:
            return None
        if len(alive) == 1:
            self.target = alive[0]
            return self.target
        if number and 1 <= number <= len(alive):
            self.target = alive[number - 1]
            return self.target
        default = alive.index(self.target) if self.target in alive else 0
        labels = ["%s {hint}%d{/}" % (f.name, f.hp) for f in alive]
        pick = self.ui.menu(labels, cancel=True, prompt="Target> ", aliases={"": default}, compact=True)
        if pick is None:
            return None
        self.target = alive[pick]
        return self.target

    def player_attack(self, mult=1.0, hit=0.92, ignore_defense=False, flat=None, sure=False, label=None,
                      target=None):
        p, e = self.player, target or self.enemy
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
            " It was braced." if e.guarding else ""), who=e)
        self.g.audio.sfx("crit" if crit else "hit")
        self.check_fall(e)
        return dmg

    def apply_status(self, e, st):
        if not st or e.hp <= 0:
            return
        if st["name"] in (e.char.get("immune") or []):
            self.say("{enemy} shrugs it off.", who=e)
            return
        e.add_status(st["name"], int(st.get("turns", 2)), int(st.get("power", 0)))
        self.say("{enemy} is {%s}%s{/}." % (STATUS_INFO.get(st["name"], ("", "gray"))[1],
                                           STATUS_INFO.get(st["name"], (st["name"],))[0]), who=e)

    def do_ability(self, aid, spec, number=None):
        p = self.player
        cost = int(spec.get("cost", 1))
        if self.focus < cost:
            self.say("Not enough focus for %s (needs %d)." % (spec.get("name", aid), cost), "error")
            return False
        kind = spec.get("kind", "attack")
        area = bool(spec.get("area"))
        tag = spec.get("tag")
        e = None
        if kind != "heal":
            if area:
                victims = [f for f in self.alive if not tag or tag in (f.char.get("tags") or [])]
                if not victims:
                    self.say("%s has no effect here." % spec.get("name", aid), "error")
                    return False
                e = victims[0]
            else:
                e = self.pick_target(number)
                if e is None:
                    return False
                if tag and tag not in (e.char.get("tags") or []):
                    self.say("%s has no effect on {enemy}." % spec.get("name", aid), "error", who=e)
                    return False
                victims = [e]
        self.focus -= cost
        self.g.audio.sfx(spec.get("sfx", "special"))
        if spec.get("text"):
            self.say(spec["text"], who=e)
        if kind == "heal":
            amount = int(spec.get("heal", 0) + p.max_hp * float(spec.get("heal_pct", 0)))
            before = p.hp
            p.hp = p.hp + amount
            self.say("You recover {heal}%d{/} health." % (p.hp - before))
            return True
        st = spec.get("status")
        flat = None
        if "flat" in spec:
            flat = spec["flat"] + spec.get("per_level", 0) * (self.g.world.player.get("level", 1) - 1)
        mult = float(spec.get("mult", 1.0))
        focused = p.focused
        for f in victims:
            landed = True
            if kind == "attack":
                p.focused = focused                         # a focused sweep is critical on everyone
                landed = self.player_attack(mult, 0.92, bool(spec.get("ignore_defense")), flat,
                                            bool(spec.get("sure")), target=f) > 0
            if landed:
                self.apply_status(f, st)
        p.focused = False if kind == "attack" else p.focused
        splash = float(spec.get("splash", 0) or 0)
        if kind == "attack" and splash and not area:
            for f in [x for x in self.alive if x is not e]:
                self.player_attack(mult * splash, 0.92, bool(spec.get("ignore_defense")),
                                   (flat * splash) if flat is not None else None, True,
                                   label="The sweep catches", target=f)
        return True

    def do_item(self, number=None):
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
        if not combat:
            return self.g.use_consumable(iid)
        st = combat.get("status")
        victims = []
        if combat.get("damage") or st:
            if combat.get("area"):
                victims = self.alive
            else:
                e = self.pick_target(number)
                if e is None:
                    return False
                victims = [e]
        w.inventory.remove(iid)
        self.g.audio.sfx(combat.get("sfx", "use"))
        if combat.get("text"):
            self.say(combat["text"], who=victims[0] if victims else None)
        for f in victims:
            if combat.get("damage"):
                dmg = int(combat["damage"])
                f.hp = f.hp - dmg
                self.hit_flash()
                self.say("It deals {damage}%d{/} to {enemy}." % dmg, who=f)
                self.check_fall(f)
            self.apply_status(f, st)
        if combat.get("heal"):
            before = self.player.hp
            self.player.hp = self.player.hp + int(combat["heal"])
            self.say("You recover {heal}%d{/} health." % (self.player.hp - before))
        if combat.get("cure"):
            for s in list(self.player.status):
                if combat["cure"] is True or s in combat["cure"]:
                    self.player.status.pop(s)
        if combat.get("focus"):
            self.focus = min(self.max_focus, self.focus + int(combat["focus"]))
        return True

    def try_flee(self):
        if not self.can_flee:
            self.say("There is nowhere to run.", "error")
            return False
        alive = self.alive
        hampered = sum(1 for f in alive if f.has("stun") or f.has("blind"))
        chance = 0.55 - 0.08 * (len(alive) - 1) + 0.1 * hampered
        if self.rng.random() < max(0.25, chance):
            self.g.audio.sfx("flee")
            self.say("You break away and run.", "system")
            self.result = "fled"
        else:
            keeper = [f for f in alive if not (f.has("stun") or f.has("blind"))] or alive
            self.say("You try to run, but {enemy} cuts you off.", who=keeper[0])
        return True

    def player_turn(self):
        """Ask for an action until one actually uses the turn."""
        p = self.player
        ui = self.ui
        if p.has("stun"):
            self.say("You are stunned and lose your turn.", "error")
            self.spend_stun(p)
            return
        self.actor = None
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
            if ui.narrow or compact:
                labels = [ui.term.strip_markup(l).split(" (")[0] for _k, l in options]
            else:
                labels = [l for _k, l in options]
            aliases = {"attack": 0, "a": 0, "hit": 0, "s": 0, "h": 1, "defend": 2, "block": 2,
                       "d": 2, "g": 2, "f": 3, "aim": 3, "run": len(options) - 1 if self.can_flee else 0,
                       "use": [k for k, _l in options].index("item") if self.usable_items() else 0}
            pick = ui.menu(labels, cancel=False, prompt="Action> ", aliases=aliases, compact=compact,
                           numbered=True)
            number = ui.menu_number
            if pick is None:
                # no usable answer (or input ended): do the sensible default
                key = "strike"
            else:
                key = options[pick][0]
            if key in ("strike", "heavy"):
                e = self.pick_target(number)
                if e is None:
                    continue
                if key == "strike":
                    self.player_attack(target=e)
                else:
                    self.player_attack(1.8, 0.7, label="Your heavy blow lands on", target=e)
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
                if self.do_item(number):
                    return
                continue
            if key == "flee":
                if self.try_flee():
                    return
                continue
            if key.startswith("ability:"):
                aid = key.split(":", 1)[1]
                if self.do_ability(aid, self.g.abilities[aid], number):
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
                                                                  "bleed": "bleeding"}[name]),
                         who=None if f.is_player else f)
            st["turns"] -= 1
            if st["turns"] <= 0:
                del f.status[name]

    def title(self):
        names = ", ".join(f.name for f in self.enemies)
        if len(names) > self.ui.width - 12:
            names = "%d enemies" % len(self.enemies)
        return names

    def run(self):
        """Fight to the end. Returns "win", "lose" or "fled"."""
        g, ui = self.g, self.ui
        p = self.player
        lead = max(self.enemies, key=lambda f: f.max_hp)
        g.audio.sfx("encounter")
        g.play_music(lead.char.get("battle_music") or g.data.config.get("battle_music")
                     or {"generate": {"mood": "battle", "seed": lead.char.get("template") or lead.cid}},
                     raw=True)
        ui.rule("%s  %s" % (ui.g("sword"), self.title()))
        self.show_enemy()
        told = set()
        for f in self.enemies:
            intro = f.char.get("battle_intro")
            if intro and intro not in told:
                told.add(intro)
                self.say(intro, "story", who=f)
        while self.alive and p.hp > 0 and self.result is None:
            self.round += 1
            self.actor = None
            for e in self.alive:
                e.intent = self.choose_intent(e)
                e.guarding = e.intent.get("type") == "guard"
            self.show_status()
            if not self.group:
                self.say(self.describe_intent(self.enemies[0].intent), "default", who=self.enemies[0])
            else:
                tells = set()
                for e in self.alive:            # spell out the dangerous ones
                    kind = e.intent.get("type")
                    if kind == "heavy":
                        tell = self.describe_intent(e.intent)
                        if not ui.narrow and tell not in tells:
                            tells.add(tell)
                            self.say(tell, "default", who=e)
                    elif kind == "release":
                        self.say("{error}%s{/} {enemy}{error}: %s is coming!{/} {hint}(Guard to blunt it){/}" % (
                            ui.g("star"), _mid(e.intent.get("name")) or "the heavy blow"), "default", who=e)
                if self.round == 1 and not ui.narrow:
                    self.say("{hint}Add a number to aim: 'strike 2', 'heavy 1'.{/}", "default")
            p.guarding = False
            self.player_turn()
            if self.result or not self.alive or p.hp <= 0:
                break
            for e in self.alive:
                if e.hp <= 0:
                    continue                    # brought down by a counter earlier this round
                self.enemy_act(e)
                if p.hp <= 0:
                    break
            p.open = False
            if p.hp <= 0:
                break
            for e in self.alive:
                self.actor = e
                self.tick_statuses(e)
                self.check_fall(e)
            self.actor = None
            if not self.alive:
                break
            self.tick_statuses(p)
        for f in self.enemies:
            f.guarding = False
        p.guarding = False
        killer = self.actor or self.enemy
        self.actor = None
        if self.result is None:
            self.result = "win" if not self.alive and p.hp > 0 else "lose"
        if self.result == "win":
            last = self.last_fallen or self.enemies[-1]
            for f in self.enemies:
                if f.hp <= 0 and not f.fell:
                    f.fell = True
                    last = f
            self.last_fallen = last
            g.audio.sfx("enemy_down")
            self.show_enemy(tint="dark")
            self.say(last.char.get("defeat_text") or "{enemy} is defeated.", "success", who=last)
            if self.group:
                self.say("The fight is yours.", "success")
        elif self.result == "lose":
            self.killer = killer
            self.say(killer.char.get("victory_text") or "{enemy} has beaten you.", "error", who=killer)
        if self.result == "lose":
            g.audio.music(None)
        else:
            g.resume_music()                    # back to the scene's music
        ui.rule()
        return self.result
