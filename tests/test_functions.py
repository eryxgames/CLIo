# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Functions (engine/sim.py): what a console does when asked - at a key at once, when the key has been
held, switched on and off; locked, lasting, waiting, used up; what one sets, adds and keeps; the values
formulas read of it; the same keys doing the same again; the autopilot using them; how they are shown in
the column, on a screen of panels and when typed; what a scene gets of them; checks; and the station
starter's."""
import io
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import panels as P  # noqa: E402
from engine import sim as S  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.keys import PRESS, RELEASE, REPEAT  # noqa: E402
from engine.realtime import Controls, replay  # noqa: E402
from engine.sim import Sim  # noqa: E402
from engine.term import Term, strip_ansi  # noqa: E402

STATION = os.path.join(ROOT, "templates", "station")
CORE = {"mode": "systems", "time": 300,
        "controls": {"rods": {"keys": ["up", "down"], "min": 0, "max": 100, "start": 50, "step": 20}},
        "systems": {"heat": {"rate": "rods * 2 - 20", "start": 100, "min": 0, "max": 1000},
                    "reserve": {"rate": "-10 * pumps", "start": 20, "min": 0, "max": 100},
                    "double": {"value": "heat * 2"}},
        "functions": {
            "scram": {"label": "Scram", "key": "x", "hold": 1, "lasts": 3, "cooldown": 2, "keeps": {"rods": 0},
                      "tone": "hot", "words": {"on": "RODS IN"}, "says": "Rods in."},
            "vent": {"label": "Vent steam", "key": "V", "if": "heat > 150", "why": "the core is cool",
                     "add": {"heat": -100}, "cooldown": 5, "sound": "hiss"},
            "pumps": {"label": "Reserve pumps", "key": "r", "toggle": True, "if": "reserve > 0",
                      "why": "the reserve is spent", "says_off": "Pumps off."},
            "beacon": {"label": "Deploy beacon", "hold": 2, "uses": 1, "set": {"heat": "heat / 2", "rods": 500}}},
        "win_if": "heat >= 999"}
PLAIN = dict(CORE, systems={"heat": CORE["systems"]["heat"], "double": CORE["systems"]["double"]})
FIELD = ["####################",
         "#..................#",
         "#..@......1........#",
         "#..................#",
         "####################"]


def sim(spec=CORE, **more):
    s = Sim(dict(spec, **more))
    s.paused = None
    return s


def hold(s, keys=(), seconds=1.0):
    """The keys held for so long (the first tick: pressed)."""
    before = s.__dict__.get("_held", frozenset())
    now = frozenset([keys] if isinstance(keys, str) else keys)
    for i in range(int(round(seconds * s.rate))):
        s.step(Controls(s.tick, now, sorted(now - before) if i == 0 else (), sorted(before - now) if i == 0 else ()))
        before = now
    s.__dict__["_held"] = now
    return s


def words(s):
    return {f["id"]: S.function_word(f, unicode=False) for f in s.shown_functions()}


class FunctionTests(unittest.TestCase):
    def test_at_a_key_at_once_and_once_a_press(self):
        s = sim()
        self.assertEqual([(f.name, f.key) for f in s.functions],
                         [("scram", "x"), ("vent", "v"), ("pumps", "r"), ("beacon", "1")])   # no key: a digit
        hold(s, "v", 0.5)                                    # the core is cool: it is locked, and says why
        self.assertEqual((words(s)["vent"], s.note[0], s.function("vent").done), ("LOCKED", "Vent steam: the core is cool.", 0))
        s.step(Controls(s.tick, frozenset(["v"])))
        self.assertEqual(s.events, [])                       # still down: asked once
        hold(s, (), 3.0)                                     # 80 a second: hot enough now
        heat = s.env()["heat"]
        self.assertGreater(heat, 150)
        self.assertEqual(words(s)["vent"], "READY")
        s.step(Controls(s.tick, frozenset(["v"]), ("v",)))
        self.assertEqual(s.events, ["hiss"])                 # its own sound
        self.assertAlmostEqual(s.env()["heat"], heat - 100 + 80 / 20.0, places=6)
        self.assertEqual((s.env()["vent_done"], words(s)["vent"], s.note[0]), (1.0, "DONE", "Vent steam."))
        self.assertTrue(s.shown_functions(["vent"])[0]["flash"])
        hold(s, "v", 2.0)                                    # held on: it is not done again
        self.assertEqual((s.function("vent").done, words(s)["vent"]), (1, "WAIT 3 s"))
        self.assertAlmostEqual(s.env()["vent_wait"], 3.0, places=6)
        hold(s, (), 0.1)
        hold(s, "v", 0.1)                                    # asked again too soon
        self.assertEqual((s.function("vent").done, s.note[0]), (1, "Vent steam: ready in 3 s."))
        hold(s, (), 0.1)
        s.step(Controls(s.tick, frozenset(["v"]), ("v",)))
        self.assertEqual(s.events, ["refused"])
        hold(s, (), 3.0)
        hold(s, "v", 0.1)
        self.assertEqual(s.function("vent").done, 2)

    def test_held_until_it_is_done(self):
        s = sim()
        hold(s, "x", 0.5)
        self.assertEqual((words(s)["scram"], s.env()["scram_charge"], s.env()["scram"]), ("###--- HOLD", 0.5, 0.0))
        hold(s, (), 0.15)                                    # let go early: it falls back
        self.assertAlmostEqual(s.env()["scram_charge"], 0.2, places=6)
        hold(s, (), 0.2)
        self.assertEqual((s.env()["scram_charge"], words(s)["scram"]), (0.0, "READY"))
        hold(s, "x", 0.95)
        self.assertEqual(s.function("scram").done, 0)
        hold(s, "x", 0.05)                                   # a second of it: done
        self.assertEqual((s.function("scram").done, s.env()["scram"], s.note), (1, 1.0, ("Rods in.", "hurt", s.note[2])))
        self.assertEqual(words(s)["scram"], "RODS IN 3 s")   # a word of its own while it is on
        hold(s, "x", 3.5)                                    # the key still down: over, waiting, and not begun again
        self.assertEqual((s.function("scram").done, s.env()["scram"], s.env()["scram_charge"]), (1, 0.0, 0.0))
        hold(s, (), 2.0)
        hold(s, "x", 1.0)
        self.assertEqual(s.function("scram").done, 2)

    def test_what_is_on_keeps_what_it_keeps_and_is_over_in_its_time(self):
        s = sim()
        hold(s, "x", 1.0)
        self.assertEqual(s.env()["rods"], 0.0)
        hold(s, "up", 2.0)                                   # the rods will not come out while it lasts
        self.assertEqual((s.env()["rods"], s.env()["scram"]), (0.0, 1.0))
        self.assertAlmostEqual(s.env()["scram_left"], 1.0, places=6)
        hold(s, "up", 1.0)                                   # over: a tick of the key moves them again
        self.assertEqual((s.env()["scram"], s.env()["rods"]), (0.0, 1.0))
        self.assertEqual(words(s)["scram"], "WAIT 2 s")
        self.assertIn("function_off", S.Runner.SOUNDS)

    def test_a_switch_goes_on_and_off_and_off_by_itself(self):
        s = sim()
        hold(s, "r", 0.3)
        self.assertEqual((words(s)["pumps"], s.env()["pumps"], s.env()["pumps_done"]), ("ON", 1.0, 1.0))
        hold(s, (), 0.2)
        hold(s, "r", 0.3)                                    # the next press: off
        self.assertEqual((words(s)["pumps"], s.env()["pumps"], s.note[0]), ("OFF", 0.0, "Pumps off."))
        self.assertAlmostEqual(s.env()["reserve"], 15.0, places=6)
        hold(s, (), 0.2)
        hold(s, "r", 0.1)
        hold(s, (), 1.6)                                     # the reserve runs out under it
        self.assertEqual((words(s)["pumps"], s.env()["reserve"], s.note[0]),
                         ("LOCKED", 0.0, "Reserve pumps: off - the reserve is spent."))
        hold(s, "r", 0.1)
        self.assertEqual((s.env()["pumps"], s.note[0]), (0.0, "Reserve pumps: the reserve is spent."))

    def test_what_it_sets_and_adds_within_bounds_and_how_often(self):
        s = sim()
        heat = s.env()["heat"] + 2.05 * 80
        hold(s, "1", 2.05)
        self.assertEqual((s.function("beacon").done, s.function("beacon").fired), (1, s.tick - 1))
        # set from the values as they were when it was done (2 s in), and the control kept within its bounds
        self.assertEqual(s.env()["rods"], 100.0)
        self.assertLess(abs(s.env()["heat"] - (heat - 80 * 0.05) / 2.0), 20.0)
        self.assertEqual((words(s)["beacon"], s.function("beacon").why_not()), ("DONE", "there is no more of it"))
        hold(s, (), 1.0)
        self.assertEqual(words(s)["beacon"], "SPENT")        # one use, and it is spent
        hold(s, "1", 2.5)
        self.assertEqual((s.function("beacon").done, s.env()["beacon_charge"]), (1, 0.0))
        v = Sim({"map": FIELD, "functions": {"patch": {"key": "f", "add": {"damage": -30, "fuel": "0 - fuel / 2"}}}})
        v.paused = None
        v.damage, fuel = 50.0, v.fuel
        hold(v, "f", 0.1)
        self.assertEqual(v.damage, 20.0)
        self.assertLess(abs(v.fuel - fuel / 2.0), 0.1)
        self.assertEqual(S.Sim({"map": FIELD}).stats().get("functions"), None)
        self.assertEqual(s.stats()["functions"], {"scram": 0, "vent": 0, "pumps": 0, "beacon": 1})

    def test_the_key_that_begins_it_does_nothing_else(self):
        s = Sim(CORE)
        self.assertEqual(s.paused, "ready")
        hold(s, "r", 0.5)                                    # any key begins it - this one a switch's
        self.assertEqual((s.paused, s.env()["pumps"]), (None, 0.0))
        hold(s, "x", 0.1)
        s.step(Controls(s.tick, frozenset(["p", "x"]), ("p",)))
        self.assertEqual(s.paused, "paused")
        for _ in range(40):
            s.step(Controls(s.tick, frozenset(["x"])))       # held while it is paused, and on after
        s.step(Controls(s.tick, frozenset(["x", "enter"]), ("enter",)))
        hold(s, "x", 2.0)
        self.assertEqual((s.function("scram").done, s.env()["scram_charge"]), (0, 0.0))
        hold(s, (), 0.1)
        hold(s, "x", 1.0)
        self.assertEqual(s.function("scram").done, 1)

    def test_the_same_keys_do_the_same_again(self):
        by, tick = {}, 0                                     # keys as a terminal sends them: down, repeats, up
        plan = [((), 3.0), ("v", 0.2), ("x", 0.6), ((), 0.2), ("x", 1.1), ("r", 0.3), (("up", "1"), 2.2), ((), 1.0)]
        for keys, secs in plan:
            keys = [keys] if isinstance(keys, str) else list(keys)
            n = int(round(secs * 20))
            for i in range(n):
                kind = PRESS if i == 0 else (REPEAT if i % 2 == 0 else None)
                if kind:
                    by.setdefault(tick + i, []).extend([k, kind] for k in keys)
            tick += n
            by.setdefault(tick, []).extend([k, RELEASE] for k in keys)
        journal = [[t, evs] for t, evs in sorted(by.items()) if evs]
        a, b, c, d = sim(), sim(), sim(), sim()
        replay(a, journal, exact=True)
        self.assertEqual(a.stats()["functions"], {"scram": 1, "vent": 1, "pumps": 1, "beacon": 1})
        replay(b, journal, exact=True)
        self.assertEqual(b.state_hash(), a.state_hash())
        replay(c, journal, exact=False)                      # where held keys are guessed from their repeats, too
        self.assertEqual(c.stats()["functions"], a.stats()["functions"])
        replay(d, [[t, [e for e in evs if e[0] != "r"]] for t, evs in journal], exact=True)
        self.assertEqual((d.env()["heat"], d.env()["rods"]), (a.env()["heat"], a.env()["rods"]))
        self.assertNotEqual(d.state_hash(), a.state_hash())  # what the functions are is part of where it is
        twin = a.clone()
        self.assertEqual((twin.state_hash(), twin.data is a.data), (a.state_hash(), True))
        hold(twin, (), 0.5)                                  # a copy goes its own way
        self.assertEqual((twin.function("vent").wait, a.function("vent").wait), (0, 8))


class AutopilotTests(unittest.TestCase):
    def test_the_autopilot_does_what_helps(self):
        spec = {"mode": "systems", "time": 40,
                "controls": {"gain": {"keys": ["up", "down"], "min": 0, "max": 10, "start": 0, "step": 5}},
                "systems": {"signal": {"rate": "gain * (1 + 2 * boost)", "start": 0, "min": 0, "max": 100}},
                "functions": {"boost": {"key": "b", "toggle": True},
                              "dump": {"key": "d", "set": {"signal": 0}},
                              "send": {"key": "s", "hold": 2.5, "if": "signal >= 100", "uses": 1}},
                "win_if": "send_done >= 1", "score": "signal"}
        s = Sim(spec)
        journal = S.fly(s)
        self.assertEqual((s.result, s.stats()["functions"]), ("won", {"boost": 1, "dump": 0, "send": 1}))
        self.assertLess(s.ticks / 20.0, 12)                  # with the boost: a third of the time
        again = Sim(spec)
        replay(again, journal, exact=True, ticks=60)
        self.assertEqual((again.result, again.stats()), ("won", s.stats()))
        slow = Sim(dict(spec, functions={"send": spec["functions"]["send"]}))
        S.fly(slow)
        self.assertEqual(slow.result, "won")
        self.assertGreater(slow.ticks, s.ticks)

    def test_a_function_the_pilot_is_told_to_do(self):
        spec = {"map": FIELD, "vehicle": {"heading": 90},
                "functions": {"lamp": {"key": "l", "hold": 1, "if": "passed >= 1", "uses": 1, "pilot": True}},
                "goal": "survive", "time": 30, "win_if": "lamp_done >= 1"}
        s = Sim(spec)
        journal = S.fly(s)
        self.assertEqual((s.result, s.function("lamp").done), ("won", 1))
        self.assertIn("l", [n for _t, evs in journal for n, _k in evs])
        self.assertLess(s.ticks / 20.0, 12)
        without = Sim(dict(spec, functions={"lamp": dict(spec["functions"]["lamp"], pilot=False)},
                           win_if="lamp_done >= 1", goal="checkpoints", time=8))
        S.fly(without)
        self.assertEqual(without.function("lamp").done, 0)


class ShownTests(unittest.TestCase):
    def test_in_the_column_and_under_it(self):
        s = sim()
        hold(s, "x", 0.5)
        lines = dict((t.split("  ")[0].strip(), (t, role)) for t, role in S.panel_lines(s, 40, unicode=False))
        text = "\n".join(t for t, _ in S.panel_lines(s, 40, unicode=False))
        self.assertIn("X   Scram                    ###--- HOLD", text)
        self.assertIn("V   Vent steam                    LOCKED", text)
        self.assertIn("R   Reserve pumps                    OFF", text)
        self.assertIn("1   Deploy beacon                  READY", text)
        self.assertEqual(lines["X"][1], "hurt")              # a hot one, while it is held
        self.assertEqual(lines["V"][1], "dim")
        self.assertEqual(S.help_line(s), "rods up/down  hold X scram  V vent steam  R reserve pumps  hold 1 deploy "
                                          "beacon   P pause")
        self.assertIn("█", S.function_word({"state": "hold", "charge": 0.5}))
        self.assertEqual(S.function_word({"state": "spent"}), "SPENT")
        rows = S.Runner(s).rows(80, 24, 3, True)             # no panels: the column, on the screen
        self.assertIn("Scram", "\n".join(strip_ansi(r) if isinstance(r, str) else "".join(c[0] or " " for c in r)
                                         for r in rows))

    def test_on_a_screen_of_panels(self):
        layout = {"colour": "green", "cols": [{"title": "DOES", "widgets": [{"gauge": "heat", "max": 1000},
                                                                           {"functions": True}]},
                                              {"title": "SOME", "widgets": [{"functions": ["beacon", "scram", "none"],
                                                                             "keys": False}]}]}
        s = sim(panels=layout)
        hold(s, "x", 0.5)
        runner = S.Runner(s)
        rows = runner.panel_rows(80, 12, 3, True, None)
        text = ["".join(c[0] or " " for c in r) for r in rows]
        self.assertIn("[X] SCRAM ············· ████░░░ HOLD", text[2])
        self.assertIn("[V] VENT STEAM ·············· LOCKED", text[3])
        self.assertIn("[R] RESERVE PUMPS ·············· OFF", text[4])
        self.assertIn("[1] DEPLOY BEACON ············ READY", text[5])
        self.assertIn("│ DEPLOY BEACON ················ READY │", text[1])      # those named, in that order, no keys
        self.assertIn("│ SCRAM ················· ████░░░ HOLD │", text[2])
        at = text[2].index("SCRAM")
        self.assertEqual(rows[2][at][1], P.TONES["hot"])     # held: in its tone
        self.assertEqual(rows[3][text[3].index("VENT")][1], rows[3][text[3].index("LOCKED")][1])
        self.assertLess(sum(rows[3][text[3].index("VENT")][1]), sum(rows[5][text[5].index("DEPLOY")][1]))   # locked: dim
        hold(s, "x", 0.5)                                    # done: its line is lit for a moment
        lit = runner.panel_rows(80, 12, 3, True, None)
        self.assertEqual(lit[2][at][2], P.TONES["hot"])
        self.assertIn("RODS IN 3 s", "".join(c[0] or " " for c in lit[2]))
        hold(s, (), 0.5)
        self.assertIsNone(runner.panel_rows(80, 12, 3, True, None)[2][at][2])
        plain = ["".join(c[0] or " " for c in r) for r in runner.panel_rows(80, 12, 0, False, None)]
        self.assertIn("[X] SCRAM .............. RODS IN 3 s", plain[2])
        self.assertTrue(all(ord(ch) < 128 for line in plain for ch in line))
        self.assertEqual(P.problems(layout, {"heat"}, "p", S.formula, functions={"scram", "beacon"}),
                         ["p col 2 widget 1: there is no function called 'none'"])
        self.assertEqual(P.problems({"widgets": [{"functions": True}, {"functions": 3}]}, set(), "p", functions=set()),
                         ["p widget 1: there are no functions to list",
                          "p widget 2: \"functions\" should be true (all of them) or a list of their names"])
        self.assertEqual(P.problems(P.SAMPLE), [])
        view = P.View({"widgets": [{"functions": True}]})    # none given: nothing drawn, nothing wrong
        self.assertEqual(view.plain(30, 4, {})[1].strip("│ "), "")

    def test_typed(self):
        s = Sim(dict(CORE, win_if="beacon_done >= 1"))
        said = []
        lines = iter(["wait 3", "vent", "vent", "x 0.5", "scram", "status", "deploy", "quit"])
        self.assertEqual(S.play_text(s, said.append, lambda p: next(lines, None)), "won")
        text = "\n".join(said)
        self.assertIn("Functions: scram (x, held 1 s), vent (v), pumps (r), beacon (1, held 2 s). Type a function's "
                      "name, or its key.", text)
        self.assertIn("Vent steam.", text)
        self.assertIn("Vent steam: ready in", text)          # typed again: a key pressed afresh, and refused
        self.assertIn("X   Scram", text)
        self.assertEqual(s.stats()["functions"], {"scram": 1, "vent": 1, "pumps": 0, "beacon": 1})


class GameTests(unittest.TestCase):
    def test_problems_are_said(self):
        class D:
            config = {}
            scenes = {}
            sims = {"a": dict(PLAIN, functions={
                "heat": {"key": "h"}, "ok": {"key": "x"}, "two": {"key": "X"}, "arrow": {"key": "up"}, "stop": {"key": "p"},
                "tap": {"key": "t", "hold": 0.3, "lasts": -1, "uses": "many"},
                "both": {"key": "b", "toggle": True, "hold": 1, "tone": "pink", "words": {"gone": "X"}},
                "bad": {"key": "c", "if": "nope > 1", "set": {"double": 1, "rods": "open(1)"}, "add": 4,
                        "keeps": {"rods": 0}, "effects": "say"},
                "my-name": {"key": "m"}, "list": [], "free": {}}),
                    "b": {"map": FIELD, "functions": {"jump": {"key": "space"}, "fix": {"key": "f", "add": {"damage": -1}}}},
                    "c": dict(PLAIN, functions=[]),
                    "d": dict(PLAIN, functions={"rods_done": {"key": "z"}, "q": {"key": "y"}, "q_left": {"key": "u"}},
                              systems={"heat": {"rate": "q_done + q_wait + q_charge + q + q_lef"}})}
        text = "\n".join(S.problems(D()))
        for bit in ("sim 'a': function 'heat': there is already a value called heat",
                    "function 'two': the key 'x' is function 'ok''s",
                    "function 'arrow': the key 'up' is control 'rods''s",
                    "function 'stop': the key 'p' is the simulator's own",
                    "function 'tap': a hold under 0.75 seconds is done by a tap",
                    "function 'tap': \"lasts\" should be a number, 0 or more",
                    "function 'tap': \"uses\" should be a number, 0 or more",
                    "function 'both': a switch (\"toggle\") is not held",
                    "function 'both': unknown tone 'pink' (good, warn, hot)",
                    "function 'both': \"words\" gives a word for some of ready, off, on,",
                    "function 'bad': if reads nope, which nothing gives",
                    "function 'bad': set 'double' - it can change a control or a stock",
                    "function 'bad': set rods: not allowed in a formula",
                    "function 'bad': \"add\" should be a map of names to values",
                    "function 'bad': \"keeps\" is for a function that is on a while",
                    "function 'bad': \"effects\" should be a list of effects",
                    "function 'my-name': its name should be a word formulas can read",
                    "function 'list' should be a map",
                    "sim 'b': function 'jump': the key 'space' is the vehicle's",
                    "sim 'c': functions should be a map of names to functions",
                    "sim 'd': systems heat rate reads q_lef, which nothing gives",
                    "sim 'd': function 'q_left': there is already a value called q_left"):
            self.assertIn(bit, text)
        self.assertNotIn("function 'free'", text)            # nothing asked of it: a digit for its key
        self.assertNotIn("function 'fix'", text)
        self.assertNotIn("function 'ok':", text)
        self.assertEqual(len(text.splitlines()), 22, text)

    def test_what_was_done_at_the_console_the_scene_gets(self):
        from engine.game import Game
        from test_level_saves import Silent

        def played(sim, write, read):
            sim.paused = None
            hold(sim, "b", 2.1)                              # not the whole job: the beacon is only on its way
            hold(sim, "n", 0.1)
            sim.result = sim.over = "quit"
            return "quit"
        out = io.StringIO()
        lines = iter(["go scan", "quit"])
        term = Term(out=out, inp=lambda p: next(lines, "quit"), width=80, height=24, color=0, unicode=True,
                    animate=False, env={})
        g = Game(STATION, term=term, audio=Silent(), settings={})
        data = g.data
        data.sims["scan"]["functions"]["beacon"]["if"] = ""
        with mock.patch.object(S, "play_text", played):
            g.mode_request = next(iter(g.modes), None)
            try:
                g.run()
            except Exception:
                pass
        flags = g.world.flags
        self.assertTrue(flags.get("scan_beacon"))            # done at the console: a flag of the sim's and the name
        self.assertTrue(flags.get("scan_narrow"))
        self.assertTrue(flags.get("beacon_down"))            # and its own effects, though the sim was left
        self.assertFalse(flags.get("scan_done"))
        self.assertEqual(g.world.vars["sims"]["scan"]["functions"], {"narrow": 1, "beacon": 1})

    def test_the_station_starter(self):
        data = GameData(STATION)
        self.assertEqual(data.validate(), [])
        took = {}
        for sid in ("helm", "reactor", "scan"):
            s = S.make(data, sid)
            journal = S.fly(s)
            self.assertEqual(s.result, "won", sid)
            again = S.make(data, sid)
            replay(S.Runner(again), journal, exact=True, ticks=1200)
            self.assertEqual((again.result, again.stats()), ("won", s.stats()), sid)
            took[sid] = s
        self.assertEqual(took["scan"].stats()["functions"]["beacon"], 1)     # the scan is not done without it
        self.assertEqual([f.name for f in took["reactor"].functions], ["scram", "vent"])
        self.assertEqual([f.name for f in took["helm"].functions], ["flush"])
        scan = S.make(data, "scan")
        scan.paused = None
        runner = S.Runner(scan)
        text = "\n".join("".join(c[0] or "▀" for c in r) if isinstance(r, list) else strip_ansi(r)
                         for r in runner.rows(100, 30, 3, True))
        self.assertIn("[N] NARROW BEAM ············ OFF", text)
        self.assertIn("[B] DEPLOY BEACON ······· LOCKED", text)
        self.assertNotIn("BEACON", text.replace("DEPLOY BEACON", ""))
        hold(scan, "b", 0.1)
        self.assertEqual(scan.note[0], "Deploy beacon: the picture is not whole yet.")
        hold(scan, (), 30.0)
        scan.systems[[x.name for x in scan.systems].index("scan")].value = 100.0
        hold(scan, (), 0.1)
        hold(scan, "b", 2.0)
        text = "\n".join("".join(c[0] or "▀" for c in r) if isinstance(r, list) else strip_ansi(r)
                         for r in runner.rows(100, 30, 3, True))
        self.assertIn("DESCENT 4 s", text)
        self.assertIsNone(scan.result)
        hold(scan, (), 4.0)                                  # down: its place is on the moon below, and it is done
        text = "\n".join("".join(c[0] or "▀" for c in r) if isinstance(r, list) else strip_ansi(r)
                         for r in runner.rows(100, 30, 3, True))
        self.assertIn("┼ BEACON", text)
        self.assertIn("EREBUS ┼", "\n".join("".join(c[0] or "▀" for c in r) if isinstance(r, list) else strip_ansi(r)
                                            for r in S.Runner(S.make(data, "scan")).rows(100, 30, 3, True)))
        self.assertIn("DEPLOY BEACON ········· DOWN", text)
        self.assertEqual(scan.result, "won")
        data.sims["reactor"]["panels"]["rows"][1]["cols"][0]["widgets"][-1]["functions"] = ["vent", "purge"]
        data.sims["reactor"]["functions"]["vent"]["key"] = "up"
        self.assertEqual([p for p in data.validate() if "reactor" in p],
                         ["sim 'reactor': function 'vent': the key 'up' is control 'rods''s",
                          "sim 'reactor': panels row 2 col 1 widget 8: there is no function called 'purge'"])


class ConsoleTests(unittest.TestCase):
    """A console in a game: its menu over it, time standing; taps on its lines as keys."""

    def play(self, name, script, touch=True, mode="kitty", game=True, size=(112, 34)):
        from helpers import Session
        from engine.keys import KeyEvent, ScriptedKeys
        from engine.realtime import Clock, FakeClock
        fc = FakeClock()
        session = Session("templates/station").start()
        sim = S.make(session.game.data, name)
        term = Term(out=io.StringIO(), width=size[0], height=size[1], color=3, unicode=True, animate=False, env={},
                    glyphs="full")
        keys = ScriptedKeys([KeyEvent(k) if isinstance(k, str) else k for k in script], mode=mode, clock=fc)
        rec = S.play_frame(sim, term, keys=keys, clock=Clock(20, now=fc.now), game=session.game if game else None,
                           touch=touch)
        return sim, rec, strip_ansi(term.out.getvalue()), session

    def test_esc_opens_the_games_menu_and_time_stands(self):
        sim, rec, text, session = self.play("reactor", ["enter"] + [None] * 30 + ["esc"] + [None] * 60 + ["r"]
                                            + [None] * 30 + ["p", None, "4", "down", "enter"])
        self.assertIn("RESUME", text)
        self.assertIn("KEYS", text)
        self.assertIn("Esc menu", text)
        self.assertNotIn("PAUSED", text)
        self.assertEqual(sim.over, "quit")                                   # left by the menu, asked first
        names = [n for _, evs in rec.journal for n, _ in evs]
        self.assertEqual(names, ["enter"])                                   # the menu's keys are not the console's
        self.assertLess(sim.ticks, 80)                                       # sixty waits in the menu: not a tick

    def test_without_a_game_round_it_p_still_pauses(self):
        sim, rec, text, _ = self.play("reactor", ["enter", None, "p", None, None, "q"], game=False)
        self.assertIn("PAUSED", text)
        self.assertIn("P pause", text)
        self.assertNotIn("[MENU]", text)
        self.assertEqual(sim.over, "quit")

    def test_the_keys_page_names_the_consoles_keys(self):
        sim = S.make(GameData(STATION), "reactor")
        self.assertEqual(S.help_lines(sim, True), [("Up / Dn", "Rods out: more, less"), ("Rt / Lt", "Flow: more, less"),
                                                   ("X", "Scram (hold it)"), ("V", "Vent steam"),
                                                   ("tap", "A line that names a key is that key")])
        helm = S.make(GameData(STATION), "helm")
        self.assertEqual(S.help_lines(helm)[0], ("Up / Dn", "Thrust"))
        self.assertIn("Esc menu", S.help_line(helm, True))

    def test_a_tap_on_a_line_is_its_key(self):
        sim = S.make(GameData(STATION), "reactor")
        from engine.realtime import Pointer
        runner = S.Runner(sim)
        runner.pointer = Pointer()
        runner.menu_on = True
        runner.rows(112, 34, 3, True)
        self.assertEqual(runner.pointer.hits[0][4], "esc")                    # [MENU] at the right of the top line
        self.assertEqual(runner.pointer.key_at(50, 12), "enter")              # not begun: a tap anywhere begins it
        sim.paused = None
        rows = runner.rows(112, 34, 3, True)
        text = ["".join(c[0] or " " for c in r) if isinstance(r, list) else strip_ansi(r) for r in rows]
        at = {key: (x0, y0, x1) for x0, y0, x1, y1, key in runner.pointer.hits}
        self.assertEqual(sorted(at), ["down", "esc", "left", "right", "up", "v", "x"])
        self.assertIn("SCRAM", text[at["x"][1]][at["x"][0]:at["x"][2]])       # the line that names it
        self.assertIn("RODS OUT", text[at["down"][1]])
        self.assertLess(at["down"][0], at["up"][0])                           # left of the bar's middle less, right more
        self.assertIsNone(runner.pointer.key_at(60, 20))

    def test_a_console_played_by_taps(self):
        probe = S.Runner(S.make(GameData(STATION), "reactor"))
        from engine.realtime import Pointer
        probe.pointer = Pointer()
        probe.sim.paused = None
        probe.rows(112, 34, 3, True)
        at = {key: (x0, y0) for x0, y0, x1, y1, key in probe.pointer.hits}
        up, x = "%d:%d" % at["up"], "%d:%d" % at["x"]
        script = ["mouse:0:50:12", "mouseup:0:50:12", None, "mouse:0:" + up] + [None] * 60 + ["mouseup:0:" + up] \
            + [None] * 4 + ["mouse:0:" + x] + [None] * 70 + ["mouseup:0:" + x] + [None] * 6
        sim, rec, text, _ = self.play("reactor", script, mode="guess", game=False)
        self.assertTrue(sim.function("scram").done)                           # held by a finger for as long as it takes
        self.assertEqual(sim.controls["rods"]["value"], 0)                    # and it put the rods in
        names = {n for _, evs in rec.journal for n, _ in evs}
        self.assertEqual(names, {"enter", "up", "x", "ctrl-d"})               # the journal holds keys (and the script's end)
        again = S.make(GameData(STATION), "reactor")
        replay(again, rec.journal, rate=again.rate)
        self.assertEqual((again.ticks, again.state_hash()), (sim.ticks, sim.state_hash()))

    def test_a_small_screen_taps_too(self):
        sim = S.make(GameData(STATION), "reactor")
        from engine.realtime import Pointer
        runner = S.Runner(sim)
        runner.pointer = Pointer()
        sim.paused = None
        rows = runner.rows(48, 20, 3, True)                                   # a phone held upright: the ledger
        text = [strip_ansi(r) if isinstance(r, str) else "".join(c[0] or " " for c in r) for r in rows]
        at = {key: y0 for x0, y0, x1, y1, key in runner.pointer.hits}
        self.assertEqual(sorted(at), ["v", "x"])
        self.assertIn("Scram", text[at["x"]])
        self.assertIn("Vent", text[at["v"]])


class ConsoleEffectTests(unittest.TestCase):
    """{"console": ...}: a simulator opened by an effect, in the middle of something else."""

    def test_a_console_by_an_effect_ends_softly(self):
        from helpers import Session
        from engine import conditions
        s = Session("templates/station").start()
        game = s.game
        s.queue[:] = ["quit"]
        conditions.run([{"console": "reactor"}], game)                       # left unfinished: nothing more happens
        self.assertFalse(game.over)
        self.assertEqual(game.world.scene.get("id"), "bridge")
        self.assertFalse(game.world.flags.get("reactor_done"))
        s.queue[:] = ["quit"]
        conditions.run([{"console": {"sim": "reactor", "quit": [{"set": "walked_away"}], "done": [{"set": "lit"}]}}], game)
        self.assertTrue(game.world.flags.get("walked_away"))
        self.assertFalse(game.world.flags.get("lit"))
        with mock.patch.object(S, "play_text", side_effect=lambda sim, write, read: setattr(sim, "result", "lost")):
            conditions.run([{"console": {"sim": "reactor", "fail": [{"set": "dark"}]}}], game)
        self.assertFalse(game.over)                                          # a console that fails is not the game's end
        self.assertTrue(game.world.flags.get("reactor_failed") and game.world.flags.get("dark"))
        with mock.patch.object(S, "play_text", side_effect=lambda sim, write, read: setattr(sim, "result", "won")):
            conditions.run([{"console": {"sim": "reactor", "done": [{"set": "lit"}]}}], game)
        self.assertTrue(game.world.flags.get("reactor_done") and game.world.flags.get("lit"))
        self.assertFalse(game.world.flags.get("reactor_failed"))             # tried again and done: no longer failed
        conditions.run([{"console": "warp"}], game)
        self.assertIn("no console called 'warp'", s.text)


if __name__ == "__main__":
    unittest.main()
