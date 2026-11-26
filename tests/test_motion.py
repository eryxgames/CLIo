# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""Models moved by CLIo Motion (engine/motion): every character built as a model, its clips, what a level's
monster shows of it - striding, attacking, struck, falling and lying - the viewer, --check and the recipes."""
import json
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
        self.assertEqual(len(motion.characters()), 17)
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


class People(unittest.TestCase):
    """The four who are not soldiers, for a crowd: plain clothes, and nothing, a case or a case on wheels in the hand."""
    PEOPLE = ("person", "technician", "scientist", "hazmat")

    def test_what_they_carry(self):
        for who in self.PEOPLE:
            plain = model.Model(who, {"motion": {"character": who, "kit": "hands"}})
            case = model.Model(who, {"motion": {"character": who, "kit": "case"}})
            wheels = model.Model(who, {"motion": {"character": who, "kit": "trolley"}})
            self.assertEqual(model.problems({"a": {"motion": {"character": who, "kit": "trolley"}}}), [], who)
            self.assertNotIn("prop0", plain.groups, who)
            self.assertIn("prop0", case.groups, who)
            self.assertGreater(len(case.faces), len(plain.faces), who)
            self.assertGreater(len(wheels.faces), len(plain.faces), who)
            self.assertAlmostEqual(plain.height, 0.4 * 1.72, delta=0.06, msg=who)      # a person's height, in cells
            # the case on wheels trails behind (model space: y forward) with its wheels on the floor
            back = min(p[1] for p in wheels.verts)
            self.assertLess(back, min(p[1] for p in plain.verts) - 0.15, who)
            self.assertAlmostEqual(min(p[2] for p in wheels.verts), 0.0, delta=0.02, msg=who)
            for bad in ("rifle", "pistols", "sword"):
                said = model.problems({"a": {"motion": {"character": who, "kit": bad}}})
                self.assertTrue(said and "carries one of: case, hands, trolley" in said[0], (who, said))
        said = model.problems({"a": {"motion": {"character": "soldier", "kit": "case"}}})
        self.assertTrue(said and "carries one of: pistols, rifle, sword" in said[0], said)

    def test_they_are_dressed_differently(self):
        looks = {}
        for who in self.PEOPLE:
            m = model.Model(who, {"motion": who})
            looks[who] = sorted(set(str(f[3:]) for f in m.faces))
            self.assertEqual(model.problems({"a": {"motion": who, "colors": {"torso": "#aa3333"}}}), [], who)
        self.assertEqual(len(set(map(tuple, looks.values()))), 4, "each has colours of its own")

    def test_clips(self):
        for who, kit in (("person", "trolley"), ("technician", None), ("hazmat", "case")):
            spec = {"motion": {"character": who, "kit": kit} if kit else who}
            m = model.Model(who, spec)
            mv = m.motion
            for name in ("idle", "walk", "run", "hit", "die", "die2"):
                self.assertIsNotNone(mv.clip(name), (who, name))
            walk = mv.clip("walk")
            self.assertTrue(0.5 < walk[0] < 1.6, (who, walk[0]))
            # no weapon: an attack is a jab; it differs from standing
            self.assertIsNotNone(mv.clip("attack"), who)
            a, b = mv.pose("attack", 0.5 * mv.clip("attack")[0]), mv.pose("idle", 0.0)
            self.assertGreater(max(abs(p[i] - q[i]) for p, q in zip(a, b) for i in range(3)), 0.05, who)
        self.assertIsNone(model.Model("s", {"motion": "soldier"}).motion.clip("jab"))        # (a soldier's attack is his own)

    def test_one_in_a_level_and_live(self):
        lv, m = level_with({"motion": {"character": "person", "kit": "trolley"}})
        m.heading = 0.0
        view = View(80, 20, "pixel")
        standing = view.render(lv, FX(), 0)
        m.gone = True
        empty = view.render(lv, FX(), 0)
        m.gone = False
        self.assertNotEqual(standing, empty)
        steps = [view.render(lv, FX(pos={m.id: (m.x, m.y)}, tick=k), 3) for k in (1 / 3.0, 2 / 3.0, 1.0)]
        self.assertTrue(steps[0] != steps[1] != steps[2] and standing not in steps)
        m.dead = True                                             # it has fallen, and lies
        self.assertNotIn(view.render(lv, FX(), 0), (standing, empty))
        a = motion.Actor(model.Model("p", {"motion": {"character": "person", "kit": "trolley"}}), 1.0, 1.0, 0.0)
        for _ in range(180):
            a.step(1 / 60, speed=9.0, heading=0.0, attack=True)
        self.assertTrue(2.5 < a.speed < 3.2, a.speed)             # a case on wheels is taken at a jog, however fast it is asked
        self.assertGreater(len(a.corners()), 200)
        b = motion.Actor(model.Model("p", {"motion": "scientist"}), 1.0, 1.0, 0.0)
        for _ in range(180):
            b.step(1 / 60, speed=9.0, heading=0.0)
        self.assertGreater(b.speed, 4.5)

    def test_a_crowd_of_several_kinds(self):
        import io
        from contextlib import redirect_stdout
        import clio
        from engine import demo
        from engine.term import Term
        from test_demo import player
        self.assertEqual(motion.spec_named("traveller"), {"motion": {"character": "person", "kit": "trolley"}})
        self.assertEqual(motion.spec_named("hyena"), {"motion": "hyena"})
        self.assertIsNone(motion.spec_named("door"))                 # a recipe, but not of a moved model
        self.assertIsNone(motion.spec_named("unicorn"))
        self.assertEqual(motion.spec_named("x", {"x": {"motion": "mech"}}), {"motion": "mech"})
        kinds = list(motion.PEOPLE)
        self.assertEqual(demo.problems({"game": "rootless", "clips": [{"crowd": kinds, "views": ["pixel", "lines"]}]}), [])
        said = demo.problems({"game": "rootless", "clips": [{"crowd": ["person", "unicorn"]}]})
        self.assertTrue(len(said) == 1 and "no model 'unicorn'" in said[0], said)
        self.assertEqual(len(demo.problems({"game": "rootless", "clips": [{"crowd": ["person"] * 21}]})), 1)
        self.assertEqual(kinds[:6], ["person", "commuter", "traveller", "technician", "scientist", "hazmat"])
        p, seen, _fc = player([{"crowd": kinds, "count": 13, "seconds": 1.0, "views": ["pixel", "lines"]}], W=80, H=24)
        self.assertEqual(p.run(), "done")
        self.assertTrue(any("13 bodies of 9 kinds, each run live" in n for _t, n, _m in seen), [n for _t, n, _m in seen][:3])
        mdls = [model.Model(n, motion.spec_named(n)) for n in kinds]
        crowd = motion.Crowd([mdls[i % 6] for i in range(12)], [(2.0 + i, 3.0) for i in range(12)], (1.0, 1.0, 14.0, 6.0), seed=3)
        self.assertEqual([a.moves.character for a in crowd.actors][:6], ["person", "person", "person", "technician", "scientist", "hazmat"])
        self.assertEqual([a.moves.kit for a in crowd.actors][:6], [None, "case", "trolley", None, None, None])
        for _ in range(240):
            crowd.step(1 / 30)
        self.assertTrue(any(a.speed > 0.3 for a in crowd.actors) and all(a.speed == a.speed for a in crowd.actors))
        self.assertTrue(all(a.speed < 3.3 for a in crowd.actors if a.moves.kit == "trolley"))
        self.assertGreater(len({len(a.corners()) for a in crowd.actors}), 2)             # they are not all one body
        term = Term(out=io.StringIO(), width=80, height=24, color=0, unicode=True, animate=False, env={})
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(clio.play_crowd(term, None, "people", 12), 2)                # (nothing to draw on here)
            self.assertEqual(clio.play_crowd(term, None, "person,unicorn", 5), 2)
        self.assertEqual(out.getvalue().count("needs a terminal"), 1)
        self.assertIn("has no model 'unicorn'", out.getvalue())
        self.assertIn("--crowd people", out.getvalue())

    def test_the_recipes(self):
        folder = tempfile.mkdtemp(prefix="clio-test-people-")
        try:
            game = os.path.join(folder, "g")
            shutil.copytree(os.path.join(ROOT, "templates", "starter"), game)
            names = ("person", "commuter", "traveller", "technician", "scientist", "hazmat")
            for name in names:
                recipes.add(game, "model", name)
            data = GameData(game)
            self.assertEqual(model.problems(data.models), [])
            built = model.load(data.models)
            self.assertEqual(sorted(built), sorted(names))
            self.assertEqual(built["traveller"].motion.kit, "trolley")
            self.assertIsNone(built["technician"].motion.kit)                       # his tool box is what he starts with
            self.assertIn("prop0", built["technician"].groups)
            self.assertNotIn("prop0", built["hazmat"].groups)
            self.assertNotIn("prop0", built["scientist"].groups)
            for name in names:                                                  # a recipe is what --crowd makes of its name
                self.assertEqual(motion.spec_named(name), data.models[name], name)
        finally:
            shutil.rmtree(folder, True)


class TheWardrobe(unittest.TestCase):
    """A person dressed otherwise, of another build and height, in colours by name - and people made up."""
    RED = {"motion": {"character": "woman", "wear": {"skirt": "knee", "legs": "bare", "sleeves": "short"}, "build": 0.94,
                      "height": 1.64},
           "colors": {"top": "#b3202e", "shoe": "#8f1a26", "hair": "#2a1a14"}}

    def colours(self, m):
        return {f[4] for f in m.faces}

    def test_a_woman_in_red(self):
        colour_of = model.colour
        self.assertEqual(model.problems({"a": self.RED, "w": {"motion": "woman"}}), [])
        red, plain, man = model.Model("a", self.RED), model.Model("w", {"motion": "woman"}), model.Model("p", {"motion": "person"})
        want = colour_of("#b3202e")
        self.assertIn(want, self.colours(red))
        self.assertNotIn(want, self.colours(plain))
        n_red = sum(1 for f in red.faces if f[4] == want)
        self.assertGreater(n_red, 100)                                              # the top, and the skirt after it
        other = dict(self.RED, colors=dict(self.RED["colors"], skirt="#22252b"))
        self.assertLess(sum(1 for f in model.Model("o", other).faces if f[4] == want), 0.7 * n_red)
        self.assertGreater(len(red.faces), len(plain.faces))                        # a skirt is more to draw
        # a woman is smaller than a man unless her height says; a height is to the top of the head
        self.assertLess(plain.height, 0.96 * man.height)
        bare = dict(self.RED, motion=dict(self.RED["motion"], wear={"hair": "none"}))
        self.assertAlmostEqual(model.Model("b", bare).height, 0.4 * 1.64, delta=0.004)
        tall = model.Model("t", {"motion": {"character": "person", "height": 1.95, "wear": {"hair": "none"}}})
        self.assertAlmostEqual(tall.height, 0.4 * 1.95, delta=0.004)
        # the same joints: her clips are a woman's, and she is drawn in a level
        self.assertIsNotNone(red.motion.clip("walk"))
        self.assertEqual(len(red.motion.pose("walk", 0.3)), len(red.verts))
        self.assertNotEqual(red.motion.pose("walk", 0.3), red.motion.pose("walk", 0.6))
        lv, m = level_with(self.RED)
        view = View(80, 20, "pixel")
        with_her = view.render(lv, FX(), 0)
        m.gone = True
        self.assertNotEqual(with_her, view.render(lv, FX(), 0))

    def test_build_and_groups_and_names_together(self):
        thin = model.Model("a", {"motion": {"character": "person", "build": 0.8}})
        stout = model.Model("b", {"motion": {"character": "person", "build": 1.4}})
        self.assertGreater(max(abs(p[0]) for p in stout.verts), 1.07 * max(abs(p[0]) for p in thin.verts))
        self.assertAlmostEqual(thin.height, stout.height, delta=0.002)               # the head is as it was
        colour_of = model.colour
        both = model.Model("c", {"motion": "person", "colors": {"top": "#b3202e", "head": "#00ff00", "#3b4252": "#0000ff"}})
        seen = self.colours(both)
        for hexa in ("#b3202e", "#00ff00", "#0000ff"):                               # by name, by group, by its own colour
            self.assertIn(colour_of(hexa), seen, hexa)

    def test_what_is_wrong_is_said(self):
        for spec, word in (({"motion": {"character": "soldier", "wear": {"hat": "cap"}}}, "is for people who are not soldiers"),
                           ({"motion": {"character": "hyena", "height": 1.0}}, "is for people who are not soldiers"),
                           ({"motion": {"character": "woman", "wear": {"skirt": "mini"}}}, "wear skirt is one of: none, short, knee, long"),
                           ({"motion": {"character": "woman", "wear": {"cape": "on"}}}, "wear does not know 'cape'"),
                           ({"motion": {"character": "woman", "wear": "dress"}}, "wear should be an object"),
                           ({"motion": {"character": "person", "build": 3}}, "build should be a number from 0.6 to 1.6"),
                           ({"motion": {"character": "person", "height": "tall"}}, "height should be a number"),
                           ({"motion": "person", "colors": {"top": "red"}}, "colors 'top' should be a colour like"),
                           ({"motion": "person", "colors": {"cape": "#ffffff"}}, "nor one of its colours by name")):
            said = model.problems({"a": spec})
            self.assertTrue(len(said) == 1 and word in said[0], (spec, said))
        self.assertEqual(model.problems({"a": {"motion": {"character": "person", "wear": {"band": True, "hat": "cap"}}}}), [])

    def test_people_made_up(self):
        import random
        a = [motion.anyone(random.Random(7)) for _ in range(1)] + [motion.anyone(random.Random(7))]
        self.assertEqual(a[0], a[1])                                                 # the same seed, the same person
        rng = random.Random(11)
        specs = [motion.anyone(rng) for _ in range(60)]
        self.assertEqual(model.problems({"p%d" % i: s for i, s in enumerate(specs)}), [])
        self.assertEqual({s["motion"]["character"] for s in specs}, {"person", "woman"})
        self.assertGreater(len({json.dumps(s, sort_keys=True) for s in specs}), 55)
        self.assertTrue(any(s["motion"].get("kit") == "trolley" for s in specs) and any("skirt" in s["motion"]["wear"] for s in specs))
        built = [model.Model("p%d" % i, s) for i, s in enumerate(specs[:10])]
        self.assertGreater(len({round(m.height, 3) for m in built}), 6)
        from test_demo import player
        from engine import demo
        self.assertEqual(demo.problems({"game": "rootless", "clips": [{"crowd": "anyone", "count": 8}]}), [])
        p, seen, _fc = player([{"crowd": "anyone", "count": 7, "seconds": 0.8, "seed": 3}], W=80, H=24)
        self.assertEqual(p.run(), "done")
        self.assertTrue(any("7 people, no two alike, each run live" in n for _t, n, _m in seen), [n for _t, n, _m in seen][:2])
        p, seen, _fc = player([{"crowd": "anyone", "count": 26, "seconds": 0.5}], W=80, H=24)
        self.assertEqual(p.run(), "done")
        self.assertTrue(any("26 people of 20 kinds" in n for _t, n, _m in seen), [n for _t, n, _m in seen][:2])

    def test_the_recipes(self):
        for name in ("woman", "woman_in_red", "tourist"):
            spec = motion.spec_named(name)
            self.assertEqual(model.problems({name: spec}), [], name)
            self.assertIn(name, motion.PEOPLE)
        self.assertEqual(motion.spec_named("woman_in_red"), self.RED)


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


class InTheAirAndTheWater(unittest.TestCase):
    def test_one_that_floats_flies(self):
        wasp, dragon, hound = (model.Model(n, {"motion": n}).motion for n in ("wasp", "dragon", "hyena"))
        self.assertEqual(wasp.playing(1, "idle", 2.0, aloft=True), ("hover", 2.0))
        self.assertEqual(wasp.playing(1, "walk", 2.0, aloft=True), ("fly", 2.0))
        self.assertEqual(dragon.playing(1, "idle", 2.0, aloft=True), ("fly", 2.0))     # it cannot hang in the air
        self.assertEqual(wasp.playing(1, "walk", 2.0), ("walk", 2.0))                  # on the floor it walks
        self.assertEqual(hound.playing(1, "walk", 2.0, aloft=True), ("walk", 2.0))     # one that cannot fly walks on air
        self.assertEqual(wasp.playing(1, "attack", 2.0, aloft=True)[0], "attack")
        octo = model.Model("o", {"motion": "octopus"}).motion
        self.assertEqual(octo.playing(1, "walk", 1.0, afloat=True), ("swim", 1.0))
        self.assertEqual(octo.playing(1, "idle", 1.0, afloat=True), ("hover", 1.0))
        for mv, clip in ((wasp, "fly"), (wasp, "hover"), (dragon, "fly"), (octo, "swim")):
            low = min(p[2] for pose in mv.clip(clip)[2] for p in pose)
            self.assertTrue(0.0 < low < 0.12, (mv.character, clip, low))               # just clear of the floor: the level lifts it

    def test_in_a_level_it_flies_and_comes_down_to_lie(self):
        flier = dict(GUARD, float=0.6)
        lv, m = level_with({"motion": {"character": "wasp", "scale": 0.8}}, flier)
        lw, mw = level_with({"motion": {"character": "wasp", "scale": 0.8}})
        m.heading = mw.heading = 0.3
        view = View(80, 20, "pixel")
        up, down = view.render(lv, FX(), 0), view.render(lw, FX(), 0)
        self.assertNotEqual(up, down)

        def top(rows):                                    # the first row of the picture where the two levels differ at all
            return next(i for i, (a, b) in enumerate(zip(rows, base)) if a != b)
        m.gone = True
        base = view.render(lv, FX(), 0)
        m.gone = False
        beats = [view.render(lv, FX(pos={m.id: (m.x, m.y)}, tick=k), 1) for k in (0.3, 0.6)]
        self.assertNotEqual(beats[0], beats[1])           # its wings beat
        high = top(view.render(lv, FX(), 0))
        m.dead = True
        low = top(view.render(lv, FX(), 0))
        self.assertGreater(low, high + 2)                 # it lies on the floor, not in the air


class InLines(unittest.TestCase):
    def test_a_levels_lines_show_models_as_lines(self):
        from engine.ahead import LevelView
        lv, m = level_with({"motion": "soldier"})
        m.heading = 0.4
        view = LevelView(80, 20)

        def lit(rows):
            return sum(1 for row in rows for c in row if (c[0] if isinstance(c, (tuple, list)) else c) not in (None, " ", ""))
        standing = view.render(lv, FX(), 0)
        m.model = None                                    # as one with no model: a lamp on legs
        lamp = view.render(lv, FX(), 0)
        m.model = "g"
        self.assertGreater(lit(standing), lit(lamp) + 6)
        walking = [view.render(lv, FX(pos={m.id: (m.x, m.y)}, tick=k), 2) for k in (0.3, 0.7)]
        self.assertTrue(standing != walking[0] != walking[1])
        m.dead = True
        lying = view.render(lv, FX(), 0)
        m.gone = True
        empty = view.render(lv, FX(), 0)
        self.assertNotEqual(lying, empty)                 # the body, in lines
        self.assertNotEqual(lying, standing)

    def test_any_model_is_shown_so_and_a_broken_one_is_gone(self):
        from engine.ahead import LevelView
        from test_models import DRONE
        lv, m = level_with(DRONE)
        view = LevelView(80, 20)
        there = view.render(lv, FX(), 0)
        m.model = None
        self.assertNotEqual(there, view.render(lv, FX(), 0))
        m.model, m.dead = "g", True
        with_body = view.render(lv, FX(), 0)
        m.gone = True
        self.assertEqual(with_body, view.render(lv, FX(), 0))    # it broke into shards: nothing lies there

    def test_the_lines_are_few(self):
        for name in ("soldier", "hyena", "scorpion"):
            mv = model.Model(name, {"motion": name}).motion
            edges, faces = mv.lines()
            pts = mv.pose("walk", 0.3, lines=True)
            self.assertTrue(20 < len(edges) < 300, (name, len(edges)))
            self.assertTrue(all(0 <= a < len(pts) and 0 <= b < len(pts) for a, b in edges), name)
            self.assertNotEqual(pts, mv.pose("walk", 0.6, lines=True))


class EveryStyle(unittest.TestCase):
    def test_the_pictures_styles_all_show_it(self):
        from engine import pixels
        for style in pixels.STYLES:
            lv, m = level_with({"motion": "hyena"})
            m.heading = 0.4
            view = View(80, 20, style)
            a = view.render(lv, FX(), 0)
            b = view.render(lv, FX(pos={m.id: (m.x, m.y)}, tick=0.5), 1)
            m.gone = True
            self.assertNotEqual(a, view.render(lv, FX(), 0), style)
            self.assertNotEqual(a, b, style)

    def test_clio_picture_draws_the_same(self):
        from engine import picture
        if not picture.load():
            self.skipTest("CLIo Picture is not here")
        lv, m = level_with({"motion": "soldier"})
        m.heading = 0.4
        frames = [FX(), FX(pos={m.id: (m.x, m.y)}, tick=0.4), FX(dissolve={m.id: 0.5})]
        with_it = [View(80, 20, "pixel").render(lv, fx, 1) for fx in frames]
        was, picture._lib = picture._lib, False           # and in Python alone
        try:
            alone = [View(80, 20, "pixel").render(lv, fx, 1) for fx in frames]
        finally:
            picture._lib = was
        self.assertEqual(with_it, alone)


class OnesOwnModel(unittest.TestCase):
    """A model built on one of the skeletons (a .glb as Blender exports it, made here) and moved by it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="clio-test-motion-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def glb(self, rig_name="quad", shift=0.0, strange=True):
        from test_models import CUBE, CUBE_TRIS, Builder
        rig = motion.rig_named(rig_name)
        b = Builder()
        at = {j["name"]: (-j["o"][2] + shift, j["o"][1], j["o"][0]) for j in rig["joints"]}     # on glTF's axes
        names = [j["name"] for j in rig["joints"]]
        first = names[0]
        second = next(n for n in names if math.dist(at[n], at[first]) > 0.2)   # another joint, somewhere else
        self.pair = (first, second)
        b.doc["nodes"] = [{"name": n, "translation": list(at[n])} for n in names]
        if strange:                                       # a bone of the artist's own, on the first joint
            b.doc["nodes"][0]["children"] = [len(names)]
            b.doc["nodes"].append({"name": "Feather", "translation": [0.0, 0.1, 0.0]})
        joints = list(range(len(b.doc["nodes"])))
        ibm = []
        for i, n in enumerate(b.doc["nodes"]):
            o = at[n["name"]] if n["name"] in at else tuple(a + c for a, c in zip(at[first], n["translation"]))
            ibm.append((1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -o[0], -o[1], -o[2], 1))
        # three small cubes: on the first joint, between the first and the second (half each), on the artist's bone
        mid = tuple((a + c) / 2 for a, c in zip(at[first], at[second]))
        spots = [(at[first], [(0, 1.0)]), (mid, [(0, 0.5), (names.index(second), 0.5)])] \
            + ([(at[first], [(len(names), 1.0)])] if strange else [])
        pos, js, ws, idx = [], [], [], []
        for o, carried in spots:
            k = len(pos)
            pos += [(o[0] + 0.03 * x, o[1] + 0.03 * y, o[2] + 0.03 * z) for x, y, z in CUBE]
            js += [tuple(j for j, _w in carried) + (0,) * (4 - len(carried))] * 8
            ws += [tuple(w for _j, w in carried) + (0.0,) * (4 - len(carried))] * 8
            idx += [k + i for i in CUBE_TRIS]
        prim = {"attributes": {"POSITION": b.acc(pos, "VEC3"), "JOINTS_0": b.acc(js, "VEC4", 5121, "B"),
                               "WEIGHTS_0": b.acc(ws, "VEC4")}, "indices": b.acc(idx, "SCALAR", 5123, "H")}
        b.doc["meshes"].append({"primitives": [prim]})
        b.doc["skins"] = [{"joints": joints, "inverseBindMatrices": b.acc(ibm, "MAT4")}]
        # and a stiff piece that hangs on the second joint: a mesh that is no skin
        b.doc["meshes"].append({"primitives": [{"attributes": {"POSITION": b.acc([(0.02 * x, 0.02 * y, 0.02 * z) for x, y, z in CUBE], "VEC3")},
                                                "indices": b.acc(CUBE_TRIS, "SCALAR", 5123, "H")}]})
        b.doc["nodes"].append({"name": "Skin", "mesh": 0, "skin": 0})
        b.doc["nodes"].append({"name": "Badge", "mesh": 1, "translation": [0.0, 0.05, 0.0]})
        b.doc["nodes"][names.index(second)]["children"] = [len(b.doc["nodes"]) - 1]
        kids = {c for n in b.doc["nodes"] for c in n.get("children", [])}
        b.doc["scenes"][0]["nodes"] = [i for i in range(len(b.doc["nodes"])) if i not in kids]
        path = os.path.join(self.dir, "own.glb")
        with open(path, "wb") as f:
            f.write(b.glb())
        return path, rig

    def test_it_comes_in_with_a_skin_and_follows_the_skeleton(self):
        from engine import gltf
        path, rig = self.glb()
        spec, notes = gltf.to_model(path, scale=0.4, motion="quad")
        self.assertEqual(spec["motion"], {"character": "quad"})
        self.assertNotIn("frames", spec)
        self.assertTrue(any("Feather" in n for n in notes))
        names = spec["skin"]["joints"]
        self.assertEqual(set(names), set(self.pair))
        self.assertEqual(len(spec["mesh"]["v"]), 24)        # the artist's cube is where the first is, carried as it is: one
        rows = spec["skin"]["weights"]
        self.assertEqual(len(rows), len(spec["mesh"]["v"]))
        self.assertEqual(sorted({len(r) // 2 for r in rows}), [1, 2])          # carried by one joint, or by two
        self.assertEqual(model.problems({"own": spec}), [])
        m = model.Model("own", spec)
        self.assertEqual(m.breaks, "fall")
        self.assertEqual(m.pose("idle", 0.0) == m.verts, False)                # standing is not the template pose
        # each corner is where the library's own moves put it
        mv, cm = m.motion, motion.lib()
        index = {j["name"]: k for k, j in enumerate(rig["joints"])}
        mv.clip("walk")
        rec = motion._recorded[mv.key + ("walk",)]
        sk, worst = None, 0.0
        for pose, got in zip(rec["frames"], mv.clip("walk")[2]):
            sk = cm.rig.skeleton(mv.ch, pose, sk)
            for (x, y, z), row, g in zip(m.verts, rows, got):
                p = (-x / 0.4, z / 0.4, y / 0.4)                                # the corner at rest, on glTF's axes, in metres
                want = [0.0, 0.0, 0.0]
                for k in range(0, len(row), 2):
                    mt = cm.rig.joint_move(sk, index[names[row[k]]])
                    q = [mt[0] * p[0] + mt[4] * p[1] + mt[8] * p[2] + mt[12], mt[1] * p[0] + mt[5] * p[1] + mt[9] * p[2] + mt[13],
                         mt[2] * p[0] + mt[6] * p[1] + mt[10] * p[2] + mt[14]]
                    want = [w + row[k + 1] * c for w, c in zip(want, q)]
                worst = max(worst, math.dist(g, (-want[0] * 0.4, want[2] * 0.4, want[1] * 0.4)))
        self.assertLess(worst, 1e-9)
        self.assertGreater(far(mv.clip("walk")[2][0], mv.clip("walk")[2][4]), 0.005)   # and it does move

    def test_it_is_drawn_in_a_level_and_imported_by_the_command(self):
        import io
        from contextlib import redirect_stdout
        import clio
        path, _rig = self.glb()
        game = os.path.join(self.dir, "g")
        shutil.copytree(os.path.join(ROOT, "templates", "starter"), game)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(clio.import_model(game, path, "beast", 0.4, "quad"), 0)
        self.assertIn("moved by CLIo Motion (idle, walk", out.getvalue())
        spec = GameData(game).models["beast"]
        lv, m = level_with(dict(spec, scale=6.0))                              # (three small cubes: made big enough to see)
        view = View(80, 20, "pixel")
        a = view.render(lv, FX(), 0)
        m.gone = True
        self.assertNotEqual(a, view.render(lv, FX(), 0))

    def test_what_is_not_on_the_skeleton_is_refused(self):
        from engine import gltf
        path, _rig = self.glb(shift=0.5)                                       # its armature moved half a metre aside
        with self.assertRaises(gltf.GltfError) as e:
            gltf.to_model(path, motion="quad")
        self.assertIn("do not stand where", str(e.exception))
        path, _rig = self.glb()
        with self.assertRaises(gltf.GltfError) as e:
            gltf.to_model(path, motion="soldier")                              # another skeleton altogether
        self.assertIn("not a model on the soldier's skeleton", str(e.exception))
        with self.assertRaises(ValueError) as e:
            gltf.to_model(path, motion="unicorn")
        self.assertIn("no skeleton called 'unicorn'", str(e.exception))
        spec, _ = gltf.to_model(path, motion="quad")
        bad = dict(spec, skin=dict(spec["skin"], joints=["Nose"] + spec["skin"]["joints"][1:]))
        self.assertTrue(any("joint 'Nose'" in s for s in model.problems({"m": bad})))
        short = dict(spec, skin=dict(spec["skin"], weights=spec["skin"]["weights"][:-1]))
        self.assertTrue(any("each of the mesh's" in s for s in model.problems({"m": short})))


class Live(unittest.TestCase):
    def test_an_actor_goes_where_it_is_sent(self):
        m = model.Model("h", {"motion": "hyena"})
        a = motion.Actor(m, 5.0, 5.0, 0.0)
        self.assertAlmostEqual(a.x, 5.0, places=6)
        still = a.corners()
        for _ in range(120):
            a.step(1 / 30.0, speed=2.0, heading=0.0)
        self.assertAlmostEqual(a.x, 5.0 + 4.0 * 2.0 * 0.4, delta=0.35)          # four seconds east at 2 m/s, 0.4 cells a metre
        self.assertAlmostEqual(a.y, 5.0, delta=0.05)
        self.assertAlmostEqual(a.speed, 2.0, delta=0.05)
        for _ in range(90):
            a.step(1 / 30.0, heading=math.pi / 2)                               # south
        self.assertGreater(a.y, 5.8)
        self.assertAlmostEqual(a.heading, math.pi / 2, delta=0.1)
        moving = a.corners()
        self.assertEqual(len(moving), len(m.verts))
        self.assertLess(max(math.hypot(p[0], p[1]) for p in moving), 3 * m.radius + 0.3)   # about its own spot
        self.assertGreater(far(still, moving), 0.05)
        for _ in range(60):
            a.step(1 / 30.0, speed=0.0)
        del a.events[:]
        a.step(1 / 30.0, attack=True)
        for _ in range(30):
            a.step(1 / 30.0)
        self.assertIn("bite", a.events)
        a.step(0.0)                                                             # no time: nothing
        tall = max(p[2] for p in a.corners())
        a.step(1 / 30.0, speed=0.0, die=True)
        for _ in range(90):
            a.step(1 / 30.0)
        self.assertTrue(a.down)
        self.assertLess(max(p[2] for p in a.corners()), 0.8 * tall)
        a.stand()
        a.step(1 / 30.0)
        self.assertFalse(a.down)
        with self.assertRaises(ValueError):
            motion.Actor(model.Model("d", {"parts": [{"shape": "box"}]}))

    def test_a_level_draws_a_monster_from_its_actor(self):
        lv, m = level_with({"motion": "hyena"})
        view = View(80, 20, "pixel")
        m.heading = 0.0
        as_clip = view.render(lv, FX(), 0)
        m.actor = motion.Actor(lv.models["g"], m.x, m.y, 0.0)
        a = view.render(lv, FX(), 0)
        for _ in range(20):
            m.actor.step(1 / 30.0, speed=1.0, heading=0.0)
        b = view.render(lv, FX(), 0)
        self.assertNotEqual(a, b)                          # it has walked on, on its own feet
        self.assertNotEqual(as_clip, b)
        self.assertEqual((m.x, m.y), (2, 2))               # and the rules know nothing of it

    def test_a_crowd_wanders_and_stays_in_its_yard(self):
        m = model.Model("h", {"motion": "hyena"})
        spots = [(3 + 2 * (k % 4), 3 + 2 * (k // 4)) for k in range(12)]
        crowd = motion.Crowd(m, spots, (1.0, 1.0, 11.0, 9.0), seed=3)
        again = motion.Crowd(m, spots, (1.0, 1.0, 11.0, 9.0), seed=3)
        for _ in range(450):                               # fifteen seconds
            crowd.step(1 / 30.0)
            again.step(1 / 30.0)
        places = [(round(a.x, 6), round(a.y, 6)) for a in crowd.actors]
        self.assertEqual(places, [(round(a.x, 6), round(a.y, 6)) for a in again.actors])     # the same seed, the same wandering
        self.assertTrue(all(-1.0 < a.x < 13.0 and -1.0 < a.y < 11.0 for a in crowd.actors), places)
        self.assertGreater(sum(1 for a, s in zip(crowd.actors, spots) if math.hypot(a.x - s[0], a.y - s[1]) > 0.5), 8)
        self.assertGreater(len({round(a.heading, 2) for a in crowd.actors}), 6)              # none in step with another

    def test_the_demo_plays_a_crowd(self):
        from engine import demo
        self.assertEqual(demo.problems({"game": "rootless", "clips": [{"crowd": "hyena", "count": 8}]}), [])
        said = demo.problems({"game": "rootless", "clips": [{"crowd": "hopper"}, {"crowd": "unicorn"}, {"crowd": "hyena", "count": 0}]})
        self.assertEqual(len(said), 3)
        from test_demo import player
        p, seen, _fc = player([{"crowd": "hyena", "count": 8, "seconds": 1.0}], W=80, H=24)
        self.assertEqual(p.run(), "done")
        self.assertTrue(any("8 hyena, each run live" in n for _t, n, _m in seen))


class TheCCore(unittest.TestCase):
    """Bodies run live are stepped in CLIo Motion's C library when it is there (CLIO_MOTION_LIB, engine/motion/lib)."""

    def setUp(self):
        if motion.fast() is None:
            self.skipTest("CLIo Motion's C library is not here: %s" % motion.status())

    def test_a_body_in_c_goes_as_one_in_python(self):
        from array import array
        from engine.motion.clio_motion import native
        for name in ("hyena", "soldier"):
            m = model.Model(name, {"motion": name})
            fast = motion.Actor(m, 4.0, 5.0, 0.3)
            self.assertIsNotNone(fast.body)
            native.use(False)
            try:
                slow = motion.Actor(m, 4.0, 5.0, 0.3)
            finally:
                native.use(True)
            self.assertIsNone(slow.body)
            for i in range(150):
                how = dict(speed=1.5 if i < 100 else 0.0, heading=1.1 if i > 40 else 0.3, attack=i == 120)
                fast.step(1 / 30.0, **how)
                slow.step(1 / 30.0, **how)
            for a, b in ((fast.x, slow.x), (fast.y, slow.y), (fast.heading, slow.heading), (fast.speed, slow.speed)):
                self.assertAlmostEqual(a, b, places=6)
            self.assertLess(far(fast.corners(), slow.corners()), 1e-6, name)
            self.assertLess(far(fast.corners(lines=True), slow.corners(lines=True)), 1e-6, name)
            row = fast.packed()
            self.assertIsInstance(row, array)
            self.assertEqual(len(row), 3 * len(m.verts))
            self.assertEqual(sorted(set(fast.events)), sorted(set(slow.events)), name)
            fast.step(1 / 30.0, die=True)
            for _ in range(120):
                fast.step(1 / 30.0)
            self.assertTrue(fast.down)
            self.assertLess(max(p[2] for p in fast.corners()), 0.8 * m.height)
            fast.stand()
            fast.step(1 / 30.0)
            self.assertGreater(max(p[2] for p in fast.corners()), 0.8 * m.height)

    def test_a_model_of_ones_own_is_skinned_there_too(self):
        from engine import gltf
        from engine.motion.clio_motion import native
        own = OnesOwnModel("glb")
        own.dir = tempfile.mkdtemp(prefix="clio-test-motion-")
        self.addCleanup(shutil.rmtree, own.dir, True)
        path, _rig = own.glb()
        spec, _notes = gltf.to_model(path, scale=0.4, motion="quad")
        m = model.Model("own", spec)
        fast = motion.Actor(m, 1.0, 1.0, 0.0)
        native.use(False)
        try:
            slow = motion.Actor(m, 1.0, 1.0, 0.0)
        finally:
            native.use(True)
        for _ in range(60):
            fast.step(1 / 30.0, speed=1.0, heading=0.4)
            slow.step(1 / 30.0, speed=1.0, heading=0.4)
        self.assertLess(far(fast.corners(), slow.corners()), 1e-6)

    def test_a_level_draws_it_and_a_crowd_of_a_thousand_steps_in_a_blink(self):
        import time
        lv, m = level_with({"motion": "hyena"})
        view = View(80, 20, "pixel")
        m.actor = motion.Actor(lv.models["g"], m.x, m.y, 0.0)
        a = view.render(lv, FX(), 0)
        for _ in range(20):
            m.actor.step(1 / 30.0, speed=1.0, heading=0.0)
        self.assertNotEqual(a, view.render(lv, FX(), 0))
        mdl = model.Model("h", {"motion": "hyena"})
        crowd = motion.Crowd(mdl, [(2 + k % 40, 2 + k // 40) for k in range(1000)], (1.0, 1.0, 45.0, 30.0), seed=5)
        t = time.perf_counter()
        for _ in range(10):
            crowd.step(1 / 30.0)
        self.assertLess((time.perf_counter() - t) / 10, 0.1)       # (about 10 ms where this was written; 180 in Python)

    def test_one_with_a_ground_of_its_own_stays_in_python(self):
        m = model.Model("h", {"motion": "hyena"})
        self.assertIsNone(motion.Actor(m, 0.0, 0.0, 0.0, ground=lambda x, y: 0.1 * x).body)


class TheCrowdCommand(unittest.TestCase):
    def test_a_crowd_in_lines_and_what_is_not_there(self):
        import io
        from contextlib import redirect_stdout
        import clio
        from engine import demo
        from engine.term import Term
        from test_demo import player
        self.assertEqual(demo.problems({"game": "rootless", "clips": [{"crowd": "hyena", "views": ["lines", "pixel"]}]}), [])
        self.assertEqual(len(demo.problems({"game": "rootless", "clips": [{"models": ["hopper"], "views": ["lines"]}]})), 1)
        p, seen, _fc = player([{"crowd": "soldier", "count": 6, "seconds": 1.0, "views": ["lines"]}], W=80, H=24)
        self.assertEqual(p.run(), "done")
        self.assertTrue(any("6 soldier, each run live" in n and ("in C" in n or "Python" in n) for _t, n, _m in seen))
        term = Term(out=io.StringIO(), width=80, height=24, color=0, unicode=True, animate=False, env={})
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(clio.play_crowd(term, None, "unicorn", 5), 2)
            self.assertEqual(clio.play_crowd(term, None, "hyena", 5), 2)      # nothing to draw on here
        self.assertIn("has no model 'unicorn'", out.getvalue())
        self.assertIn("characters: dragon, hazmat, horse, hyena", out.getvalue())
        self.assertIn("needs a terminal", out.getvalue())


if __name__ == "__main__":
    unittest.main()
