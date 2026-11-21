# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Real time (engine/realtime.py, engine/keys.py): a fixed-rate clock, key events with presses, repeats and
releases, held keys tracked (or guessed) in ticks, games played back from their keys, and first-person
levels whose beats pass on their own."""
import io
import os
import select
import sys
import time
import unittest

try:
    import pyte                                                # not in the standard library: only some test runs have it
except ImportError:
    pyte = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import keys as keys_mod  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.frame import Screen  # noqa: E402
from engine.keys import PRESS, RELEASE, REPEAT, KeyEvent, kitty_event, vk_name  # noqa: E402
from engine.level import IDLE, KEYMAP, FrameConsole, Level, beat_of  # noqa: E402
from engine.realtime import Clock, Controls, FakeClock, Held, Loop, Recorder, replay  # noqa: E402
from engine.term import Term  # noqa: E402

ROOTLESS = os.path.join(ROOT, "games", "rootless")


class Runner:
    """A toy game: a dot that runs while an arrow is held, jumps on space, and stops on Esc."""

    def __init__(self):
        self.x, self.y, self.vy, self.over = 0, 0, 0, False
        self.ticks = 0
        self.drawn = 0

    def step(self, c):
        self.ticks += 1
        self.x += c.axis("left", "right")
        if c.hit("space") and self.y == 0:
            self.vy = 3
        self.y = max(0, self.y + self.vy)
        self.vy = self.vy - 1 if self.y > 0 else 0
        if c.hit("esc", "ctrl-d"):
            self.over = True

    def draw(self):
        self.drawn += 1


class KeyEventTests(unittest.TestCase):
    def test_kitty_sequences(self):
        self.assertEqual(kitty_event("[97u"), KeyEvent("a", PRESS))
        self.assertEqual(kitty_event("[97;1:2u"), KeyEvent("a", REPEAT))
        self.assertEqual(kitty_event("[97;1:3u"), KeyEvent("a", RELEASE))
        self.assertEqual(kitty_event("[65;2u"), KeyEvent("a", PRESS))           # Shift+A is still the a key
        self.assertEqual(kitty_event("[A"), KeyEvent("up", PRESS))
        self.assertEqual(kitty_event("[1;1:3D"), KeyEvent("left", RELEASE))
        self.assertEqual(kitty_event("[1;5:1C"), KeyEvent("right", PRESS))      # with Ctrl
        self.assertEqual(kitty_event("[57441;2u"), KeyEvent("shift", PRESS))    # Shift alone
        self.assertEqual(kitty_event("[57442;5:3u"), KeyEvent("ctrl", RELEASE))
        self.assertEqual(kitty_event("[32u"), KeyEvent("space", PRESS))
        self.assertEqual(kitty_event("[13;1:3u"), KeyEvent("enter", RELEASE))
        self.assertEqual(kitty_event("[3;1:2~"), KeyEvent("delete", REPEAT))
        self.assertEqual(kitty_event("[15~"), KeyEvent("f5", PRESS))
        self.assertEqual(kitty_event("[99;5u"), KeyEvent("ctrl-c", PRESS))     # the protocol sends no ^C
        self.assertIsNone(kitty_event("[?1u"))
        self.assertIsNone(kitty_event("O"))

    def test_windows_virtual_keys(self):
        self.assertEqual([vk_name(v, "") for v in (0x25, 0x26, 0x27, 0x28, 0x20, 0x10, 0xA1, 0x11)],
                         ["left", "up", "right", "down", "space", "shift", "shift", "ctrl"])
        self.assertEqual((vk_name(0x41, "A"), vk_name(0x37, "7"), vk_name(0xBC, ","), vk_name(0xFF, "")),
                         ("a", "7", ",", None))

    def test_scripted_keys_give_events_and_waits(self):
        fc = FakeClock()
        k = keys_mod.ScriptedKeys(["up", None, [KeyEvent("up", RELEASE), "x"]], clock=fc)
        self.assertEqual(k.events(0.1), [KeyEvent("up")])
        self.assertEqual(k.events(0.1), [])
        self.assertAlmostEqual(fc.now(), 1000.2)
        self.assertEqual(k.events(0.1), [KeyEvent("up", RELEASE), KeyEvent("x")])
        self.assertEqual(k.events(0.1), [KeyEvent("ctrl-d")])                  # the end: no test can hang


class ClockTests(unittest.TestCase):
    def test_ticks_come_at_the_rate_and_a_slow_machine_slows_down(self):
        fc = FakeClock()
        c = Clock(20, now=fc.now, behind=3)
        c.start()
        self.assertEqual(c.due(), 1)                           # the first at once
        self.assertEqual(c.due(), 0)
        self.assertAlmostEqual(c.until(), 0.05)
        fc.advance(0.05)
        self.assertEqual(c.due(), 1)
        fc.advance(0.12)
        self.assertEqual(c.due(), 2)
        fc.advance(1.0)                                        # twenty ticks late: three, the rest let go
        self.assertEqual(c.due(), 3)
        self.assertGreater(c.dropped, 10)
        self.assertEqual(c.due(), 0)


class HeldTests(unittest.TestCase):
    def test_exact_presses_and_releases(self):
        h = Held(20, exact=True)
        c = h.feed(0, [KeyEvent("left")])
        self.assertEqual((c.held, c.pressed), (frozenset({"left"}), ("left",)))
        for t in range(1, 15):
            c = h.feed(t, [KeyEvent("left", REPEAT)] if t % 2 else [])
            self.assertIn("left", c.held)
            self.assertEqual(c.pressed, ())
        c = h.feed(15, [KeyEvent("left", RELEASE)])
        self.assertEqual((c.held, c.released), (frozenset(), ("left",)))

    def test_exact_but_lost(self):
        h = Held(20, exact=True, lost=1.0)
        h.feed(0, [KeyEvent("up")])
        self.assertIn("up", h.feed(19, []).held)
        self.assertEqual(h.feed(20, []).released, ("up",))          # a second without a word: let go

    def test_guessed_from_repeats(self):
        h = Held(20, exact=False, first=0.5, gap=0.15)
        self.assertEqual(h.feed(0, [KeyEvent("right")]).pressed, ("right",))
        self.assertIn("right", h.feed(9, []).held)            # the terminal has not repeated yet
        self.assertEqual(h.feed(10, []).released, ("right",))  # half a second without a repeat: a tap
        h.feed(20, [KeyEvent("right")])
        for t in range(29, 60, 2):                             # repeats every tenth of a second
            self.assertIn("right", h.feed(t, [KeyEvent("right")]).held)
        self.assertIn("right", h.feed(61, []).held)
        self.assertEqual(h.feed(62, []).released, ("right",))   # three ticks after the last repeat

    def test_controls(self):
        c = Controls(4, {"left", "shift"}, ("space",))
        self.assertTrue(c.down("left") and c.down("space") and c.hit("space"))
        self.assertFalse(c.hit("left"))
        self.assertEqual(c.axis(("left", "a"), ("right", "d")), -1)
        self.assertEqual(Controls(0, {"left", "right"}).axis("left", "right"), 0)


class LoopTests(unittest.TestCase):
    def test_a_game_is_its_keys_played_back(self):
        fc = FakeClock()
        script = ["right"] + [None] * 6 + [[KeyEvent("right", REPEAT), KeyEvent("space")]] + [None] * 30 + ["esc"]
        game = Runner()
        loop = Loop(game, keys_mod.ScriptedKeys(script, mode="kitty", clock=fc), rate=20,
                    clock=Clock(20, now=fc.now))
        rec = loop.run()
        self.assertTrue(game.over)
        self.assertGreater(game.x, 3)                          # it ran while the key was down
        self.assertGreaterEqual(game.drawn, 2)
        again = Runner()
        replay(again, rec.journal, rate=20, exact=True)
        self.assertEqual((again.x, again.y, again.ticks, again.over), (game.x, game.y, game.ticks, game.over))

    def test_played_back_at_any_speed_the_same(self):
        rec = Recorder(20, exact=False)
        game = Runner()
        for t in range(60):
            evs = [KeyEvent("right")] if t in (0, 12, 14, 16, 18) else ([KeyEvent("space")] if t == 30 else [])
            game.step(rec.next(evs))
        again = Runner()
        replay(again, rec.journal, rate=20, ticks=60 - 31)
        self.assertEqual((again.x, again.y), (game.x, game.y))
        self.assertEqual(again.ticks, game.ticks)

    @unittest.skipIf(os.name == "nt", "a pseudo-terminal is a POSIX thing")
    @unittest.skipIf(pyte is None, "reads the terminal's screen with pyte (pip install pyte)")
    def test_the_key_test_in_a_terminal_that_speaks_kitty(self):
        import pty
        pid, fd = pty.fork()
        if pid == 0:                                           # the child: CLIo's key test
            os.execvp(sys.executable, [sys.executable, os.path.join(ROOT, "clio.py"), "--keys"])
        screen = pyte.Screen(80, 24)
        stream = pyte.ByteStream(screen)

        def pump(t):
            end = time.time() + t
            while time.time() < end:
                if select.select([fd], [], [], 0.02)[0]:
                    try:
                        data = os.read(fd, 4096)
                    except OSError:
                        return
                    if b"\x1b[?u" in data:                     # the terminal says it speaks the protocol
                        os.write(fd, b"\x1b[?0u\x1b[?62;22c")
                    stream.feed(data)

        def line(word):
            return next((l.strip() for l in screen.display if l.startswith(word)), "")
        try:
            pump(1.0)
            self.assertIn("kitty keyboard protocol", line("keys read by"))
            os.write(fd, b"\x1b[1;1:1C\x1b[57441;2u")
            pump(0.4)
            self.assertEqual(line("held"), "held: right shift")
            os.write(fd, b"\x1b[1;1:3C")
            pump(0.3)
            self.assertEqual(line("held"), "held: shift")
            os.write(fd, b"\x1b[57441;1:3u\x1b[113u")
            pump(0.6)
        finally:
            try:
                os.kill(pid, 9)
            except OSError:
                pass
            os.waitpid(pid, 0)
            os.close(fd)


class RealTimeLevelTests(unittest.TestCase):
    def test_the_screen_gives_an_idle_beat_when_the_time_is_up(self):
        fc = FakeClock()
        term = Term(out=io.StringIO(), width=80, height=24, color=3, unicode=True, animate=False, env={})
        sc = Screen(term, keys_mod.ScriptedKeys([None, None, None], clock=fc), {"up": "k"}, animate=False,
                    out=io.StringIO())
        sc.now = fc.now
        sc.last_size = sc.size()
        self.assertEqual(sc.read(lambda: None, deadline=fc.now() + 0.25, idle="."), ".")
        self.assertGreaterEqual(fc.now(), 1000.25)
        sc.keys = keys_mod.ScriptedKeys([None, "up"], clock=fc)
        self.assertEqual(sc.read(lambda: None, deadline=fc.now() + 0.5, idle="."), "k")   # a key in time acts
        sc.keys = keys_mod.ScriptedKeys(["f", None, None, None, None, None, None, "enter"], clock=fc)
        self.assertEqual(sc.read(lambda: None, deadline=fc.now() + 0.15, idle="."), "f")  # typing holds the beat

    def test_a_level_in_real_time_goes_on_without_the_player(self):
        fc = FakeClock()
        term = Term(out=io.StringIO(), width=80, height=24, color=3, unicode=True, animate=False, env={})
        con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False, realtime=0.5)
        con.screen.keys = keys_mod.ScriptedKeys(["enter"] + [None] * 30 + ["up"] + [None] * 12, clock=fc)
        con.screen.now = fc.now
        con.keys = con.screen.keys
        lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
        start = (lv.player.x, lv.player.y)
        self.assertEqual(lv.run(con), "quit")
        lines = [l for _b, l in lv.journal]
        self.assertGreaterEqual(lines.count(IDLE), 4)          # beats passed with nobody pressing anything
        self.assertIn("k", lines)
        self.assertEqual((lv.player.x, lv.player.y), (start[0], start[1] - 1))
        self.assertNotEqual(lv.last_line, IDLE)                # an idle beat is nobody's command
        again = Level(GameData(ROOTLESS), "e1m1", seed=1)
        again.replay(lv.journal)
        again.over = lv.over                                   # the one played was quit at the end of its keys
        self.assertEqual(again.state_hash(), lv.state_hash())  # the beats that passed play back the same
        self.assertIn("REAL TIME 0.5s", term.out.getvalue())

    def test_the_realtime_command(self):
        term = Term(out=io.StringIO(), width=80, height=24, color=3, unicode=True, animate=False, env={})
        con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False)
        con.screen.keys = con.keys = keys_mod.ScriptedKeys([])
        lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
        lv.console = con
        lv.run_line("realtime 0.4")
        self.assertEqual(con.beat(lv), 0.4)
        lv.run_line("realtime off")
        self.assertEqual(con.beat(lv), 0)
        lv.run_line("realtime")
        self.assertEqual(con.beat(lv), 0.8)
        self.assertEqual(lv.journal, [])                       # about the game, not in it: not played back
        text = Level(GameData(ROOTLESS), "e1m1", seed=1)
        from test_levels import Quiet
        text.console = Quiet()
        text.run_line("realtime")
        self.assertIn("Real time needs single keys", " ".join(str(t) for t in text.console.told))

    def test_the_beat_is_the_command_lines_else_the_levels_else_the_games(self):
        lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
        self.assertEqual(beat_of(lv), 0.0)
        lv.cfg = dict(lv.cfg, realtime=0.7)
        self.assertEqual(beat_of(lv), 0.7)
        lv.spec = dict(lv.spec, realtime=False)
        self.assertEqual(beat_of(lv), 0.0)
        self.assertEqual(beat_of(lv, 1.5), 1.5)
        self.assertEqual(beat_of(lv, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
