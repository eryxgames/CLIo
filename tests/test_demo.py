# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Demos: playlists of clips that play themselves (engine/demo.py), the tech demo, RØØTLESS's own."""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import demo  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.keys import ScriptedKeys  # noqa: E402
from engine.realtime import FakeClock  # noqa: E402
from engine.term import Term, strip_ansi  # noqa: E402

ROOTLESS = os.path.join(ROOT, "games", "rootless")


def player(clips, keys=None, W=100, H=30, game="rootless", title="Test"):
    fc = FakeClock()
    term = Term(out=io.StringIO(), width=W, height=H, color=3, unicode=True, animate=False,
                env={"TERM": "xterm-256color"})
    p = demo.Player(term, {"title": title, "game": game, "clips": clips},
                    keys=ScriptedKeys([None] * 20000 if keys is None else keys, clock=fc), clock=fc)
    p.screen.size = lambda: (W, H)
    seen = []
    frame = p.screen.frame

    def grab(rows, **kw):
        frame(rows, **kw)
        seen.append((fc.now(), p.note, p.ms))
    p.screen.frame = grab
    return p, seen, fc


class Playlists(unittest.TestCase):
    def test_the_two_demos_are_right(self):
        self.assertEqual(demo.problems(demo.tech()), [])
        spec = demo.of_game(ROOTLESS)
        self.assertEqual(demo.problems(spec, GameData(ROOTLESS)), [])
        self.assertEqual({demo.kind_of(c) for c in demo.tech()["clips"]}, set(demo.KINDS))   # every kind shows

    def test_what_is_wrong_is_said(self):
        bad = {"game": "rootless", "clips": [{"level": "e9m9"}, {"dance": 1}, {"sim": "sim8", "seconds": 0},
                                             {"level": "e1m1", "views": ["oils"]}, {"models": ["teapot"]},
                                             {"level": "e1m1", "skip_until": "lunch"}, {"stage": "sim5", "game": "nope"}]}
        said = " | ".join(demo.problems(bad))
        for words in ("has no level 'e9m9'", "clip 2: a clip is one of", "\"seconds\" should be a number above 0",
                      "no view 'oils'", "has no model 'teapot'", "\"skip_until\" is vehicle or fight", "no game 'nope'"):
            self.assertIn(words, said)
        self.assertTrue(demo.problems({"clips": []}))
        data = GameData(ROOTLESS)
        data.demo = bad                                    # what --check says of a game's demo.json
        self.assertTrue(any("e9m9" in p for p in data.validate()))


class Clips(unittest.TestCase):
    def test_a_level_played_by_its_bot(self):
        p, seen, fc = player([{"level": "e1m1", "seconds": 8, "views": ["pixel", "dots"], "caption": "Boot"}])
        self.assertEqual(p.run(), "done")
        out = strip_ansi(p.term.out.getvalue())
        self.assertIn("BOOT SECTOR", out)                  # the level's own title page, a moment
        self.assertIn("Boot", out)
        self.assertIn("any key: back", out)
        self.assertIn("pixel", out)
        self.assertIn("dots", out)                         # the view changed halfway
        self.assertTrue(any(ms for _t, _n, ms in seen))    # how long a picture took
        self.assertGreaterEqual(seen[-1][0] - seen[0][0], 7.5)

    def test_skipping_to_where_it_gets_going(self):
        p, seen, fc = player([{"level": "e1m2", "skip_until": "vehicle", "seconds": 3}])
        self.assertEqual(p.run(), "done")
        self.assertIn("cargo loader", strip_ansi(p.term.out.getvalue()))

    def test_real_time_clips(self):
        for clip, words in (({"sim": "sim8", "seconds": 3}, "SIM-8"), ({"sim": "sim9", "seconds": 3}, "COOLANT"),
                            ({"stage": "sim5", "seconds": 3}, "SIM-5"), ({"skirmish": "sim7", "seconds": 4}, "XANTRIUM")):
            p, seen, fc = player([clip])
            self.assertEqual(p.run(), "done", clip)
            self.assertIn(words, strip_ansi(p.term.out.getvalue()), clip)
            self.assertGreater(len(seen), 20, clip)         # drawn as it moves, not once

    def test_the_skirmish_is_the_computers_on_both_sides(self):
        from engine import rts
        p, seen, fc = player([{"skirmish": "sim7", "seconds": 20}])
        made = []
        world = rts.World

        def spy(spec, *a, **k):
            made.append(spec)
            return world(spec, *a, **k)
        rts.World = spy
        try:
            p.run()
        finally:
            rts.World = world
        self.assertEqual({s["control"] for s in made[0]["sides"]}, {"ai"})
        self.assertEqual(GameData(ROOTLESS).skirmishes["sim7"]["sides"][0]["control"], "player")   # the game's own: untouched

    def test_models_in_the_showroom(self):
        p, seen, fc = player([{"models": ["hopper", "fuel_cell"], "seconds": 1.5, "views": ["pixel", "dots"]}])
        self.assertEqual(p.run(), "done")
        notes = [n for _t, n, _m in seen]
        self.assertTrue(any("hopper" in n and "588 triangles" in n for n in notes))
        self.assertTrue(any("fuel cell" in n for n in notes))

    def test_a_model_turns_about_its_middle(self):
        from engine import model as model_mod
        data = GameData(ROOTLESS)
        for name in ("hopper", "drone_scout"):
            mdl = demo.centred(model_mod.Model(name, data.models[name]))
            for t in (0.0, 1.3):
                pts = mdl.pose("idle", t)
                xs, ys, zs = [q[0] for q in pts], [q[1] for q in pts], [q[2] for q in pts]
                if t == 0.0:
                    self.assertAlmostEqual((min(xs) + max(xs)) / 2, 0.0, places=6)
                    self.assertAlmostEqual((min(ys) + max(ys)) / 2, 0.0, places=6)
                self.assertGreaterEqual(min(zs), 0.0)            # on its stand, not in the floor

    def test_a_text_adventure_typed(self):
        p, seen, fc = player([{"adventure": "derelict", "commands": ["look", "take wire", "inventory"], "seconds": 12}])
        self.assertEqual(p.run(), "done")
        out = strip_ansi(p.term.out.getvalue())
        self.assertIn("> take wire", out)
        self.assertIn("Derelict", out)

    def test_cards(self):
        p, seen, fc = player([{"card": "HELLO", "text": ["a line under it"], "seconds": 1},
                              {"logo": True, "text": ["the engine"], "seconds": 1}])
        self.assertEqual(p.run(), "done")
        out = strip_ansi(p.term.out.getvalue())
        self.assertIn("a line under it", out)
        self.assertIn("the engine", out)
        self.assertIn("Test", out)                          # a card's caption: the playlist's title

    def test_a_key_ends_it(self):
        p, seen, fc = player([{"level": "e1m1", "seconds": 30}, {"sim": "sim8"}], keys=[None] * 40 + ["x"])
        self.assertEqual(p.run(), "key")
        out = p.term.out.getvalue()
        self.assertTrue(out.startswith("\x1b[?1049h"))
        self.assertIn("\x1b[?1049l", out[-60:])             # the screen given back
        self.assertNotIn("SIM-8", strip_ansi(out))

    def test_looping(self):
        p, seen, fc = player([{"card": "A", "seconds": 1}], keys=[None] * 120 + ["x"])
        p.loop = True
        self.assertEqual(p.run(), "key")
        self.assertGreater(len(seen), 2)                    # round more than once

    def test_a_clip_that_cannot_play_is_passed_over(self):
        p, seen, fc = player([{"level": "nowhere", "seconds": 2}, {"card": "NEXT", "seconds": 1}])
        self.assertEqual(p.run(), "done")
        out = strip_ansi(p.term.out.getvalue())
        self.assertIn("(level: there is no level 'nowhere')", out)
        self.assertEqual(seen[-1][1], "Test")                # and on to the card after it

    def test_every_clip_of_both_demos_plays(self):
        for spec in (demo.tech(), demo.of_game(ROOTLESS)):
            clips = []
            for c in spec["clips"]:
                c = dict(c, seconds=min(2.5, float(c.get("seconds", 3))))
                if demo.kind_of(c) == "models":
                    c["models"] = c["models"][:2]
                if demo.kind_of(c) == "stage" and c["stage"] == "sim6":
                    continue                                # (its bot takes seconds to find the way: sim5 shows it)
                clips.append(c)
            p, seen, fc = player(clips, W=80, H=24)
            self.assertEqual(p.run(), "done", spec["title"])
            self.assertNotIn("(level:", strip_ansi(p.term.out.getvalue()))


class Menus(unittest.TestCase):
    def test_no_screen_no_demo(self):
        term = Term(out=io.StringIO(), width=80, height=24, color=0, unicode=True, animate=False, env={})
        self.assertIsNone(demo.play(term, demo.tech()))

    def test_waiting_at_a_prompt(self):
        term = Term(out=io.StringIO(), inp=lambda _p: "3", width=80, height=24, env={})
        self.assertTrue(term.wait_key(5))                  # scripted: never idle
        called = []
        self.assertEqual(term.read("> ", idle=(0.01, lambda: called.append(1))), "3")
        self.assertEqual(called, [])

    def test_idle_turned_off(self):
        old = demo.IDLE
        try:
            demo.IDLE = 0
            self.assertIsNone(demo.idle_play(None, demo.tech()))
            demo.IDLE = 30
            self.assertEqual(demo.idle_play(None, demo.tech())[0], 30)
            self.assertIsNone(demo.idle_play(None, None))
        finally:
            demo.IDLE = old

    def test_the_title_screen_without_a_screen(self):
        from engine.game import Game
        from engine.audio import Audio
        from engine.audio.backends import NullBackend
        asked = []
        term = Term(out=io.StringIO(), inp=lambda p: asked.append(p) or "", width=80, height=24, env={})
        term.interactive = True
        game = Game(ROOTLESS, term=term, audio=Audio(backend=NullBackend(), enabled=False), seed=1)
        game.title_pause()
        self.assertTrue(any("Enter to begin" in strip_ansi(a) for a in asked))
        self.assertFalse(any("demo" in strip_ansi(a) for a in asked))   # no screen to play it on: not offered


if __name__ == "__main__":
    unittest.main()


class CtrlCTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "a pseudo-terminal is a POSIX thing")
    def test_ctrl_c_at_the_menu_ends_cleanly(self):
        # Termux, 2026-11-21: Ctrl+C while the launcher's menu waited for a key (its demo starts when idle) left a
        # traceback. Now: the terminal as it was, exit code 130, no traceback.
        import pty
        import select
        import signal
        import time
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        pid, fd = pty.fork()
        if pid == 0:
            os.environ["CLIO_DEMO_IDLE"] = "600"
            signal.signal(signal.SIGINT, signal.SIG_DFL)      # a shell's background job starts with it ignored
            os.execvp(sys.executable, [sys.executable, os.path.join(root, "clio.py"), "--no-sound"])

        def gather(seconds):
            nonlocal got
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                if select.select([fd], [], [], 0.2)[0]:
                    try:
                        chunk = os.read(fd, 4096)
                    except OSError:
                        return True                            # the other end closed: CLIo has ended
                    if not chunk:
                        return True
                    got += chunk
                    if b"#>" in got and seconds > 5:
                        return False
            return False

        got, status = b"", None
        try:
            gather(30)
            self.assertIn(b"#>", got)                          # the menu, waiting
            # A signal that comes just before Python blocks waiting for a key is only seen after the next key
            # (CPython's way): a person never types that fast, the test does - so it waits, and types again.
            for _ in range(4):
                time.sleep(0.5)
                os.write(fd, b"\x03")
                if gather(3):
                    break
            for _ in range(50):
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    break
                time.sleep(0.1)
            else:
                status = None
        finally:
            if status is None:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            os.close(fd)
        self.assertIsNotNone(status, "CLIo did not end")
        self.assertNotIn(b"Traceback", got)
        self.assertTrue(os.WIFEXITED(status))
        self.assertEqual(os.WEXITSTATUS(status), 130)
