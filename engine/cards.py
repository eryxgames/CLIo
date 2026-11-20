# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Card battles: a fight played with a deck.

A game turns them on with ``"battle": "cards"`` in game.json, in one of its modes, or on one character
(``"battle": "classic"`` on a character keeps the old fight for it). The player brings a deck
(``world.player["deck"]``: card ids), from ``"cards"`` in game.json::

    "cards": {"energy": 3, "hand": 5, "rewards": 3,
              "deck": ["strike", "strike", "defend", ...],
              "decks": {"warrior": [...], "rogue": [...]},
              "enemy_health": 1.0, "enemy_damage": 1.0}

Each turn he gets ``energy`` and draws ``hand`` cards; he plays what he can pay for and ends the turn;
what is left in his hand goes to the discard pile. When the draw pile is empty, the discard pile is
shuffled back into it. Cards come from the game's ``cards.json`` (over the engine's own, below)::

    "bash": {"name": "Bash", "cost": 2, "type": "attack", "rarity": "common",
             "effects": [{"damage": 8}, {"status": "exposed", "turns": 2}]}

Effects, in order: ``damage`` (``times`` over), ``block`` (soaks damage until his next turn),
``draw``, ``energy``, ``heal``, ``status`` (``turns``, ``power``) on the target, ``strength`` (more
damage on every hit, for the fight). ``"target"``: ``"enemy"`` (one, chosen), ``"all"`` or ``"self"``;
``"exhaust": true`` takes the card out for the rest of the fight.

Statuses: ``weak`` (hits a quarter softer), ``exposed`` (takes half again), ``poison``, ``burn``,
``bleed`` (``power`` a turn), ``stun`` (loses its next turn), ``blind`` (hits half as hard).

Enemies fight by their ``moves`` as in the classic battle, and show what they will do, with numbers:
an attack's damage is (4 + its attack) times the move's ``mult``; a guard gives it block (4 + twice
its defence); a heavy move winds up a turn before it lands. An enemy with a ``"deck"`` (and
``"energy"``, ``"hand"``) is a **duellist**: it plays cards as he does, from a hand he cannot see,
and chooses them by Monte Carlo tree search over guesses of what he holds (engine/ai/search.py).

The player's ``attack`` adds to every hit (one for each two points over 5), his ``defense`` takes
from every hit he takes (half of it). A won fight offers ``rewards`` cards, one to add to the deck:
from the character's ``"card_rewards"``, else the game's cards (``"reward": false`` keeps one out;
``"rarity"`` common, uncommon, rare). Effects ``add_card`` and ``remove_card`` change the deck, and
the ``deck`` command shows it.
"""
from __future__ import annotations

from .ai import search
from .combat import STATUS_INFO, Battle, _mid
from .term import truncate

CARDS = {
    "strike": {"name": "Strike", "cost": 1, "type": "attack", "rarity": "starter", "effects": [{"damage": 6}]},
    "defend": {"name": "Defend", "cost": 1, "type": "skill", "rarity": "starter", "effects": [{"block": 5}]},
    "bash": {"name": "Bash", "cost": 2, "type": "attack", "rarity": "starter",
             "effects": [{"damage": 8}, {"status": "exposed", "turns": 2}]},
    "cleave": {"name": "Cleave", "cost": 1, "type": "attack", "target": "all", "effects": [{"damage": 7}]},
    "twin_strike": {"name": "Twin Strike", "cost": 1, "type": "attack", "effects": [{"damage": 5, "times": 2}]},
    "heavy_blow": {"name": "Heavy Blow", "cost": 2, "type": "attack", "effects": [{"damage": 14}]},
    "second_wind": {"name": "Second Wind", "cost": 1, "type": "skill", "effects": [{"block": 7}, {"draw": 1}]},
    "quick_step": {"name": "Quick Step", "cost": 0, "type": "skill", "effects": [{"draw": 2}], "exhaust": True},
    "hamstring": {"name": "Hamstring", "cost": 1, "type": "attack", "effects": [{"damage": 4}, {"status": "weak", "turns": 2}]},
    "envenom": {"name": "Envenom", "cost": 1, "type": "attack",
                "effects": [{"damage": 3}, {"status": "poison", "turns": 3, "power": 3}]},
    "rally": {"name": "Rally", "cost": 1, "type": "power", "rarity": "uncommon", "effects": [{"strength": 2}],
              "exhaust": True},
    "bandage": {"name": "Bandage", "cost": 1, "type": "skill", "rarity": "uncommon", "effects": [{"heal": 7}],
                "exhaust": True},
    "adrenaline": {"name": "Adrenaline", "cost": 0, "type": "skill", "rarity": "rare",
                   "effects": [{"energy": 1}, {"draw": 2}], "exhaust": True},
    "iron_wall": {"name": "Iron Wall", "cost": 2, "type": "skill", "rarity": "uncommon", "effects": [{"block": 14}]},
}
STARTER = ["strike"] * 5 + ["defend"] * 4 + ["bash"]
EFFECTS = ("damage", "times", "block", "draw", "energy", "heal", "status", "turns", "power", "strength")
TARGETS = ("enemy", "all", "self")
TYPES = ("attack", "skill", "power")
RARITY = {"common": 6, "uncommon": 3, "rare": 1}
STATUSES = ("weak", "exposed", "poison", "burn", "bleed", "stun", "blind")
HURTS = ("poison", "burn", "bleed")


# ---------------------------------------------------------------------- #
# the game's cards and decks
# ---------------------------------------------------------------------- #
def table(data):
    """Every card: the engine's, with the game's ``cards.json`` over them."""
    out = {k: dict(v) for k, v in CARDS.items()}
    for cid, c in (getattr(data, "cards", None) or {}).items():
        if isinstance(c, dict):
            out[cid] = dict(c)
    return out


def settings(game):
    c = game.cfg.get("cards")
    return c if isinstance(c, dict) else {}


def wanted(game, ids):
    """Whether the fight with these characters is played with cards."""
    for cid in ids:
        how = (game.world.characters.get(cid) or {}).get("battle")
        if how in ("cards", "classic"):
            return how == "cards"
    how = game.mode_spec.get("battle") or game.cfg.get("battle")
    return how == "cards"


def deck_of(game):
    """The player's deck (made from the game's start deck - his class's, if it has one - the first time)."""
    p = game.world.player
    if not isinstance(p.get("deck"), list):
        cfg = settings(game)
        decks = cfg.get("decks") if isinstance(cfg.get("decks"), dict) else {}
        p["deck"] = list(decks.get(p.get("class")) or cfg.get("deck") or STARTER)
    return p["deck"]


def target_of(card):
    t = card.get("target")
    if t in TARGETS:
        return t
    hostile = any(("damage" in e or "status" in e) for e in card.get("effects") or [] if isinstance(e, dict))
    return "enemy" if hostile else "self"


def describe(card, strength=0):
    """What a card does, in a few words ("Deal 6. Exposed 2."), unless it says it itself (``"text"``)."""
    if card.get("text"):
        return card["text"]
    parts = []
    everyone = target_of(card) == "all"
    for e in card.get("effects") or []:
        if not isinstance(e, dict):
            continue
        if "damage" in e:
            n = int(e["damage"]) + strength
            times = int(e.get("times", 1))
            parts.append("Deal %d%s%s." % (n, " x%d" % times if times > 1 else "", " to all" if everyone else ""))
        if "block" in e:
            parts.append("Block %d." % int(e["block"]))
        if "draw" in e:
            parts.append("Draw %d." % int(e["draw"]))
        if "energy" in e:
            parts.append("+%d energy." % int(e["energy"]))
        if "heal" in e:
            parts.append("Heal %d." % int(e["heal"]))
        if "strength" in e:
            parts.append("+%d strength." % int(e["strength"]))
        if "status" in e:
            name = str(e["status"]).capitalize()
            power = int(e.get("power", 0))
            parts.append("%s %d%s." % (name, int(e.get("turns", 2)), " (%d a turn)" % power if power else ""))
    if card.get("exhaust"):
        parts.append("Exhaust.")
    return " ".join(parts) or "Does nothing."


def problems(data):
    """What is wrong with the game's cards and decks (for --check)."""
    out = []
    cards = table(data)
    for cid, c in (getattr(data, "cards", None) or {}).items():
        where = "card '%s'" % cid
        if not isinstance(c, dict):
            out.append("%s should be an object" % where)
            continue
        cost = c.get("cost", 1)
        if not (isinstance(cost, int) and not isinstance(cost, bool) and 0 <= cost <= 9):
            out.append("%s: cost should be a whole number, 0 to 9" % where)
        if c.get("type", "attack") not in TYPES:
            out.append("%s: type should be one of %s" % (where, ", ".join(TYPES)))
        if c.get("target") is not None and c["target"] not in TARGETS:
            out.append("%s: target should be one of %s" % (where, ", ".join(TARGETS)))
        if c.get("rarity") is not None and c["rarity"] not in tuple(RARITY) + ("starter",):
            out.append("%s: rarity should be starter, common, uncommon or rare" % where)
        effects = c.get("effects")
        if not isinstance(effects, list) or not effects:
            out.append("%s: effects should be a list of what it does" % where)
            continue
        for e in effects:
            if not isinstance(e, dict) or not e:
                out.append("%s: an effect should be an object like {\"damage\": 6}" % where)
                continue
            for k, v in e.items():
                if k not in EFFECTS:
                    out.append("%s: unknown effect '%s' (%s)" % (where, k, ", ".join(EFFECTS)))
                elif k == "status":
                    if v not in STATUSES:
                        out.append("%s: unknown status '%s' (%s)" % (where, v, ", ".join(STATUSES)))
                elif not (isinstance(v, int) and not isinstance(v, bool) and v >= 0):
                    out.append("%s: %s should be a whole number" % (where, k))
    cfg = data.config.get("cards") if isinstance(data.config.get("cards"), dict) else {}
    decks = [("the start deck", cfg.get("deck"))] + [("the %s deck" % k, v) for k, v in (cfg.get("decks") or {}).items()]
    for cid, ch in (data.characters or {}).items():
        if ch.get("deck") is not None:
            decks.append(("character '%s''s deck" % cid, ch["deck"]))
        for r in ch.get("card_rewards") or []:
            if r not in cards:
                out.append("character '%s': card_rewards has an unknown card '%s'" % (cid, r))
        if ch.get("battle") not in (None, "cards", "classic"):
            out.append("character '%s': battle should be \"cards\" or \"classic\"" % cid)
    for where, deck in decks:
        if deck is None:
            continue
        if not isinstance(deck, list) or not deck:
            out.append("%s should be a list of cards" % where)
            continue
        for cid in deck:
            if cid not in cards:
                out.append("%s has an unknown card '%s'" % (where, cid))
    for key in ("energy", "hand", "rewards"):
        if key in cfg and not (isinstance(cfg[key], int) and not isinstance(cfg[key], bool) and 0 <= cfg[key] <= 12):
            out.append("cards: %s should be a whole number, 0 to 12" % key)
    for mid, spec in (data.config.get("modes") or {}).items():
        if isinstance(spec, dict) and spec.get("battle") not in (None, "cards", "classic"):
            out.append("mode '%s': battle should be \"cards\" or \"classic\"" % mid)
    if data.config.get("battle") not in (None, "cards", "classic"):
        out.append("battle should be \"cards\" or \"classic\"")
    return out


# ---------------------------------------------------------------------- #
# the rules: one side hits another
# ---------------------------------------------------------------------- #
def hit(attacker_strength, attacker_status, defender_status, n):
    """The damage one hit of ``n`` does before block: strength, then weak and blind, then exposed."""
    n = max(0, n + attacker_strength)
    if "weak" in attacker_status:
        n = n * 3 // 4
    if "blind" in attacker_status:
        n //= 2
    if "exposed" in defender_status:
        n = n * 3 // 2
    return n


def soak(block, n):
    """(damage through, block left)."""
    taken = min(block, n)
    return n - taken, block - taken


# ---------------------------------------------------------------------- #
# a duel, for the search: two sides, one to play
# ---------------------------------------------------------------------- #
class Duel:
    """A state of a duel between the player and one duellist, for ``search.mcts``: what each side has, and
    whose turn it is. Moves are the cards the side to play can pay for (by id), and ``"end"``."""

    __slots__ = ("sides", "turn", "cards")

    def __init__(self, sides, turn, cards):
        self.sides, self.turn, self.cards = sides, turn, cards

    @staticmethod
    def side(hp, max_hp, block, energy, max_energy, hand, draw, discard, strength, status, hand_size, armour=0,
             foe_attack=0):
        return {"hp": hp, "max": max_hp, "block": block, "energy": energy, "max_energy": max_energy,
                "hand": list(hand), "draw": list(draw), "discard": list(discard), "strength": strength,
                "status": {k: list(v) for k, v in status.items()}, "hand_size": hand_size, "armour": armour,
                "foe_attack": foe_attack}

    def copy(self):
        sides = []
        for s in self.sides:
            t = dict(s)
            t["hand"], t["draw"], t["discard"] = list(s["hand"]), list(s["draw"]), list(s["discard"])
            t["status"] = {k: list(v) for k, v in s["status"].items()}
            sides.append(t)
        return Duel(sides, self.turn, self.cards)

    def done(self):
        return self.sides[0]["hp"] <= 0 or self.sides[1]["hp"] <= 0

    def to_play(self):
        return self.turn                                 # a side plays card after card, then ends its turn

    def moves(self):
        if self.done():
            return []
        s = self.sides[self.turn]
        seen, out = set(), []
        for cid in s["hand"]:
            if cid not in seen and int(self.cards[cid].get("cost", 1)) <= s["energy"]:
                seen.add(cid)
                out.append(cid)
        return out + ["end"]

    def score(self):
        me, foe = self.sides[self.turn], self.sides[1 - self.turn]
        if foe["hp"] <= 0:
            return 1.0
        if me["hp"] <= 0:
            return -1.0
        return (me["hp"] + me["block"] * 0.5) / float(me["max"]) - foe["hp"] / float(foe["max"])

    def play(self, move):
        st = self.copy()
        me, foe = st.sides[st.turn], st.sides[1 - st.turn]
        if move == "end":
            st.end_turn()
            return st
        card = st.cards[move]
        me["hand"].remove(move)
        me["energy"] -= int(card.get("cost", 1))
        for e in card.get("effects") or []:
            st.effect(me, foe, e)
        if not card.get("exhaust"):
            me["discard"].append(move)
        return st

    def effect(self, me, foe, e):
        if "damage" in e:
            for _ in range(int(e.get("times", 1))):
                n = max(0, hit(me["strength"], me["status"], foe["status"], int(e["damage"])) - foe["armour"])
                n, foe["block"] = soak(foe["block"], n)
                foe["hp"] -= n
        if "block" in e:
            me["block"] += int(e["block"])
        if "draw" in e:
            self.draw(me, int(e["draw"]))
        if "energy" in e:
            me["energy"] += int(e["energy"])
        if "heal" in e:
            me["hp"] = min(me["max"], me["hp"] + int(e["heal"]))
        if "strength" in e:
            me["strength"] += int(e["strength"])
        if "status" in e:
            have = foe["status"].get(e["status"])
            turns, power = int(e.get("turns", 2)), int(e.get("power", 0))
            foe["status"][e["status"]] = [max(turns, have[0]) if have else turns, max(power, have[1]) if have else power]

    @staticmethod
    def draw(s, n):
        for _ in range(n):
            if not s["draw"]:
                s["draw"], s["discard"] = s["discard"][::-1], []      # the search's own shuffle: a fixed one
            if not s["draw"]:
                return
            s["hand"].append(s["draw"].pop())

    def end_turn(self):
        me = self.sides[self.turn]
        me["discard"].extend(me["hand"])
        me["hand"] = []
        for name in list(me["status"]):
            turns, power = me["status"][name]
            if name in HURTS:
                me["hp"] -= power
            if turns <= 1:
                del me["status"][name]
            else:
                me["status"][name][0] = turns - 1
        self.turn = 1 - self.turn
        nxt = self.sides[self.turn]
        nxt["block"] = 0
        nxt["energy"] = nxt["max_energy"]
        if "stun" in nxt["status"]:
            nxt["energy"] = 0
        self.draw(nxt, nxt["hand_size"])


def choose(duel, rng, guesses=3, playouts=90, horizon=24):
    """The duellist's next move: Monte Carlo tree search over a few guesses of what it cannot see (the player's
    hand and the order of both draw piles), the visits added up (information-set MCTS, the simple way)."""
    votes = {}
    order = []
    for _ in range(max(1, guesses)):
        g = duel.copy()
        foe = g.sides[1 - g.turn]
        unseen = foe["hand"] + foe["draw"]
        rng.shuffle(unseen)
        foe["hand"], foe["draw"] = unseen[:len(foe["hand"])], unseen[len(foe["hand"]):]
        rng.shuffle(g.sides[g.turn]["draw"])
        for mv, n in search.mcts_visits(g, rng, playouts=playouts, horizon=horizon):
            if mv not in votes:
                order.append(mv)
            votes[mv] = votes.get(mv, 0) + n
    if not votes:
        return "end"
    return max(order, key=lambda mv: (votes[mv], -order.index(mv)))


# ---------------------------------------------------------------------- #
# the fight
# ---------------------------------------------------------------------- #
class CardBattle(Battle):
    """A fight played with cards: the player against one enemy or a group (some of them maybe duellists)."""

    def __init__(self, game, enemy_ids, can_flee=True):
        super().__init__(game, enemy_ids, can_flee)
        self.cards = table(game.data)
        cfg = settings(game)
        self.max_energy = int(cfg.get("energy", 3))
        self.hand_size = int(cfg.get("hand", 5))
        self.energy = 0
        deck = [c for c in deck_of(game) if c in self.cards]
        self.draw_pile = list(deck)
        self.rng.shuffle(self.draw_pile)
        self.hand, self.discard, self.exhausted = [], [], []
        p = self.player
        p.block = 0
        p.strength = max(0, int(p.stats.get("attack", 5)) - 5) // 2
        p.armour = max(0, int(p.stats.get("defense", 0))) // 2
        hp_k, dmg_k = float(cfg.get("enemy_health", 1.0)), float(cfg.get("enemy_damage", 1.0))
        self.dmg_k = dmg_k
        for e in self.enemies:
            e.block = 0
            e.strength = int(e.char.get("strength", 0))
            e.armour = 0
            if hp_k != 1.0:
                e.stats["max_health"] = max(1, int(round(e.max_hp * hp_k)))
                e.hp = e.max_hp
            e.duel = None
            if isinstance(e.char.get("deck"), list) and e.char["deck"]:
                pile = [c for c in e.char["deck"] if c in self.cards]
                self.rng.shuffle(pile)
                e.duel = {"draw": pile, "hand": [], "discard": [], "energy": 0,
                          "max_energy": int(e.char.get("energy", 3)), "hand_size": int(e.char.get("hand", 5))}
        self.played = 0

    # ---- piles ----------------------------------------------------------- #
    def draw(self, n):
        got = 0
        for _ in range(n):
            if not self.draw_pile:
                if not self.discard:
                    break
                self.draw_pile, self.discard = self.discard, []
                self.rng.shuffle(self.draw_pile)
                self.say("You shuffle your discard pile into a new draw pile.", "system")
            self.hand.append(self.draw_pile.pop())
            got += 1
        return got

    # ---- numbers --------------------------------------------------------- #
    def base(self, e):
        return 4 + int(e.stats.get("attack", 5))

    def intent_damage(self, e, intent):
        """What the enemy's move would do to the player, as it stands: shown, and dealt."""
        t = intent.get("type", "attack")
        if t in ("guard", "heal", "stunned", "heavy", "cards"):
            return 0
        mult = float(intent.get("mult", 2.2 if t == "release" else 1.0))
        n = int(round(self.base(e) * mult * self.dmg_k))
        n = hit(e.strength, e.status, self.player.status, n)
        return max(1, n - self.player.armour) if n > 0 else 0

    def guard_block(self, e):
        return 4 + 2 * int(e.stats.get("defense", 0))

    def strike(self, attacker, defender, n, label=None):
        """One hit of ``n`` (before strength): block soaks it first. What got through."""
        n = hit(attacker.strength, attacker.status, defender.status, n)
        if defender.is_player:
            n = max(1, n - defender.armour) if n > 0 else 0
        through, defender.block = soak(defender.block, n)
        defender.hp = defender.hp - through
        if defender.is_player:
            self.say("%s for {damage}%d{/}%s." % (label or "{enemy} hits you", through,
                                                   " (%d blocked)" % (n - through) if n > through else ""),
                     who=attacker)
            self.g.audio.sfx("hurt")
        else:
            self.say("%s {enemy} for {damage}%d{/}%s." % (label or "You hit", through,
                                                          " (%d blocked)" % (n - through) if n > through else ""),
                     who=defender)
            self.g.audio.sfx("hit")
            self.check_fall(defender)
        return through

    # ---- the player's cards ------------------------------------------------ #
    def playable(self, i):
        return 0 <= i < len(self.hand) and int(self.cards[self.hand[i]].get("cost", 1)) <= self.energy

    def play(self, i, target=None):
        """Play the card in hand at ``i`` (at ``target``, an enemy, if it needs one). False if it cannot be."""
        if not self.playable(i):
            return False
        cid = self.hand[i]
        card = self.cards[cid]
        aim = target_of(card)
        if aim == "enemy":
            target = target if target is not None and target.hp > 0 else self.enemy
            if target is None or target.hp <= 0:
                return False
        self.hand.pop(i)
        self.energy -= int(card.get("cost", 1))
        self.played += 1
        p = self.player
        self.say("{key}%s{/}%s" % (card.get("name", cid), (" - " + card["say"]) if card.get("say") else ""), "system")
        self.g.audio.sfx(card.get("sfx") or ("hit" if card.get("type", "attack") == "attack" else "use"))
        for e in card.get("effects") or []:
            if not isinstance(e, dict):
                continue
            victims = [target] if aim == "enemy" else (list(self.alive) if aim == "all" else [])
            if "damage" in e:
                for v in victims:
                    for _ in range(int(e.get("times", 1))):
                        if v.hp > 0:
                            self.strike(p, v, int(e["damage"]))
            if "block" in e:
                p.block += int(e["block"])
                self.say("You have {system}%d{/} block." % p.block, "system")
            if "draw" in e:
                self.draw(int(e["draw"]))
            if "energy" in e:
                self.energy += int(e["energy"])
            if "heal" in e:
                before = p.hp
                p.hp = p.hp + int(e["heal"])
                self.say("You recover {heal}%d{/} health." % (p.hp - before))
            if "strength" in e:
                p.strength += int(e["strength"])
                self.say("Your strength is %d." % p.strength, "system")
            if "status" in e:
                st = {"name": e["status"], "turns": int(e.get("turns", 2)), "power": int(e.get("power", 0))}
                for v in (victims if aim != "self" else []):
                    self.apply_status(v, st)
                if aim == "self":
                    p.add_status(st["name"], st["turns"], st["power"])
        (self.exhausted if card.get("exhaust") else self.discard).append(cid)
        return True

    # ---- the enemies ------------------------------------------------------- #
    def choose_intent(self, e=None):
        e = e or self.enemy
        if getattr(e, "duel", None) is not None:
            if e.has("stun"):
                return {"type": "stunned"}
            d = e.duel
            d["energy"] = d["max_energy"]
            for _ in range(d["hand_size"] - len(d["hand"])):
                if not d["draw"]:
                    d["draw"], d["discard"] = d["discard"], []
                    self.rng.shuffle(d["draw"])
                if d["draw"]:
                    d["hand"].append(d["draw"].pop())
            return {"type": "cards", "name": "its cards"}
        return super().choose_intent(e)

    def intent_text(self, e):
        intent = e.intent or {}
        t = intent.get("type", "attack")
        g = self.ui.g
        name = _mid(intent.get("name") or "")
        if t == "cards":
            d = e.duel
            return "{intent}%s{/} holds %d cards {hint}(%d energy){/}" % (g("arrow"), len(d["hand"]), d["max_energy"])
        if t == "stunned":
            return "{intent}%s{/} {hint}stunned{/}" % g("dot")
        if t == "heavy":
            nxt = dict(intent, type="release")
            return "{intent}%s{/} winding up - next turn %s {error}%d{/}" % (g("arrow"), name or "a heavy blow",
                                                                            self.intent_damage(e, nxt))
        if t == "guard":
            return "{intent}%s{/} guards {hint}(block %d){/}" % (g("shield"), self.guard_block(e))
        if t == "heal":
            return "{intent}%s{/} heals %d" % (g("arrow"), int(intent.get("amount", e.max_hp * 0.2)))
        n = self.intent_damage(e, intent)
        extra = ""
        if t == "status" or intent.get("status"):
            st = intent.get("status", "poison")
            extra = " + %s" % STATUS_INFO.get(st if isinstance(st, str) else st.get("name"), (st,))[0]
        if t == "drain":
            extra = " + drains"
        style = "error" if t == "release" else "damage"
        return "{intent}%s{/} %s {%s}%d{/}%s" % (g("star") if t == "release" else g("arrow"), name or "attack",
                                                style, n, extra)

    def enemy_act(self, e=None, intent=None):
        e = e or self.enemy
        intent = intent or e.intent or {"type": "attack"}
        self.actor = e
        t = intent.get("type", "attack")
        e.last_move_type = t
        if e.has("stun"):
            if t != "stunned":
                self.say("{enemy} is stunned and loses its turn.")
            e.charged = None
            self.spend_stun(e)
            return
        if t == "stunned":
            return
        if t == "cards":
            return self.duellist_turn(e)
        if t == "heavy":
            e.charged = intent
            self.say("{enemy} gathers itself for %s." % (_mid(intent.get("name")) or "a heavy blow"))
            return
        if t == "guard":
            e.block += self.guard_block(e)
            self.say("{enemy} braces: {system}%d{/} block." % e.block)
            return
        if t == "heal":
            amount = int(intent.get("amount", e.max_hp * 0.2))
            e.hp = e.hp + amount
            self.say(intent.get("text") or "{enemy} recovers {heal}%d{/} health." % amount)
            self.g.audio.sfx("heal")
            return
        if t == "release":
            e.charged = None
        name = intent.get("name")
        dealt = self.strike_player(e, intent, "{enemy} hits you with %s" % _mid(name) if name else None)
        if t == "drain" and dealt > 0:
            e.hp = e.hp + max(1, dealt // 2)
        if t == "status" or intent.get("status"):
            sname = intent.get("status", "poison")
            if isinstance(sname, dict):
                sname, turns, power = sname.get("name", "poison"), sname.get("turns", 2), sname.get("power", 3)
            else:
                turns, power = int(intent.get("turns", 3)), int(intent.get("power", 3))
            if self.player.hp > 0:
                self.player.add_status(sname, turns, power)
                self.say("You are {%s}%s{/}." % (STATUS_INFO.get(sname, ("", "gray"))[1],
                                                STATUS_INFO.get(sname, (sname,))[0]))

    def strike_player(self, e, intent, label=None):
        p = self.player
        n = self.intent_damage(e, intent)
        through, p.block = soak(p.block, n)
        p.hp = p.hp - through
        self.say("%s for {damage}%d{/}%s." % ((label or "{enemy} hits you").rstrip("."), through,
                                               " (%d blocked)" % (n - through) if n > through else ""), who=e)
        self.g.audio.sfx("hurt")
        return through

    def duellist_turn(self, e):
        d = e.duel
        for _ in range(12):                              # a turn: card after card, until it ends it
            if e.hp <= 0 or self.player.hp <= 0:
                break
            mv = choose(self.duel_state(e), self.rng)
            if mv == "end" or mv not in d["hand"]:
                break
            card = self.cards[mv]
            d["hand"].remove(mv)
            d["energy"] -= int(card.get("cost", 1))
            self.say("{enemy} plays {key}%s{/}." % card.get("name", mv), who=e)
            for eff in card.get("effects") or []:
                self.enemy_effect(e, card, eff)
            (d["discard"] if not card.get("exhaust") else []).append(mv)
        d["discard"].extend(d["hand"])
        d["hand"] = []

    def enemy_effect(self, e, card, eff):
        p = self.player
        if "damage" in eff:
            for _ in range(int(eff.get("times", 1))):
                if p.hp > 0:
                    self.strike(e, p, int(round(int(eff["damage"]) * self.dmg_k)), label="{enemy} hits you")
        if "block" in eff:
            e.block += int(eff["block"])
        if "draw" in eff:
            d = e.duel
            for _ in range(int(eff["draw"])):
                if d["draw"]:
                    d["hand"].append(d["draw"].pop())
        if "energy" in eff:
            e.duel["energy"] += int(eff["energy"])
        if "heal" in eff:
            e.hp = e.hp + int(eff["heal"])
            self.say("{enemy} recovers {heal}%d{/} health." % int(eff["heal"]), who=e)
        if "strength" in eff:
            e.strength += int(eff["strength"])
        if "status" in eff:
            if target_of(card) == "self":
                e.add_status(eff["status"], int(eff.get("turns", 2)), int(eff.get("power", 0)))
            elif p.hp > 0:
                p.add_status(eff["status"], int(eff.get("turns", 2)), int(eff.get("power", 0)))
                self.say("You are {%s}%s{/}." % (STATUS_INFO.get(eff["status"], ("", "gray"))[1],
                                                STATUS_INFO.get(eff["status"], (eff["status"],))[0]))

    def duel_state(self, e):
        """The duel as the duellist ``e`` sees it, for the search (the player's hand and piles as they are -
        ``choose`` hides what it should not know)."""
        p, d = self.player, e.duel
        st = lambda f: {k: [v["turns"], v.get("power", 0)] for k, v in f.status.items()}   # noqa: E731
        me = Duel.side(e.hp, e.max_hp, e.block, d["energy"], d["max_energy"], d["hand"], d["draw"], d["discard"],
                       e.strength, st(e), d["hand_size"])
        him = Duel.side(p.hp, p.max_hp, p.block, self.max_energy, self.max_energy, [],
                        self.draw_pile + self.hand, self.discard, p.strength, st(p), self.hand_size, armour=p.armour)
        return Duel([him, me], 1, self.cards)

    # ---- statuses ---------------------------------------------------------- #
    def tick_statuses(self, f):
        for name in list(f.status):
            if name == "stun":
                continue
            st = f.status[name]
            if name in HURTS and f.hp > 0:
                dmg = max(1, int(st.get("power", 2)))
                f.hp = f.hp - dmg
                who = "You take" if f.is_player else "{enemy} takes"
                self.say("%s {damage}%d{/} from %s." % (who, dmg, {"poison": "poison", "burn": "the flames",
                                                                  "bleed": "bleeding"}[name]),
                         who=None if f.is_player else f)
            st["turns"] -= 1
            if st["turns"] <= 0:
                del f.status[name]

    # ---- the screen ------------------------------------------------------------ #
    def show_table(self):
        ui = self.ui
        p = self.player
        alive = self.alive
        ui.gap()
        w = 5 if ui.width < 40 else (8 if ui.narrow else 12)
        name_w = max(6, min(max(len(f.name) for f in alive + [p]), 16))
        for i, f in enumerate(alive, 1):
            lead = " %s " % ui.c(str(i), "key") if len(alive) > 1 else " "
            line = self._bar_line(f, name_w, w, lead)
            if f.block:
                line += ui.c(" %s%d" % (ui.g("shield"), f.block), "system")
            note = ui.fmt(self.intent_text(f), "default", ) + ui.fmt(self.status_line(f), "system")
            if ui.width >= 72:
                ui.line(truncate(line + "  " + note, ui.width))
            else:
                ui.line(truncate(line, ui.width))
                ui.line(truncate("     " + note, ui.width))
        line = self._bar_line(p, name_w, w, "   " if len(alive) > 1 else " ")
        if p.block:
            line += ui.c(" %s%d" % (ui.g("shield"), p.block), "system")
        ui.line(truncate(line + ui.fmt(self.status_line(p), "system"), ui.width))
        ui.line(truncate(" " + ui.c("Energy ", "system") + ui.term.paint(ui.g("star") * self.energy, "byellow")
                         + ui.term.paint(ui.g("dot") * max(0, self.max_energy - self.energy), "darkgray")
                         + ui.c("   draw %d  discard %d%s" % (len(self.draw_pile), len(self.discard),
                                                              "  exhausted %d" % len(self.exhausted)
                                                              if self.exhausted else ""), "hint"), ui.width))
        self.show_hand()
        ui._last = "text"

    def show_hand(self):
        ui = self.ui
        if not self.hand:
            ui.line(" " + ui.c("(your hand is empty)", "hint"))
            return
        numw = len(str(len(self.hand)))
        for i, cid in enumerate(self.hand, 1):
            c = self.cards[cid]
            cost = int(c.get("cost", 1))
            can = cost <= self.energy
            head = "%s %s %s" % (ui.c("%*d." % (numw, i), "key" if can else "hint"),
                                 ui.c("(%d)" % cost, "system" if can else "hint"),
                                 ui.c(c.get("name", cid), "item" if can else "hint"))
            ui.line(truncate(" " + head + "  " + ui.c(describe(c, self.player.strength if any(
                "damage" in e for e in c.get("effects") or [] if isinstance(e, dict)) else 0), "hint"), ui.width))

    # ---- the player's turn --------------------------------------------------- #
    HELP = ("Type a card's number to play it ('2', or '2 1' to aim it at enemy 1); 'end' (or 'e', '0') ends "
            "your turn. 'piles' shows your draw and discard piles, 'use' an item (1 energy)%s.")

    def player_turn(self):
        p = self.player
        ui = self.ui
        if p.has("stun"):
            self.say("You are stunned and lose your turn.", "error")
            self.spend_stun(p)
            return
        while self.alive and p.hp > 0 and self.result is None:
            raw = ui.prompt(" Play> ").strip().lower()
            if raw in ("end", "e", "0", "done", "pass", "end turn"):
                return
            if raw == "":
                if not any(self.playable(i) for i in range(len(self.hand))):
                    return
                self.show_hand()
                continue
            words = raw.split()
            if words[0] in ("play", "p") and len(words) > 1:
                words = words[1:]
            if words[0].isdigit():
                i = int(words[0]) - 1
                if not 0 <= i < len(self.hand):
                    self.say("You have %d cards in hand." % len(self.hand), "error")
                    continue
                if not self.playable(i):
                    self.say("Not enough energy for %s." % self.cards[self.hand[i]].get("name", self.hand[i]), "error")
                    continue
                target = None
                if target_of(self.cards[self.hand[i]]) == "enemy":
                    target = self.pick_target(int(words[1]) if len(words) > 1 and words[1].isdigit() else None)
                    if target is None:
                        continue
                self.play(i, target)
                if self.alive and p.hp > 0:
                    self.show_table()
                continue
            if words[0] in ("piles", "pile", "draw", "discard", "deck"):
                self.show_piles()
                continue
            if words[0] in ("use", "item", "items", "u", "i"):
                if self.energy < 1:
                    self.say("Using an item takes 1 energy.", "error")
                    continue
                if self.do_item():
                    self.energy -= 1
                    if self.alive and p.hp > 0:
                        self.show_table()
                continue
            if words[0] in ("flee", "run", "f"):
                if not self.can_flee:
                    self.say("There is no getting away from this one.", "error")
                    continue
                self.try_flee()
                return
            if words[0] in ("help", "?", "h"):
                self.say(self.HELP % (", 'flee' to run" if self.can_flee else ""), "hint")
                continue
            self.say("Play a card by its number, or 'end' your turn ('help' for more).", "error")

    def show_piles(self):
        def counted(ids):
            n = {}
            for c in ids:
                n[c] = n.get(c, 0) + 1
            return ", ".join("%s%s" % (self.cards[c].get("name", c), " x%d" % k if k > 1 else "")
                             for c, k in sorted(n.items(), key=lambda kv: self.cards[kv[0]].get("name", kv[0])))
        self.say("Draw pile (%d, in no order): %s" % (len(self.draw_pile), counted(self.draw_pile) or "-"), "system")
        self.say("Discard pile (%d): %s" % (len(self.discard), counted(self.discard) or "-"), "system")
        if self.exhausted:
            self.say("Exhausted (%d): %s" % (len(self.exhausted), counted(self.exhausted)), "system")

    # ---- the fight ----------------------------------------------------------- #
    def run(self):
        """Fight to the end. Returns "win", "lose" or "fled"."""
        g, ui = self.g, self.ui
        p = self.player
        lead = max(self.enemies, key=lambda f: f.max_hp)
        g.audio.sfx("encounter")
        g.play_music(lead.char.get("battle_music") or g.data.config.get("battle_music")
                     or {"generate": {"mood": "battle", "seed": lead.char.get("template") or lead.cid}}, raw=True)
        ui.rule("%s  %s" % (ui.g("sword"), self.title()))
        self.show_enemy()
        told = set()
        for f in self.enemies:
            intro = f.char.get("battle_intro")
            if intro and intro not in told:
                told.add(intro)
                self.say(intro, "story", who=f)
        if self.round == 0 and not ui.narrow:
            self.say("{hint}A card battle. 'help' tells you how to play.{/}", "default")
        while self.alive and p.hp > 0 and self.result is None:
            self.round += 1
            self.actor = None
            for e in self.alive:
                e.intent = self.choose_intent(e)
            p.block = 0
            self.energy = self.max_energy
            self.draw(self.hand_size)
            self.show_table()
            self.player_turn()
            self.discard.extend(self.hand)
            self.hand = []
            if self.result or not self.alive or p.hp <= 0:
                break
            self.tick_statuses(p)
            if p.hp <= 0:
                break
            for e in self.alive:
                if e.hp <= 0:
                    continue
                e.block = 0
                self.enemy_act(e)
                if p.hp <= 0:
                    break
            if p.hp <= 0:
                break
            for e in self.alive:
                self.actor = e
                self.tick_statuses(e)
                self.check_fall(e)
            self.actor = None
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
            self.reward()
        elif self.result == "lose":
            self.killer = killer
            self.say(killer.char.get("victory_text") or "{enemy} has beaten you.", "error", who=killer)
        if self.result == "lose":
            g.audio.music(None)
        else:
            g.resume_music()
        ui.rule()
        return self.result

    # ---- after a win ------------------------------------------------------------ #
    def offers(self):
        """The cards offered after a win: the enemies' ``card_rewards``, else from the game's (by rarity)."""
        n = int(settings(self.g).get("rewards", 3))
        if n <= 0:
            return []
        named = []
        for e in self.enemies:
            for c in e.char.get("card_rewards") or []:
                if c in self.cards and c not in named:
                    named.append(c)
        if named:
            pool = named
            weights = [1.0] * len(pool)
        else:
            klass = self.g.world.player.get("class")
            pool = [cid for cid, c in self.cards.items() if c.get("reward", True) and c.get("rarity") != "starter"
                    and (not c.get("classes") or klass in c["classes"])]
            weights = [float(RARITY.get(self.cards[c].get("rarity", "common"), 6)) for c in pool]
        out = []
        while pool and len(out) < n:
            r = self.rng.uniform(0, sum(weights))
            for k, (c, wt) in enumerate(zip(pool, weights)):
                r -= wt
                if r <= 0 or k == len(pool) - 1:
                    out.append(c)
                    pool, weights = pool[:k] + pool[k + 1:], weights[:k] + weights[k + 1:]
                    break
        return out

    def reward(self):
        offers = self.offers()
        if not offers:
            return
        ui = self.ui
        labels = ["{item}%s{/} {hint}(%d) %s{/}" % (self.cards[c].get("name", c), int(self.cards[c].get("cost", 1)),
                                                    describe(self.cards[c])) for c in offers]
        pick = ui.menu(labels, title="Take a card for your deck:", cancel_label="Take none", prompt="Card> ")
        if pick is None:
            self.say("You leave them.", "system")
            return
        deck_of(self.g).append(offers[pick])
        self.say("%s goes into your deck (%d cards)." % (self.cards[offers[pick]].get("name"), len(deck_of(self.g))),
                 "success")

    # ---- a player that plays itself (tests, the editor's odds) --------------------- #
    def auto_command(self):
        """A plain, greedy turn: block what is coming if it would hurt, else hit the weakest; 'end' when spent."""
        p = self.player
        alive = self.alive
        if not alive:
            return "end"
        coming = sum(self.intent_damage(e, e.intent or {}) for e in alive)
        best = None
        for i, cid in enumerate(self.hand):
            if not self.playable(i):
                continue
            c = self.cards[cid]
            eff = [e for e in c.get("effects") or [] if isinstance(e, dict)]
            dmg = sum(hit(p.strength, p.status, {}, int(e["damage"])) * int(e.get("times", 1)) for e in eff if "damage" in e)
            if target_of(c) == "all":
                dmg *= len(alive)
            block = sum(int(e["block"]) for e in eff if "block" in e)
            cost = max(1, int(c.get("cost", 1)))
            value = dmg / cost
            if coming > p.block and block:
                value += min(block, coming - p.block) * 1.2 / cost
            if any("draw" in e or "energy" in e for e in eff) and int(c.get("cost", 1)) == 0:
                value += 10
            if any("strength" in e for e in eff) and self.round <= 2:
                value += 8
            if any("heal" in e for e in eff):
                value += 6 if p.hp < p.max_hp * 0.6 else -5
            if any("status" in e for e in eff):
                value += 2
            if best is None or value > best[0]:
                best = (value, i)
        if best is None or best[0] <= 0:
            return "end"
        aim = ""
        if len(alive) > 1 and target_of(self.cards[self.hand[best[1]]]) == "enemy":
            weakest = min(alive, key=lambda f: (f.hp + f.block, f.max_hp))
            aim = " %d" % (alive.index(weakest) + 1)
        return "%d%s" % (best[1] + 1, aim)
