# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Realms (engine/realm.py): the calendar and the tides, names for formulas, works and hands, the
season (yields, hunger, growth), orders, effects, threats told ahead, events and their choices, how a
realm ends, the steward, checks, and the realm starter played at a prompt, saved and loaded."""
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from helpers import Session  # noqa: E402
from engine import realm as R  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.realm import Realm  # noqa: E402
from engine.term import visible_len  # noqa: E402

STARTER = os.path.join(ROOT, "templates", "realm")
HOLD = {
    "name": "Hold",
    "calendar": {"seasons": ["Thaw", "Long Day", "Frost"], "length": 9, "start_year": 3},
    "tides": {"levels": ["Low", "High"], "weights": [1, 1], "forecast": 2},
    "stocks": {"food": {"start": 10, "max": "20 + 10 * barn"}, "wood": 6, "dread": {"start": 0, "show": False}},
    "values": {"watch": {"formula": "1 + 2 * wall + gate_hands", "show": True}},
    "people": {"start": 4, "eats": {"food": 1}, "growth": "0.5 if food >= people else 0", "room": "4 + 2 * hut"},
    "works": {
        "plot": {"start": 1, "staff": 2, "hands": 2, "max": 2, "cost": {"wood": 3}, "yields": {"food": "0 if frost else 3"}},
        "hut": {"cost": {"wood": 2}, "dearer": 0.5, "max": 3},
        "barn": {"cost": {"wood": 4}, "max": 1, "needs": "hut >= 1", "needs_text": "Huts first."},
        "wall": {"cost": {"wood": 5}, "max": 1},
        "gate": {"cost": {"wood": 1}, "max": 1, "hands": 2},
        "lore": {"name": "Old songs", "finding": True, "cost": {"food": 2}, "on_built": [{"set": "sung"}]},
    },
    "threats": {"wolves": {"called": True, "strength": 3, "against": "watch", "swing": 0.001,
                           "on_held": [{"stock": {"food": 1}}], "on_lost": [{"people": -1}]}},
}


def hold(seed=1, **more):
    spec = copy.deepcopy(HOLD)
    spec.update(more)
    return Realm(spec, "hold", seed)


class Data:
    def __init__(self, realms, scenes=None):
        self.realms = realms
        self.scenes = scenes or {}


class CalendarTests(unittest.TestCase):
    def test_seasons_years_and_names_for_formulas(self):
        r = hold()
        self.assertEqual((r.season(), r.year(), r.date()), ("Thaw", 3, "Year 3, Thaw"))
        self.assertEqual((r.season(4), r.year(4)), ("Long Day", 4))
        e = r.env()
        self.assertEqual((e["thaw"], e["long_day"], e["frost"]), (1.0, 0.0, 0.0))
        self.assertEqual((e["people"], e["idle"], e["plot"], e["plot_hands"], e["left"]), (4.0, 2.0, 1.0, 2.0, 9.0))
        self.assertEqual(R.name_of("High Sun"), "high_sun")
        self.assertEqual(e[R.name_of(r.levels[r.tide()])], 1.0)

    def test_the_tide_is_the_same_whoever_asks_and_depends_on_the_seed(self):
        a, b = hold(7), hold(7)
        self.assertEqual([a.tide(t) for t in range(40)], [b.tide(t) for t in range(40)])
        self.assertEqual([a.clone(blind=True).tide(t) for t in range(40)], [a.tide(t) for t in range(40)])
        self.assertNotEqual([a.tide(t) for t in range(40)], [hold(8).tide(t) for t in range(40)])
        self.assertEqual(len(a.forecast()), 3)
        far = hold(7, tides={"levels": ["Low", "High"], "forecast": "1 + 3 * sung"})
        self.assertEqual(len(far.forecast()), 2)
        far.build("lore")                                        # a finding lengthens what is read ahead
        self.assertEqual(len(far.forecast()), 5)
        self.assertEqual(a.forecast()[1], a.levels[a.tide(1)])

    def test_tides_rise_through_the_years_and_with_a_season(self):
        flat = hold(1, tides={"levels": ["a", "b", "c"], "weights": [1, 0, 0]})
        self.assertEqual({flat.tide(t) for t in range(9)}, {0})
        risen = hold(1, tides={"levels": ["a", "b", "c"], "weights": [1, 0, 0], "rise": 2})
        self.assertEqual(risen.tide(0), 0)
        self.assertGreaterEqual(risen.tide(8), 1)
        frost = hold(1, tides={"levels": ["a", "b", "c"], "weights": [1, 0, 0], "by_season": {"Frost": 1}})
        self.assertEqual([frost.tide(t) for t in range(3)], [0, 0, 1])


class SeasonTests(unittest.TestCase):
    def test_works_yield_by_the_hand_people_eat_and_stocks_keep_their_bounds(self):
        r = hold()
        self.assertEqual(r.flows()["food"], 2 * 3 - 4)
        r.end_season()
        self.assertEqual(r.state["stocks"]["food"], 12)
        r.state["stocks"]["food"] = 19
        r.end_season()
        self.assertEqual(r.state["stocks"]["food"], 20)          # its max, without a barn
        self.assertEqual(r.turn, 2)

    def test_hunger_takes_people_and_the_hands_they_were(self):
        r = hold()
        r.state["stocks"]["food"] = 0
        r.state["hands"]["plot"] = 0
        news = r.end_season()
        self.assertEqual(r.state["people"], 2)                   # all of the need unmet: half of them go
        self.assertTrue(any("not enough food" in t for t, _ in news))
        self.assertLessEqual(sum(r.state["hands"].values()), r.state["people"])

    def test_people_grow_while_there_is_room(self):
        r = hold()
        r.state["works"]["hut"] = 1
        for _ in range(2):
            r.end_season()
        self.assertEqual(r.state["people"], 5)
        r.state["works"]["hut"] = 0
        r.state["people"] = 4
        for _ in range(2):
            r.end_season()
        self.assertEqual(r.state["people"], 4)                   # no room

    def test_the_same_orders_play_the_same_years(self):
        def run(seed):
            r = Realm(GameData(STARTER).realms["ford"], "ford", seed)
            R.steward(r)
            return r.state_hash()
        self.assertEqual(run(4), run(4))
        self.assertNotEqual(run(4), run(5))


class OrderTests(unittest.TestCase):
    def test_building_costs_is_dearer_each_time_and_has_a_most(self):
        r = hold()
        self.assertEqual(r.build("hut"), (True, "Hut: built."))
        self.assertEqual(r.state["stocks"]["wood"], 4)
        self.assertIn("order to build is given", r.build("hut")[1])
        r.end_season()
        self.assertEqual(r.cost("hut"), {"wood": 3})             # half as much again
        r.state["works"]["hut"] = 3
        self.assertEqual(r.build("hut"), (False, "There is no room for another."))

    def test_needs_costs_and_findings(self):
        r = hold()
        self.assertEqual(r.build("barn"), (False, "Huts first."))
        self.assertNotIn("barn", [w for w, _ in r.open_works("build")])
        self.assertEqual(r.build("wall")[0], True)
        self.assertEqual(r.build("lore"), (True, "Old songs: known."))      # a finding is its own order
        self.assertIn("sung", r.state["flags"])
        self.assertEqual(r.env()["sung"], 1.0)
        self.assertEqual(r.build("lore"), (False, "It is known already."))
        r.end_season()
        r.state["stocks"]["wood"] = 0
        self.assertEqual(r.build("gate"), (False, "It wants 1 wood more."))

    def test_hands_go_as_far_as_places_and_idle_hands_allow(self):
        r = hold()
        self.assertEqual(r.put("plot", 5), (False, "Plot keeps 2."))
        self.assertEqual(r.put("plot", 0)[1], "Plot: 0 of 2.")
        self.assertEqual(r.idle(), 4)
        self.assertEqual(r.put("hut", 1), (False, "Hut takes no hands."))
        r.state["works"]["plot"] = 2
        r.state["works"]["gate"] = 1
        r.put("plot", 4)
        self.assertEqual(r.put("gate", 2), (False, "Gate keeps 0."))        # no one is idle
        self.assertEqual(r.find_work("pl"), "plot")
        self.assertEqual(r.find_work("old songs"), "lore")
        self.assertIsNone(r.find_work("mill"))


class EffectTests(unittest.TestCase):
    def test_effects_change_stocks_people_works_and_flags(self):
        r = hold()
        news = []
        r.do([{"stock": {"food": "people", "wood": -100}, "say": "A cart comes.", "role": "success"},
              {"people": 1}, {"work": {"hut": 2}}, {"set": ["a", "b"]}, {"clear": "a"},
              {"if": "b", "then": [{"stock": {"dread": 3}}], "else": [{"stock": {"dread": 9}}]},
              {"game": [{"set": "seen_by_the_game"}]}], news)
        s = r.state
        self.assertEqual((s["stocks"]["food"], s["stocks"]["wood"], s["stocks"]["dread"]), (14, 0, 3))
        self.assertEqual((s["people"], s["works"]["hut"], s["flags"]), (5, 2, ["b"]))
        self.assertEqual(news, [("A cart comes.", "success")])
        self.assertEqual(r.outbox, [[{"set": "seen_by_the_game"}]])
        r.do({"random": [[{"set": "x"}], [{"set": "y"}]]}, news)
        self.assertEqual(len(set(s["flags"]) & {"x", "y"}), 1)
        r.do({"lose": "The hold is ash."}, news)
        self.assertEqual((s["result"], s["why"]), ("lost", "The hold is ash."))

    def test_works_lost_take_their_hands(self):
        r = hold()
        r.do({"work": {"plot": -1}}, [])
        self.assertEqual((r.state["works"]["plot"], r.state["hands"]["plot"]), (0, 0))


class ThreatTests(unittest.TestCase):
    def test_a_threat_is_told_a_season_ahead_and_met_by_the_watch(self):
        r = hold()
        news = []
        r.do({"threat": "wolves"}, news)
        self.assertEqual(r.state["coming"], [{"id": "wolves", "strength": 3, "at": 1}])
        self.assertEqual(news[0][1], "warning")
        self.assertEqual(r.odds(r.state["coming"][0]), 0.0)
        text = " ".join(l[1] for l in R.status_lines(r) if l[0] == "text")
        self.assertIn("Wolves: strength 3, in 2 seasons. Watch 1 - no hope of holding.", text)
        r.end_season()
        self.assertEqual(r.state["people"], 4)                   # not yet
        r.state["works"]["wall"] = 1
        self.assertEqual(r.odds(r.state["coming"][0]), 0.5)      # as strong as the watch: either way
        r.state["works"]["gate"] = 1
        self.assertEqual(r.put("gate", 1)[0], True)
        self.assertEqual(r.odds(r.state["coming"][0]), 1.0)
        food = r.state["stocks"]["food"]
        news = r.end_season()
        self.assertEqual(r.state["coming"], [])
        self.assertEqual(r.state["stocks"]["food"], food + 2 + 1)        # the season's, and the held effect's
        self.assertIn(("Wolves came, and the hold stood.", "success"), news)
        self.assertEqual(r.stats()["held"], 1)

    def test_a_threat_that_breaks_in_and_one_that_comes_by_itself(self):
        r = hold()
        r.do({"threat": "wolves"}, [])
        r.end_season()
        r.end_season()
        self.assertEqual((r.state["people"], r.stats()["lost"]), (3, 1))
        spec = copy.deepcopy(HOLD)
        spec["threats"]["wolves"] = {"if": "frost", "chance": 1, "strength": "2 + turn", "warn": 1}
        r = Realm(spec, "hold", 1)
        r.end_season()
        r.end_season()
        self.assertEqual(r.state["coming"], [])
        r.end_season()                                           # the frost ends: sighted
        self.assertEqual(r.state["coming"], [{"id": "wolves", "strength": 4, "at": 3}])


class EventTests(unittest.TestCase):
    def test_events_fire_once_or_every_so_often_and_ask(self):
        asked = []

        def choose(realm, event, options, news):
            asked.append((event["id"], [o["text"] for o in options]))
            return len(options) - 1
        r = hold(events=[
            {"id": "cart", "if": "turn >= 1", "text": "A cart.", "do": [{"stock": {"wood": 2}}]},
            {"id": "toll", "once": False, "every": 3, "text": "The toll.", "choices": [
                {"text": "Pay.", "if": "food >= 100", "do": [{"stock": {"food": -100}}]},
                {"text": "Feast.", "say": "They feast.", "do": [{"stock": {"food": -1}}]},
                {"text": "Refuse.", "do": [{"set": "refused"}]}]},
            {"id": "never", "chance": 0, "do": [{"lose": "no"}]}])
        news = [r.end_season(choose) for _ in range(6)]
        self.assertEqual([t for t, _ in news[0]], [])
        self.assertIn(("A cart.", "story"), news[1])
        self.assertEqual(sum(("A cart.", "story") in n for n in news), 1)
        self.assertEqual(asked, [("toll", ["Feast.", "Refuse."])] * 2)   # the third and the sixth season
        self.assertIn("refused", r.state["flags"])
        self.assertIsNone(r.state["result"])
        r2 = hold(events=r.events)
        for _ in range(3):
            r2.end_season()                                       # no one to ask: the first that may be chosen
        self.assertEqual(r2.state["news"][-1], ["They feast.", "story"])


class EndTests(unittest.TestCase):
    def test_a_realm_stands_at_its_last_season_or_ends_by_a_formula(self):
        r = hold(end_text="Nine seasons.")
        r.state["stocks"]["food"] = 20
        for _ in range(9):
            r.end_season()
        self.assertEqual((r.state["result"], r.state["why"], r.turn), ("won", "Nine seasons.", 9))
        self.assertEqual(r.end_season(), [])
        r = hold(fail_if="wood < 1", fail_text="No wood.")
        r.state["stocks"]["wood"] = 0
        r.end_season()
        self.assertEqual((r.state["result"], r.state["why"]), ("lost", "No wood."))
        r = hold(win_if="hut >= 1")
        r.build("hut")
        r.end_season()
        self.assertEqual(r.state["result"], "won")
        r = hold()
        r.state["people"] = 0
        r.end_season()
        self.assertEqual((r.state["result"], r.state["why"]), ("lost", "No one is left."))
        self.assertEqual(r.worth() < -1e5, True)


class StewardTests(unittest.TestCase):
    def test_trying_things_on_copies_changes_nothing(self):
        r = hold()
        before = r.state_hash()
        R.ahead(r, 5)
        r.clone(blind=True).end_season()
        self.assertEqual(r.state_hash(), before)

    def test_the_steward_keeps_the_starter_standing_and_its_orders_play_back(self):
        spec = GameData(STARTER).realms["ford"]
        for seed in (1, 2, 3):
            journal = []
            r = R.steward(Realm(spec, "ford", seed), journal=journal)
            self.assertEqual(r.state["result"], "won", seed)
            self.assertGreaterEqual(r.state["people"], 8, seed)
            again = Realm(spec, "ford", seed)
            for turn, did in journal:                             # the orders, as a player would type them
                self.assertEqual(again.turn, turn)
                for line in did:
                    verb, rest = line.split(" ", 1)
                    if verb == "put":
                        again.state["hands"][rest.split(" ", 1)[1]] = 0
                for line in did:
                    verb, rest = line.split(" ", 1)
                    if verb == "put":
                        n, wid = rest.split(" ", 1)
                        again.put(wid, int(n))
                    else:
                        self.assertTrue(again.build(rest)[0], line)
                again.end_season(R.answer)
            self.assertEqual(again.state_hash(), r.state_hash(), seed)

    def test_the_steward_feeds_people_before_it_builds(self):
        r = hold()
        R.tend(r)
        self.assertEqual(r.state["hands"]["plot"], 2)
        r.state["stocks"]["wood"] = 30
        for _ in range(6):
            R.tend(r)
            r.end_season(R.answer)
        self.assertGreaterEqual(r.state["people"], 4)
        self.assertGreaterEqual(r.state["works"]["hut"], 1)


class CheckTests(unittest.TestCase):
    def test_the_starter_and_the_hold_have_no_problems(self):
        self.assertEqual(GameData(STARTER).validate(), [])
        self.assertEqual(R.problems(Data({"hold": HOLD})), [])

    def test_what_is_wrong_is_said(self):
        bad = {
            "a": {"calendar": {"seasons": []}, "tides": {"weights": [1]},
                  "stocks": {"food": {"max": "barns * 2"}, "frost": 1},
                  "calendar_": 1,
                  "people": {"eats": {"meat": 1}, "growth": "open('x')"},
                  "works": {"plot": {"yields": {"food": 1}, "cost": {"gold": 1}, "needs": "food >"},
                            "food": {}, "odd": 3},
                  "events": [{"id": "e", "do": [{"stok": {}}, {"threat": "ghosts"}, 4]},
                             {"id": "e", "choices": [{"do": []}]}, "x"],
                  "threats": {"w": {"strength": "claws"}, "v": 1},
                  "score": "glory"},
            "b": 4,
        }
        text = "\n".join(R.problems(Data(bad, {"s": {"realm": "zz"}})))
        for part in ("realm 'a': calendar seasons should be a list of names", "tides need levels",
                     "stock food max reads barns, which nothing gives", "'food' is both a stock and a work",
                     "people eats names 'meat', which is not a stock", "people growth: not allowed",
                     "work 'plot' cost names 'gold'", "work 'plot' needs: cannot read",
                     "work 'plot' yields by the hand, and takes no hands", "work 'odd' should be an object",
                     "event 'e': unknown effect 'stok'", "calls the threat 'ghosts'",
                     "an effect should be an object", "two events are called 'e'", "a choice needs a text",
                     "event '2' should be an object", "threat 'w' strength reads claws",
                     "threat 'w' against reads watch", "threat 'v' should be an object", "score reads glory",
                     "it never ends", "realm 'b' should be an object", "scene 's': unknown realm 'zz'"):
            self.assertIn(part, text)


class PlayTests(unittest.TestCase):
    def game(self, more=None):
        folder = os.path.join(tempfile.mkdtemp(prefix="clio-realm-test-"), "ford")
        shutil.copytree(STARTER, folder)
        self.addCleanup(shutil.rmtree, os.path.dirname(folder), True)
        if more:
            for name, change in more.items():
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as f:
                    blob = json.load(f)
                change(blob)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(blob, f)
        return folder

    def test_the_pages_fit_narrow_screens_in_unicode_and_ascii(self):
        script = ["help", "build", "build huts", "put 1 woodlot", "fields 3", "works", "sky", "find", "e", "1",
                  "news", "", "steward 2", "look"]
        for width, uni in ((40, True), (40, False), (24, False), (100, True)):
            s = Session(os.path.join("templates", "realm"), list(script), seed=3, width=width, unicode=uni)
            text = s.run()
            self.assertLessEqual(max(visible_len(l) for l in text.splitlines()), width, (width, uni))
            self.assertIn("Year 1, Sowing", text)
            self.assertIn("Huts: built.", text)
            if not uni:
                self.assertTrue(text.isascii(), [c for c in text if ord(c) > 127][:5])

    def test_orders_at_the_prompt(self):
        s = Session(os.path.join("templates", "realm"),
                    ["build 4", "build quarry", "put 1 woodlot", "woodlot +1", "put 9 mill", "fly", "e", "3"], seed=3)
        text = s.run()
        for part in ("Huts: built.", "This season's order to build is given already.", "Woodlot: 1 of 2. Idle: 2.",
                     "Woodlot: 2 of 2. Idle: 1.", "Say how many and where", "Orders: end the season",
                     "Traders water their mules", "Year 1, High Sun"):
            self.assertIn(part, text)
        self.assertEqual(s.game.over, "quit")                     # the script ran out: the game is left
        self.assertEqual(s.world.vars["realms"]["ford"]["turn"], 1)
        self.assertEqual(s.world.turn, 1)                         # a season is a turn of the game

    def test_a_save_holds_the_season_and_a_load_goes_on_from_it(self):
        folder = self.game()
        s = Session(folder, ["steward 2", "build huts", "save", "steward 3", "load", "look", "quit"], seed=5)
        text = s.run()
        state = s.world.vars["realms"]["ford"]
        self.assertEqual(state["turn"], 2)
        self.assertEqual(text.count("The Ford  Year 1, Reaping"), 3)      # the page: reached, loaded, looked at
        self.assertIn("Year 1, Sowing. The steward", text)
        self.assertIn("Game saved.", text)
        again = Session(folder, [], seed=99)                      # the title screen offers it, by its season
        self.assertEqual(again.game.resumable(), [("save", "The Ford, season 3")])
        self.assertTrue(again.game.load_slot())
        self.assertEqual(again.world.vars["realms"]["ford"]["turn"], 2)
        self.assertEqual(again.world.vars["realms"]["ford"]["works"]["huts"], state["works"]["huts"])

    def test_a_load_with_nothing_saved_stays_in_the_realm(self):
        s = Session(self.game(), ["load", "e", "3"], seed=3)
        text = s.run()
        self.assertIn("There is no saved game.", text)
        self.assertEqual(s.world.vars["realms"]["ford"]["turn"], 1)

    def test_the_end_of_a_realm_ends_the_game_or_runs_the_scenes_effects(self):
        s = Session(self.game(), ["steward 40"], seed=2)
        text = s.run()
        self.assertEqual(s.game.over, "win")
        self.assertIn("The sixteenth season ends. The ford has held.", text)
        self.assertIn("smoke rises from the roofs", text)
        self.assertTrue(s.world.flags.get("ford_won"))
        self.assertEqual(s.world.vars["seasons"], 16)
        self.assertGreater(s.world.vars["realm_score"], 80)

        def scenes(blob):
            blob[0]["on_realm_lost"] = [{"say": "Only the ford is left."}, {"set": "fell"}]
            blob[0]["exits"] = []

        def realms(blob):
            blob["ford"]["fail_if"] = "turn >= 2"
            blob["ford"]["fail_text"] = "The river takes the bank."
        s = Session(self.game({"scenes.json": scenes, "realms.json": realms}), ["e", "3", "e", "3", "look"], seed=3)
        text = s.run()
        self.assertIn("The river takes the bank.", text)
        self.assertIn("Only the ford is left.", text)
        self.assertTrue(s.world.flags.get("fell"))
        self.assertIn("A shallow crossing", text.split("Only the ford is left.")[1])      # the scene is a scene again

    def test_effects_for_the_game_and_its_triggers_run_each_season(self):
        def realms(blob):
            blob["ford"]["events"] = [{"id": "gift", "text": "A pedlar leaves a knife.",
                                       "do": [{"game": [{"set": "knife_left"}, {"var": ["gifts", "+=", 1]}]}]}]

        def triggers(blob):
            blob.append({"id": "third", "when": {"turns": [">=", 3]}, "do": [{"say": "Three seasons gone."}]})
        folder = self.game({"realms.json": realms})
        with open(os.path.join(folder, "triggers.json"), "w", encoding="utf-8") as f:
            json.dump([{"id": "third", "when": {"turns": [">=", 3]}, "do": [{"say": "Three seasons gone."}]}], f)
        s = Session(folder, ["e", "e", "e"], seed=3)
        text = s.run()
        self.assertTrue(s.world.flags.get("knife_left"))
        self.assertEqual(s.world.vars.get("gifts"), 1)
        self.assertEqual(text.count("Three seasons gone."), 1)

    def test_a_new_game_can_start_in_a_realm_by_its_id(self):
        from engine.game import Game
        from engine.term import Term
        out = io.StringIO()
        term = Term(out=out, inp=lambda p: None, width=80, height=24, color=0, unicode=True, animate=False, env={})
        from test_level_saves import Silent
        g = Game(STARTER, term=term, audio=Silent(), settings={"start_level": "ford", "dev": True})
        g.begin_story()
        self.assertIn("Year 1, Sowing", out.getvalue())

    def test_the_steward_plays_from_the_command_line(self):
        out = io.StringIO()
        old = sys.stdout
        sys.stdout = out
        try:
            code = R.main([STARTER, "2"])
        finally:
            sys.stdout = old
        self.assertEqual(code, 0)
        self.assertIn("ford: stood 2 of 2", out.getvalue())


if __name__ == "__main__":
    unittest.main()
