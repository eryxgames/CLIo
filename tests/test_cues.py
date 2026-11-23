# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Cues (engine/cues.py): shapes, a sheet asked for levels, turns and events (round a loop too), a sheet
Playhead wrote, sheets from a song's own notes by rules, the sheet beside a sound file, and the clock and
sheet of the track that is playing."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import cues  # noqa: E402
from engine.audio import Audio  # noqa: E402
from engine.audio.backends import NullBackend  # noqa: E402

SONG = {"tempo": 120, "steps_per_beat": 4,
        "instruments": {"lead": {"wave": "square"}, "kit": {"wave": "drums"}},
        "patterns": {"A": {"lead": "c4:8 e4:8", "kit": "k . h . s . h@4 . k . h . s . h ."},
                     "B": {"lead": "g4:16", "kit": "k k . . c . o . t . . . s . . ."}},
        "sequence": ["A", "A", "B", "A"]}


def sheet(cue_list, duration=10.0, loop=True, curves=None):
    doc = {"format": "playhead-cues", "version": 1, "source": {"duration": duration}, "cues": cue_list}
    if curves:
        doc["curves"] = curves
    return cues.Sheet(doc, loop)


class ShapeTests(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual([cues.shape("hold", u) for u in (0, 0.5, 1)], [1, 1, 1])
        self.assertEqual([cues.shape("ramp", u) for u in (0, 0.5, 1)], [0, 0.5, 1])
        self.assertEqual([cues.shape("fade", u) for u in (0, 0.25, 1)], [1, 0.75, 0])
        self.assertAlmostEqual(cues.shape("swell", 0.5), 1.0)
        self.assertEqual(cues.shape("pulse", 0), 1.0)
        self.assertAlmostEqual(cues.shape("pulse", 1), 0.0183, 3)
        self.assertEqual(cues.shape("no such", 0), 1.0)                      # a pulse
        self.assertEqual((cues.shape("hold", -0.1), cues.shape("hold", 1.1)), (0.0, 0.0))


class SheetTests(unittest.TestCase):
    def test_levels_are_the_greatest_of_the_cues_that_are_on(self):
        s = sheet([{"t": 1.0, "length": 2.0, "action": "glow", "amount": 0.5, "shape": "hold"},
                   {"t": 2.0, "length": 1.0, "action": "glow", "amount": 0.8, "shape": "fade"},
                   {"t": 2.0, "length": 0.5, "action": "flash", "amount": 1.0, "shape": "ramp"}], loop=False)
        self.assertEqual([s.level("glow", t) for t in (0.5, 1.0, 2.0, 2.75, 3.5)], [0.0, 0.5, 0.8, 0.5, 0.0])
        self.assertEqual(s.level("flash", 2.25), 0.5)
        self.assertEqual(s.level("nothing", 2.0), 0.0)
        self.assertEqual(s.levels(2.0), {"flash": 0.0, "glow": 0.8})
        self.assertEqual(s.actions, ["flash", "glow"])

    def test_a_curve_joins_its_action(self):
        s = sheet([{"t": 0.0, "length": 1.0, "action": "rough", "amount": 0.3, "shape": "hold"}], loop=False,
                  curves={"rate": 10, "values": {"rough": [0.0, 0.1, 0.9, 0.2], "glow": [0.5, 0.6]}})
        self.assertEqual([s.level("rough", t) for t in (0.0, 0.15, 0.25, 0.35, 5.0)], [0.3, 0.3, 0.9, 0.3, 0.2])
        self.assertEqual(s.level("glow", 0.1), 0.6)

    def test_a_loop_comes_round_and_turns_count(self):
        s = sheet([{"t": 1.0, "length": 1.0, "action": "palette", "shape": "hold"},
                   {"t": 5.0, "length": 2.0, "action": "palette", "shape": "hold"}], duration=10.0)
        self.assertEqual(s.level("palette", 11.5), 1.0)
        self.assertEqual([s.turns("palette", t) for t in (0.5, 1.5, 3.0, 6.0, 9.0, 11.5)], [0.0, 0.5, 1.0, 1.5, 2.0, 0.5])
        self.assertEqual(sheet([], 0.0).level("x", 3.0), 0.0)                # no length: no loop, no trouble
        once = sheet([{"t": 1.0, "length": 1.0, "action": "palette", "shape": "hold"}], loop=False)
        self.assertEqual(once.level("palette", 11.5), 0.0)

    def test_what_happens_once_is_told_once(self):
        s = sheet([{"t": 2.0, "length": 0.1, "action": "event", "name": "eruption"},
                   {"t": 9.5, "length": 0.1, "action": "event", "name": "lock"}], duration=10.0)
        self.assertEqual(s.events(0.0, 1.9), [])
        self.assertEqual(s.events(1.9, 2.0), ["eruption"])
        self.assertEqual(s.events(2.0, 2.1), [])
        self.assertEqual(s.events(9.0, 12.5), ["lock", "eruption"])          # round the end
        self.assertEqual(s.events(0.0, 25.0), ["eruption", "lock"])
        self.assertEqual(s.events(5.0, 4.0), [])
        self.assertEqual(s.level("event", 2.0), 0.0)

    def test_a_sheet_playhead_wrote(self):
        s = cues.load(os.path.join(HERE, "data", "recording.cues.json"))
        self.assertEqual(s.duration, 6.0)
        self.assertEqual(s.actions, ["glow", "palette", "punch", "rough", "shockwave", "sparks"])
        self.assertGreater(len(s.cues), 60)
        first = s.by["sparks"][1][0]
        self.assertAlmostEqual(s.level("sparks", first["t"]), first["amount"])
        peaks = [max(s.level(a, i / 50.0) for i in range(300)) for a in ("punch", "shockwave", "sparks", "glow")]
        self.assertTrue(all(0.3 < p <= 1.0 for p in peaks), peaks)
        self.assertIsNone(cues.load(os.path.join(HERE, "data", "no-such.json")))
        self.assertIsNone(cues.load(os.path.join(ROOT, "templates", "starter", "game.json")))   # not a cue sheet


class SongTests(unittest.TestCase):
    def test_a_songs_notes_say_what_happens(self):
        events, total, beat, bar = cues.song_events(SONG)
        self.assertEqual((total, beat, bar), (8.0, 0.5, 2.0))
        kinds = {}
        for e in events:
            kinds[e["type"]] = kinds.get(e["type"], 0) + 1
        self.assertEqual(kinds, {"hit.low": 2 * 3 + 3, "hit.mid": 2 * 3 + 2, "hit.high": 4 * 3 + 1,
                                 "beat": 16, "bar": 4, "section.new": 2, "section.repeat": 1})
        parts = [(e["t"], e["type"], e["label"]) for e in events if e["type"].startswith("section")]
        self.assertEqual(parts, [(0.0, "section.new", "A"), (4.0, "section.new", "B"), (6.0, "section.repeat", "A")])
        soft = [e for e in events if e["type"] == "hit.high" and e["strength"] < 1][0]
        self.assertEqual((soft["t"], round(soft["strength"], 2)), (0.75, 0.44))

    def test_the_usual_rules(self):
        s = cues.from_song(SONG)
        self.assertEqual(s.duration, 8.0)
        self.assertEqual(s.actions, ["bar", "beat", "palette", "punch", "shockwave", "sparks"])
        self.assertEqual(s.level("punch", 0.0), 1.0)
        self.assertLess(s.level("punch", 0.1), 0.1)
        self.assertEqual(s.level("shockwave", 0.5), 1.0)
        self.assertEqual(s.level("shockwave", 0.75), 0.5)
        self.assertAlmostEqual(s.level("sparks", 0.75), 0.444)               # a soft hat
        self.assertEqual(s.level("bar", 2.0), 1.0)
        self.assertEqual(s.level("bar", 8.0), 1.0)                           # round again
        self.assertEqual([round(s.turns("palette", t), 2) for t in (0.5, 3.0, 4.5, 7.5)], [0.5, 1.0, 1.5, 3.0])
        self.assertEqual(s.doc["format"], "playhead-cues")

    def test_rules_of_ones_own(self):
        rules = [{"on": "hit.low", "do": "thump", "every": 2, "amount": 0.5, "scale": False, "length": 1,
                  "lengthUnit": "beats", "shape": "hold"},
                 {"on": "section.new", "where": {"label": "B"}, "do": "event", "name": "bridge"},
                 {"on": "section.new", "where": {"label": "B"}, "do": "darken", "at": -1, "unit": "bars",
                  "length": 1, "lengthUnit": "bars", "shape": "ramp"},
                 {"on": "section", "do": "wash", "length": 0.5, "lengthUnit": "event", "shape": "fade"},
                 {"on": "bar", "do": "event", "name": "one", "at": -0.5, "unit": "beats"},
                 {"oops": 1}]
        s = cues.from_song(dict(SONG, cues=rules))
        self.assertEqual([c["t"] for c in s.by["thump"][1]], [0.0, 2.0, 4.0, 5.0, 7.0])     # every second low hit
        self.assertEqual(s.level("thump", 0.4), 0.5)
        self.assertEqual(s.events(3.9, 4.0), ["bridge"])
        self.assertEqual((s.level("darken", 2.0), s.level("darken", 3.0), s.level("darken", 4.0)), (0.0, 0.5, 1.0))
        self.assertEqual(s.level("wash", 1.0), 0.5)                          # half of a part of four seconds
        self.assertEqual(s.events(7.7, 7.8), ["one"])                        # before the first bar: at the end
        self.assertEqual(cues.from_song(SONG, rules=[]).actions, [])

    def test_rules_are_checked(self):
        self.assertEqual(cues.problems(cues.RULES), [])
        text = "\n".join(cues.problems([{"on": "beat"}, {"on": "beat", "do": "x", "shape": "zig", "unit": "miles"},
                                        {"on": "bar", "do": "event"}, 3], "song 'a' cues"))
        for part in ("song 'a' cues rule 1: it needs \"on\" and \"do\"", "rule 2: unknown shape 'zig'",
                     "rule 2: unit is s, beats or bars", "rule 3: an event needs a name", "rule 4: it needs"):
            self.assertIn(part, text)
        self.assertEqual(cues.problems({}), ["cues should be a list of rules"])

    def test_the_composers_songs_have_their_cues(self):
        from engine.audio.compose import compose
        for mood in ("tense", "calm", "battle"):
            s = cues.from_song(compose(5, mood, 8))
            self.assertGreater(s.duration, 5)
            self.assertIn("beat", s.actions)
            self.assertEqual(s.level("bar", 0.0), 1.0)


class PlayingTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="clio-cues-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def audio(self, **kw):
        os.makedirs(os.path.join(self.dir, "cache"), exist_ok=True)
        return Audio(game_dir=self.dir, backend=NullBackend(record=True), cache_dir=os.path.join(self.dir, "cache"), **kw)

    def test_the_track_that_plays_has_a_clock_and_a_sheet(self):
        a = self.audio(songs={"theme": SONG})
        self.assertIsNone(a.clock())
        self.assertIsNone(a.cues())
        a.music("theme")
        t = a.clock()
        self.assertTrue(0.0 <= t < 0.5, t)
        time.sleep(0.05)
        self.assertGreater(a.clock(), t)
        a.cue_offset = 100.0
        self.assertEqual(a.clock(), 0.0)
        s = a.cues()
        self.assertEqual(s.duration, 8.0)
        self.assertIs(a.cues(), s)                                           # made once
        a.music({"generate": {"mood": "calm", "seed": 2, "bars": 4}})
        self.assertIsNot(a.cues(), s)
        self.assertIn("beat", a.cues().actions)
        a.stop_music()
        self.assertIsNone(a.clock())
        self.assertIsNone(a.cues())

    def test_a_chain_of_players_has_the_clock_of_the_one_that_plays(self):
        from engine.audio.backends import ChainBackend

        class Can(NullBackend):
            def can_play(self, path):
                return True

        chain = ChainBackend([NullBackend(record=True), Can(record=True)])
        self.assertIsNone(chain.loop_began)
        chain.loop("x.wav")
        self.assertIsNotNone(chain.loop_began)
        chain.stop_loop()
        self.assertIsNone(chain.loop_began)

    def test_a_sound_file_takes_the_sheet_beside_it(self):
        os.makedirs(os.path.join(self.dir, "music"))
        wav = os.path.join(self.dir, "music", "bridge.wav")
        from engine.audio import synth
        synth.write_wav(wav, synth.tone(220, 0.1))
        a = self.audio()
        a.music("music/bridge.wav")
        self.assertIsNotNone(a.clock())
        self.assertIsNone(a.cues())                                          # none beside it
        shutil.copy(os.path.join(HERE, "data", "recording.cues.json"), os.path.join(self.dir, "music", "bridge.cues.json"))
        self.assertEqual(cues.beside(wav).duration, 6.0)
        b = self.audio()
        b.music("music/bridge.wav")
        self.assertEqual(b.cues().duration, 6.0)
        self.assertGreater(len(b.cues().cues), 60)


if __name__ == "__main__":
    unittest.main()
