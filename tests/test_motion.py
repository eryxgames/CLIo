# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""Models moved by CLIo Motion (engine/motion): every character built as a model, its clips, what a level's
monster shows of it - striding, attacking, struck, falling and lying - the viewer, --check and the recipes."""
import math
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import model, motion, recipes, viewer  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.firstperson import FX, View  # noqa: E402
from engine.level import Level  # noqa: E402
from test_levels import ROOTLESS  # noqa: E402

GUARD = {"name": "Guard", "tag": "g", "model": "g", "hp": 50, "attack": {"kind": "melee", "damage": [4, 6]}}


def level_with(spec, monster=None):
    data = GameData(ROOTLESS)
    data.models = {"g": spec}
    data.monsters = dict(data.monsters, g1=monster or GUARD)
    data.levels = dict(data.levels, t={"name": "T", "map": ["#####", "#...#", "#.G.#", "#.@.#", "#####"], "legend": {"G": "g1"},
                                       "facing": "n"})
    lv = Level(data, "t", seed=2)
    return lv, [m for m in lv.monsters if m.model == "g"][0]


def far(a, b):
    return max(math.dist(p, q) for p, q in zip(a, b))


class EveryCharacter(unittest.TestCase):
    def test_each_is_a_model_with_its_clips(self):
        self.assertEqual(len(motion.characters()), 12)
        for name in motion.characters():
            m = model.Model(name, {"motion": name})
            self.assertIsNotNone(m.motion, name)
            self.assertTrue(200 < len(m.faces) < 1500, (name, len(m.faces)))
            self.assertTrue(all(0 <= i < len(m.verts) for f in m.faces for i in f[:3]), name)
            self.assertTrue(0.15 < m.height < 2.5, (name, m.height))
            self.assertGreater(min(p[2] for p in m.verts), -0.05, name)             # it stands on the floor
            self.assertEqual(m.clips[0], "idle", name)
            self.assertIn("walk", m.clips, name)
            self.assertIn("die", m.clips, name)
            self.assertEqual(m.breaks, "fall", name)
            self.assertTrue(m.moves, name)
            self.assertGreater(len(m.groups), 4, name)
            edges = {}                                                             # every part a closed shape
            for f in m.faces:
                for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                    edges[e] = edges.get(e, 0) + 1
            self.assertTrue(all(n == 1 and edges.get((b, a)) == 1 for (a, b), n in edges.items()), name)

    def test_a_walk_goes_round_and_an_end_is_held(self):
        for name in ("soldier", "hyena", "spider"):
            m = model.Model(name, {"motion": name})
            beats = m.beats("walk")
            self.assertTrue(0.3 < beats < 2.5, (name, beats))
            a, b = m.pose("walk", 0.0), m.pose("walk", beats * 0.5)
            self.assertGreater(far(a, b), 0.03 * m.height, name)                   # it strides
            self.assertLess(far(a, m.pose("walk", beats)), 1e-9, name)              # and comes round
            self.assertLess(far(m.pose("walk", beats * 0.999), a), 0.03 * m.height, name)   # with no jump at the seam
            self.assertLess(far(m.pose("walk", 0.25 * beats), m.pose("walk", 0.255 * beats)), 0.03 * m.height, name)
            # in place: its middle stays over its spot
            for k in range(8):
                p = m.pose("walk", beats * k / 8.0)
                self.assertLess(abs(sum(q[1] for q in p) / len(p)), 0.3 * m.radius + 0.05, name)
            end = m.beats("die")
            lying = m.pose("die", end * 0.999999)
            self.assertLess(max(p[2] for p in lying), 0.75 * max(p[2] for p in m.pose("idle", 0.0)), name)   # it lies low
            self.assertEqual(lying, m.pose("die", end + 0.3), name)                 # and stays so for a while

    def test_kits_colours_and_materials(self):
        rifle = model.Model("a", {"motion": "soldier"})
        sword = model.Model("b", {"motion": {"character": "soldier", "kit": "sword"}})
        self.assertNotIn("prop1", rifle.groups)
        self.assertIn("prop1", sword.groups)                                       # the shield
        self.assertIn("chop", model.Model("c", {"motion": {"character": "soldier", "kit": "sword", "clips": ["idle", "chop"]}}).clips)
        was = {f[4] for f in rifle.faces if rifle.groups[f[5]] == "torso"}
        painted = model.Model("d", {"motion": "soldier", "colors": {"torso": "#102030"},
                                    "materials": {"prop0": {"color": "#888888", "metal": 0.9, "rough": 0.2}}})
        now = {f[4] for f in painted.faces if painted.groups[f[5]] == "torso"}
        self.assertEqual(now, {model.colour("#102030")})
        self.assertNotEqual(was, now)
        gun = {painted.materials[f[3]].name for f in painted.faces if painted.groups[f[5]] == "prop0"}
        self.assertEqual(gun, {"prop0"})
        self.assertTrue(any(mt.glow for mt in rifle.materials))                    # its eyes
        big = model.Model("e", {"motion": {"character": "soldier", "scale": 0.8}})
        self.assertAlmostEqual(big.height, 2 * rifle.height, delta=0.01)
        low, high = (model.Model("f", {"motion": {"character": "hyena", "detail": d}}) for d in (0, 3))
        self.assertLess(len(low.faces), len(high.faces))
        self.assertEqual(model.Model("g", {"motion": "mech", "break": "parts"}).breaks, "parts")
        self.assertEqual(model.Model("h", {"motion": {"character": "soldier", "clips": ["idle", "walk"]}}).breaks, "shards")

    def test_the_library_is_carried(self):
        self.assertRegex(motion.version(), r"^\d+\.\d+\.\d+$")
        here = os.path.join(ROOT, "engine", "motion", "clio_motion")
        for name in ("characters.json", "rigs.json", "clips.py", "mesh.py", "rig.py"):
            self.assertTrue(os.path.isfile(os.path.join(here, name)), name)


class WhatIsPlayed(unittest.TestCase):
    def setUp(self):
        self.m = model.Model("g", {"motion": "soldier"}).motion

    def test_by_what_the_monster_does(self):
        mv = self.m
        self.assertEqual(mv.playing(1, "idle", 3.0), ("idle", 3.0))
        self.assertEqual(mv.playing(1, "walk", 3.4), ("walk", 3.4))
        self.assertEqual(mv.playing(1, "walk", 3.4, fast=True), ("run", 3.4))
        self.assertEqual(mv.playing(1, "attack", 7.0), ("attack", 0.0))            # aiming: held at its start
        clip, t = mv.playing(1, "attack", 7.5, tick=0.5, firing=True)
        self.assertEqual((clip, t), ("attack", 0.5))
        clip, t = mv.playing(1, "idle", 2.0, tick=0.5, struck=True)
        self.assertEqual(clip, "hit")
        self.assertTrue(0 < t < mv.beats("hit"))
        names = {mv.playing(k, "idle", 0.0, dead=True)[0] for k in range(6)}
        self.assertEqual(names, {"die", "die2", "die3"})                           # three ways to fall
        self.assertEqual(mv.playing(4, "idle", 0.0, dead=True), mv.playing(4, "walk", 9.0, dead=True))   # always its own
        c0, t0 = mv.playing(2, "idle", 0.0, falling=0.0)
        c1, t1 = mv.playing(2, "idle", 0.0, falling=1.0)
        self.assertEqual((c0, t0), ("die3", 0.0))
        self.assertAlmostEqual(t1, mv.beats("die3"), delta=1e-3)
        self.assertNotEqual(mv.pose("die", 2.0), mv.pose("die2", 2.0))

    def test_one_that_cannot_run_walks(self):
        mv = model.Model("o", {"motion": "octopus"}).motion
        self.assertEqual(mv.playing(1, "walk", 1.0, fast=True), ("walk", 1.0))


class InALevel(unittest.TestCase):
    def picture(self, lv, fx=None, phase=0):
        return View(80, 20, "pixel").render(lv, fx or FX(), phase)

    def test_it_strides_attacks_staggers_falls_and_lies(self):
        lv, m = level_with({"motion": "soldier"})
        m.heading = 0.0
        standing = self.picture(lv)
        m.gone = True
        empty = self.picture(lv)
        m.gone = False
        self.assertNotEqual(standing, empty)
        steps = [self.picture(lv, FX(pos={m.id: (m.x, m.y)}, tick=k), 3) for k in (1 / 3.0, 2 / 3.0, 1.0)]
        self.assertTrue(steps[0] != steps[1] != steps[2] and standing not in steps)
        m.intent = "aim"
        aiming = self.picture(lv, phase=1)
        m.intent = None
        firing = self.picture(lv, FX(emuzzle=(m.id,), tick=0.4), 1)
        self.assertNotEqual(aiming, standing)
        self.assertNotEqual(firing, aiming)
        biting = self.picture(lv, FX(lunge={m.id: 1.2}, tick=0.4), 1)
        self.assertNotEqual(biting, standing)
        falling = [self.picture(lv, FX(dissolve={m.id: k})) for k in (0.25, 0.5, 1.0)]
        self.assertTrue(falling[0] != falling[1] != falling[2])
        m.dead = True
        lying = self.picture(lv, phase=4)
        self.assertNotEqual(lying, empty)                                          # the body is there
        self.assertEqual(lying, self.picture(lv, phase=9))                         # and does not stir
        self.assertEqual(lying, self.picture(lv, FX(dissolve={m.id: 1.0}), 4))     # where the fall left it
        m.heading = 2.0                                                            # whatever it is told since, it lies as it fell
        self.assertEqual(lying, self.picture(lv, phase=4))

    def test_one_that_breaks_is_gone(self):
        lv, m = level_with({"motion": "soldier", "break": "shards"})
        m.gone = True
        empty = self.picture(lv)
        m.gone = False
        shards = self.picture(lv, FX(dissolve={m.id: 0.4}))
        self.assertNotEqual(shards, empty)
        m.dead = True
        self.assertEqual(self.picture(lv), empty)

    def test_a_fast_one_runs(self):
        lv, m = level_with({"motion": "hyena"}, dict(GUARD, attack={"kind": "melee", "damage": [4, 6], "speed": 2}))
        lw, mw = level_with({"motion": "hyena"})
        m.heading = mw.heading = 0.0
        self.assertNotEqual(self.picture(lv, FX(pos={m.id: (m.x, m.y)}, tick=0.5), 2),
                            self.picture(lw, FX(pos={mw.id: (mw.x, mw.y)}, tick=0.5), 2))

    def test_a_level_plays_with_one(self):
        lv, m = level_with({"motion": "hyena"})
        hp = lv.player.hp
        for _ in range(4):                                                         # it is next to him: it bites
            lv.command("w")
        self.assertLess(lv.player.hp, hp)
        self.picture(lv)

        class Shown:                                                              # a console that draws what it is given
            frames = []

            def said(self, text, role):
                pass

            def play(self, level, frames, dt):
                view = View(80, 20, "pixel")
                Shown.frames += [(fx, view.render(level, fx, 0)) for fx in frames]
        lv.console = Shown()
        lv.damage([(m, 999)], "The test:")
        self.assertTrue(m.dead)
        falls = [pic for fx, pic in Shown.frames if m.id in fx.dissolve]
        self.assertEqual(len(falls), 8)                                            # as a model's end is shown: eight pictures
        self.assertGreaterEqual(len({str(p) for p in falls}), 5)                   # further down in each, until it lies
        lv.console = None
        m.gone = True
        empty = self.picture(lv)
        m.gone = False
        self.assertNotEqual(self.picture(lv), empty)                               # and there it lies


class Elsewhere(unittest.TestCase):
    def test_the_viewer_plays_it(self):
        s = viewer.Subject(model.Model("hound", {"motion": "hyena"}))
        self.assertTrue(s.moving)
        a = viewer.draw(s, "solid", 60, 20, clip="walk", at=0.0)
        b = viewer.draw(s, "solid", 60, 20, clip="walk", at=0.5)
        c = viewer.draw(s, "shaded", 60, 20)
        self.assertNotEqual(a, b)
        self.assertTrue(any(ch for row in c for ch in row))

    def test_check_says_what_is_wrong(self):
        good = {"a": {"motion": "hyena"}, "b": {"motion": {"character": "soldier", "kit": "pistols", "style": {"bounce": 1.3},
                                                         "clips": ["idle", "walk", "reload", "die"], "detail": 2, "scale": 0.5},
                                              "colors": {"torso": "#223344", "#000000": "#111111"}, "break": "fall"}}
        self.assertEqual(model.problems(good), [])
        for spec, word in (({"motion": "unicorn"}, "no character 'unicorn'"), ({"motion": 7}, "a character's name or an object"),
                           ({"motion": {"character": "soldier", "kit": "axe"}}, "kit 'axe'"),
                           ({"motion": {"character": "hyena", "kit": "rifle"}}, "carries no kit"),
                           ({"motion": {"character": "hyena", "clips": ["fly"]}}, "no clip 'fly'"),
                           ({"motion": {"character": "hyena", "style": {"bouncy": 1}}}, "style takes numbers"),
                           ({"motion": {"character": "hyena", "detail": 9}}, "detail should be"),
                           ({"motion": {"character": "hyena", "scale": 0}}, "scale should be"),
                           ({"motion": {"character": "hyena", "speed": 2}}, "does not know 'speed'"),
                           ({"motion": "hyena", "colors": {"hat": "#fff"}}, "names 'hat'"),
                           ({"motion": "hyena", "break": "melt"}, "break 'melt'"),
                           ({"parts": [{"shape": "box"}], "break": "fall"}, "break 'fall'")):
            said = model.problems({"m": spec})
            self.assertTrue(said and any(word in s for s in said), (spec, said))
        self.assertEqual(model.load({"m": {"motion": "unicorn"}}), {})              # one that does not build is left out

    def test_the_recipes(self):
        folder = tempfile.mkdtemp(prefix="clio-test-motion-")
        try:
            game = os.path.join(folder, "g")
            shutil.copytree(os.path.join(ROOT, "templates", "starter"), game)
            for name in ("soldier", "hound", "walker"):
                said = recipes.add(game, "model", name)
                self.assertIn("walks, attacks and falls", said[0])
            data = GameData(game)
            self.assertEqual(model.problems(data.models), [])
            built = model.load(data.models)
            self.assertEqual(sorted(built), ["hound", "soldier", "walker"])
            self.assertAlmostEqual(built["walker"].height, 1.0, delta=0.15)
            self.assertEqual(built["walker"].breaks, "parts")
        finally:
            shutil.rmtree(folder, True)


if __name__ == "__main__":
    unittest.main()
