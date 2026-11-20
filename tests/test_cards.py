# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Card battles (engine/cards.py): a deck, a hand, energy, intents with numbers, duellists that choose their
cards by search, rewards, and The Hollow's Deck mode."""
import json
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import cards  # noqa: E402
from engine.ai import search  # noqa: E402
from engine.cards import CardBattle, Duel  # noqa: E402
from engine.combat import Battle  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.editor.balance import odds  # noqa: E402
from engine.term import strip_ansi  # noqa: E402
from helpers import Session  # noqa: E402

DEPTHS = os.path.join(ROOT, "games", "depths")


def hollow(commands=(), klass="1", seed=1):
    """The Hollow in its Deck mode, a character made: (session, game)."""
    s = Session("depths", ["Tess", klass] + list(commands), mode="cards", seed=seed)
    g = s.game
    g.choose_mode()
    g.create_character(g.cfg["character_creation"])
    s.out.seek(0)
    s.out.truncate(0)
    return s, g


def said(s):
    return strip_ansi(s.out.getvalue())


class RuleTests(unittest.TestCase):
    def test_hits_strength_weak_blind_exposed_and_block(self):
        self.assertEqual(cards.hit(0, {}, {}, 6), 6)
        self.assertEqual(cards.hit(2, {}, {}, 6), 8)
        self.assertEqual(cards.hit(0, {"weak": 1}, {}, 8), 6)
        self.assertEqual(cards.hit(0, {"blind": 1}, {}, 8), 4)
        self.assertEqual(cards.hit(0, {}, {"exposed": 1}, 8), 12)
        self.assertEqual(cards.soak(5, 8), (3, 0))
        self.assertEqual(cards.soak(10, 8), (0, 2))

    def test_cards_say_what_they_do(self):
        t = cards.table(GameData(DEPTHS))
        self.assertEqual(cards.describe(t["strike"]), "Deal 6.")
        self.assertEqual(cards.describe(t["strike"], 2), "Deal 8.")
        self.assertEqual(cards.describe(t["backstab"]), "Deal 7. Bleed 3 (3 a turn).")
        self.assertEqual(cards.describe(t["twin_daggers"]), "Deal 4 x3.")
        self.assertEqual(cards.describe(t["nova"]), "Deal 11 to all.")
        self.assertEqual(cards.describe(t["shield_bash"]), "Deal 7. Stun 1. Exhaust.")
        self.assertEqual(cards.target_of(t["defend"]), "self")
        self.assertEqual(cards.target_of(t["strike"]), "enemy")
        self.assertIn("strike", t)                                 # the engine's own are there too
        self.assertEqual(t["greatsword"]["name"], "Rusted Greatsword")


class BattleTests(unittest.TestCase):
    def battle(self, ids=("bone_rat",), deck=None, **kw):
        s, g = hollow(**kw)
        if deck is not None:
            g.world.player["deck"] = list(deck)
        b = CardBattle(g, list(ids), can_flee=True)
        return s, g, b

    def test_the_deck_hand_and_energy(self):
        s, g, b = self.battle(deck=["strike"] * 6 + ["defend"] * 4)
        self.assertEqual(len(b.draw_pile), 10)
        b.energy = 3
        b.draw(5)
        self.assertEqual((len(b.hand), len(b.draw_pile)), (5, 5))
        rat = b.enemies[0]
        hp = rat.hp
        i = b.hand.index("strike")
        self.assertTrue(b.play(i, rat))
        self.assertEqual(rat.hp, hp - 6 - b.player.strength)
        self.assertEqual((b.energy, len(b.hand), b.discard), (2, 4, ["strike"]))
        b.energy = 0
        self.assertFalse(b.play(0, rat))                           # no energy, no card
        b.discard.extend(b.hand + b.draw_pile)
        b.hand, b.draw_pile = [], []
        b.draw(3)
        self.assertEqual(len(b.hand), 3)                           # the discard pile shuffled back in
        self.assertIn("shuffle your discard pile", said(s))

    def test_block_soaks_an_intent_with_numbers(self):
        s, g, b = self.battle(deck=["defend"] * 10)
        rat = b.enemies[0]
        rat.intent = {"type": "attack", "name": "a snapping bite"}
        n = b.intent_damage(rat, rat.intent)
        self.assertEqual(n, max(1, int(round((4 + rat.stats["attack"]) * 1.1)) - b.player.armour))
        self.assertIn("a snapping bite %d" % n, strip_ansi(g.ui.fmt(b.intent_text(rat))))
        b.player.block = 5
        hp = b.player.hp
        b.enemy_act(rat)
        self.assertEqual(b.player.hp, hp - max(0, n - 5))
        self.assertIn("blocked", said(s))
        rat.intent = {"type": "guard"}
        b.enemy_act(rat)
        self.assertEqual(rat.block, b.guard_block(rat))

    def test_a_heavy_blow_is_shown_a_turn_ahead(self):
        s, g, b = self.battle(("bone_warden",), deck=["defend"] * 10)
        w = b.enemies[0]
        w.duel = None                                              # the warden by its moves, not its deck
        move = next(m for m in w.moves if m["type"] == "heavy")
        w.intent = move
        text = strip_ansi(g.ui.fmt(b.intent_text(w)))
        self.assertIn("winding up - next turn", text)
        self.assertIn(str(b.intent_damage(w, dict(move, type="release"))), text)
        b.enemy_act(w)
        self.assertIsNotNone(w.charged)
        self.assertEqual(b.choose_intent(w)["type"], "release")

    def test_statuses_and_exhaust(self):
        s, g, b = self.battle(deck=["backstab", "shield_bash", "envenom"])
        b.energy = 9
        b.draw(3)
        rat = b.enemies[0]
        rat.stats["max_health"] = rat.stats["health"] = 200
        b.play(b.hand.index("envenom"), rat)
        self.assertEqual(rat.status["poison"]["power"], 3)
        b.play(b.hand.index("shield_bash"), rat)
        self.assertTrue(rat.has("stun"))
        self.assertIn("shield_bash", b.exhausted)
        rat.intent = b.choose_intent(rat)
        self.assertEqual(rat.intent["type"], "stunned")
        hp = rat.hp
        b.tick_statuses(rat)
        self.assertEqual(rat.hp, hp - 3)

    def test_a_whole_fight_typed(self):
        s, g = hollow(["2 1", "1", "end"] * 4 + ["1"] * 20)
        g.world.player["deck"] = ["strike"] * 10
        b = CardBattle(g, ["bone_rat"], can_flee=True)
        b.enemies[0].hp = 10
        self.assertEqual(b.run(), "win")
        text = said(s)
        self.assertIn("Energy", text)
        self.assertIn("Take a card for your deck", text)
        self.assertEqual(len(g.world.player["deck"]), 11)           # the first one offered was taken

    def test_a_fight_plays_itself_the_same_way_twice(self):
        def fight(seed):
            s = Session("depths", ["Tess", "1"], mode="cards", seed=seed)
            g = s.game
            g.choose_mode()
            g.create_character(g.cfg["character_creation"])
            b = CardBattle(g, ["bone_rat", "gloom_bat"], can_flee=False)
            s.queue = []
            s._next = lambda prompt: b.auto_command() if "Play>" in prompt else "1"
            s.term.inp = s._next
            return b.run(), b.player.hp, b.round
        self.assertEqual(fight(3), fight(3))
        self.assertEqual(fight(3)[0], "win")


class DuelTests(unittest.TestCase):
    def test_the_search_takes_a_kill_when_there_is_one(self):
        t = cards.table(GameData(DEPTHS))
        him = Duel.side(9, 80, 0, 3, 3, ["strike", "defend"], ["strike"] * 4, [], 0, {}, 5)
        me = Duel.side(40, 40, 0, 3, 3, ["grounded", "greatsword"], ["greatsword"] * 4, [], 0, {}, 4)
        duel = Duel([him, me], 1, t)
        self.assertEqual(duel.moves(), ["grounded", "greatsword", "end"])
        self.assertEqual(cards.choose(duel, random.Random(1)), "greatsword")
        after = duel.play("greatsword")
        self.assertTrue(after.done())
        self.assertEqual(after.score(), 1.0)                       # for the side to play: it won
        self.assertEqual(duel.sides[0]["hp"], 9)                   # play() leaves the state it was given

    def test_the_turn_passes_and_hands_are_drawn(self):
        t = cards.table(GameData(DEPTHS))
        him = Duel.side(50, 80, 0, 3, 3, [], ["strike"] * 6, [], 0, {}, 5)
        me = Duel.side(40, 40, 7, 0, 3, ["grounded"], [], ["greatsword"] * 3, 0, {"burn": [2, 5]}, 4)
        duel = Duel([him, me], 1, t).play("end")
        self.assertEqual(duel.turn, 0)
        self.assertEqual(duel.sides[1]["hp"], 35)                  # its burn, at the end of its turn
        self.assertEqual(len(duel.sides[0]["hand"]), 5)
        self.assertEqual(duel.sides[0]["energy"], 3)

    def test_mcts_visits(self):
        t = cards.table(GameData(DEPTHS))
        duel = Duel([Duel.side(50, 80, 0, 3, 3, [], ["strike"] * 6, [], 0, {}, 5),
                     Duel.side(40, 40, 0, 3, 3, ["grounded", "greatsword", "crowns_fire"], ["greatsword"] * 4, [],
                               0, {}, 4)], 1, t)
        visits = search.mcts_visits(duel, random.Random(4), playouts=60)
        self.assertEqual([mv for mv, _n in visits], ["grounded", "greatsword", "crowns_fire", "end"])
        self.assertEqual(sum(n for _mv, n in visits), 60)

    def test_a_duellist_plays_its_own_deck(self):
        s, g = hollow()
        b = CardBattle(g, ["hollow_king"], can_flee=False)
        king = b.enemies[0]
        self.assertIsNotNone(king.duel)
        king.intent = b.choose_intent(king)
        self.assertEqual(king.intent["type"], "cards")
        self.assertEqual(len(king.duel["hand"]), 4)
        self.assertIn("holds 4 cards", strip_ansi(g.ui.fmt(b.intent_text(king))))
        hp = b.player.hp
        b.enemy_act(king)
        text = said(s)
        self.assertIn("The Hollow King plays", text)
        names = {c["name"] for c in cards.table(g.data).values()}
        played = [line.split("plays ")[1].rstrip(".") for line in text.splitlines() if "plays " in line]
        self.assertTrue(played and all(p in names for p in played))
        self.assertEqual(king.duel["hand"], [])
        self.assertTrue(b.player.hp < hp or king.block > 0 or king.hp > king.max_hp)


class GameTests(unittest.TestCase):
    def test_the_mode_chooses_the_battle(self):
        s, g = hollow()
        self.assertTrue(cards.wanted(g, ["bone_rat"]))
        g.world.characters["bone_rat"]["battle"] = "classic"
        self.assertFalse(cards.wanted(g, ["bone_rat"]))
        story = Session("depths", ["Tess", "1"], mode="story").game
        self.assertFalse(cards.wanted(story, ["bone_rat"]))
        story.world.characters["bone_rat"]["battle"] = "cards"
        self.assertTrue(cards.wanted(story, ["bone_rat"]))

    def test_class_decks_the_deck_command_and_effects(self):
        s, g = hollow(klass="3")
        deck = cards.deck_of(g)
        self.assertEqual(sorted(set(deck)), ["defend", "firebolt", "mend", "strike"])
        g.execute("deck")
        self.assertIn("Your deck (10 cards)", said(s))
        self.assertIn("2x (1) Firebolt", said(s))
        from engine import conditions
        conditions.run([{"add_card": "nova"}, {"remove_card": "mend"}], g)
        self.assertIn("nova", deck)
        self.assertNotIn("mend", deck)
        self.assertIn("Nova goes into your deck", said(s))

    def test_rewards_come_from_the_classes_pool_or_the_enemy(self):
        s, g = hollow(klass="2")
        b = CardBattle(g, ["bone_rat"])
        offers = b.offers()
        self.assertEqual(len(offers), 3)
        t = b.cards
        for c in offers:
            self.assertNotEqual(t[c].get("rarity"), "starter")
            self.assertIsNot(t[c].get("reward", True), False)
            self.assertIn(g.world.player["class"], t[c].get("classes") or [g.world.player["class"]])
        g.world.characters["bone_rat"]["card_rewards"] = ["nova", "ward"]
        b = CardBattle(g, ["bone_rat"])
        self.assertEqual(sorted(b.offers()), ["nova", "ward"])

    def test_the_hollow_can_be_won_with_cards(self):
        from bot import DepthsBot
        wins = [DepthsBot(seed=seed, klass=1, mode="cards").play(900) for seed in (1, 2)]
        self.assertIn("win", wins)

    def test_the_editors_odds_play_card_battles(self):
        r = odds(DEPTHS, ["bone_rat"], level=1, fights=3, mode="cards")
        self.assertEqual({row["wins"] for row in r["rows"]}, {1.0})

    def test_classic_fights_stay_classic(self):
        s = Session("depths", ["Tess", "1"], mode="story")
        g = s.game
        g.choose_mode()
        g.create_character(g.cfg["character_creation"])
        self.assertIs(type(Battle(g, ["bone_rat"])), Battle)
        self.assertFalse(isinstance(g.world.player.get("deck"), list))

    def test_checks(self):
        data = GameData(DEPTHS)
        data.cards = dict(data.cards)
        data.cards["bad"] = {"name": "Bad", "cost": 12, "type": "spell", "target": "everyone",
                             "effects": [{"damage": "lots"}, {"status": "confused"}, {"jump": 1}]}
        data.config = dict(data.config, cards=dict(data.config["cards"], deck=["strike", "nothing"]))
        data.characters = dict(data.characters)
        data.characters["bone_rat"] = dict(data.characters["bone_rat"], battle="poker", deck=["ghost"])
        got = "\n".join(data.validate())
        for words in ("card 'bad': cost should be a whole number, 0 to 9", "card 'bad': type should be one of",
                      "card 'bad': target should be one of", "card 'bad': damage should be a whole number",
                      "card 'bad': unknown status 'confused'", "card 'bad': unknown effect 'jump'",
                      "the start deck has an unknown card 'nothing'", "character 'bone_rat''s deck has an unknown card 'ghost'",
                      "character 'bone_rat': battle should be \"cards\" or \"classic\""):
            self.assertIn(words, got)
        self.assertEqual(GameData(DEPTHS).validate(), [])
        json.dumps(cards.CARDS)


if __name__ == "__main__":
    unittest.main()
