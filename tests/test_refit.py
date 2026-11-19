"""What E1M3 brought into the engine: switches in walls, heavy balls that roll, a machine that flies on fuel,
the sky over open cells - and the level itself, Drone Refit Assembly."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import firstperson as fp  # noqa: E402
from engine import levelbot  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_level_saves import state  # noqa: E402
from test_levels import ROOTLESS, armed, put, room_with, told, with_level  # noqa: E402


def ball(lv, tag="x1"):
    return next(m for m in lv.monsters if m.tag == tag)


class SwitchTests(unittest.TestCase):
    def test_a_switch_sets_off_its_event(self):
        lv = room_with(["#####G#",
                        "#.....#",
                        "#..@..#",
                        "###D###",
                        "#.....#",
                        "#######"], {"G": {"switch": "gate", "label": "GATE"}, "D": {"wall": "steel", "opens_on": "gate"}})
        g = lv.cell(5, 0)
        self.assertEqual((g.kind, g.solid, g.texture(), g.label), ("switch", True, "switch", "GATE"))
        put(lv, 5, 1, 0)
        lv.run_line("use")
        self.assertTrue(g.pressed)
        self.assertEqual(g.texture(), "switch_on")
        self.assertIn("gate", lv.events)
        self.assertEqual(lv.cell(3, 3).kind, "floor")             # what waited for it opened
        self.assertEqual(lv.beat, 1)
        lv.run_line("use")
        self.assertIn("thrown already", told(lv))
        self.assertEqual(lv.beat, 1)

    def test_the_check_wants_something_to_listen(self):
        data = with_level({"map": ["#G#", "#@#", "#E#"], "legend": {"G": {"switch": "nothing"}}})
        self.assertTrue(any("sets off 'nothing'" in p for p in validate(data)))


class BallTests(unittest.TestCase):
    def test_a_shoved_ball_rolls_on_and_crushes_what_it_meets(self):
        lv = room_with(["############",
                        "#@x..z.....#",
                        "############"], {"x": {"monster": "xantrium"}, "z": {"monster": "zombie", "wake_on": "never"}})
        lv.player.facing = 1
        b = ball(lv)
        z = next(m for m in lv.monsters if m.kind == "zombie")
        z.hp = 10
        lv.run_line("k")                                          # walk into it: it rolls, two cells a beat
        self.assertEqual((lv.player.x, b.x), (1, 4))
        lv.run_line("w")
        self.assertTrue(z.dead)                                   # it rolled into the zombie and on
        self.assertIn("rolls into it", told(lv))
        lv.run_line("w")
        lv.run_line("w")
        self.assertEqual(b.x, 10)                                 # to the wall
        self.assertIsNone(b.rolling)
        self.assertGreater(b.rolled, 6)

    def test_what_it_cannot_crush_stops_it_and_a_ball_knocks_a_ball_on(self):
        lv = room_with(["##########",
                        "#@x..x...#",
                        "##########"], {"x": {"monster": "xantrium"}})
        lv.player.facing = 1
        a, b = ball(lv, "x1"), ball(lv, "x2")
        lv.run_line("k")
        lv.run_line("w")
        self.assertEqual((a.x, a.rolling), (4, None))             # it stopped against the other,
        self.assertEqual(b.rolling, (1, 0))                       # which rolls on
        self.assertIn("knocks", told(lv))
        lv.run_line("w")
        lv.run_line("w")
        self.assertEqual(b.x, 8)

    def test_in_acid_it_sinks_and_makes_a_step(self):
        lv = room_with(["#######",
                        "#@x~..#",
                        "#######"], {"x": {"monster": "xantrium"}})
        lv.player.facing = 1
        b = ball(lv)
        lv.run_line("k")
        self.assertTrue(b.gone)
        self.assertTrue(lv.cell(3, 1).sunk)
        self.assertFalse(lv.cell(3, 1).toxic)

    def test_it_breaks_a_hollow_wall_and_rolls_through(self):
        lv = room_with(["#######",
                        "#@x.S.#",
                        "#######"], {"x": {"monster": "xantrium"}})
        lv.player.facing = 1
        b = ball(lv)
        lv.run_line("k")
        lv.run_line("w")
        self.assertEqual(lv.cell(4, 1).kind, "floor")
        self.assertEqual(lv.stats["secrets"], 1)
        self.assertEqual(b.x, 5)

    def test_shots_ping_off_and_a_blast_sets_it_rolling(self):
        lv = armed(room_with(["#########",
                              "#.......#",
                              "#.x.....#",
                              "#.......#",
                              "#.@.....#",
                              "#########"], {"x": {"monster": "xantrium"}}), "2", bullets=10)
        b = ball(lv)
        lv.run_line("f")
        self.assertEqual((b.hp, b.dead), (999, False))
        self.assertIn("pings off", told(lv))
        lv.blast(1, 2, 40)                                       # a blast beside it: it rolls away
        self.assertEqual(b.rolling, (1, 0))
        lv.run_line("w")
        self.assertGreater(b.x, 2)

    def test_an_event_lets_one_go_after_a_rumble(self):
        lv = room_with(["###",
                        "#O#",
                        "#T#",
                        "#k#",
                        "#.#",
                        "#.#",
                        "#@#",
                        "###"], {"O": {"monster": "xantrium_core", "wake_on": "go", "roll": "s"},
                                 "T": {"wall": "steel", "opens_on": "go"}, "k": {"item": "clip", "on_pickup": "go"}})
        core = ball(lv, "O1")
        lv.run_line("k")
        lv.run_line("k")
        lv.run_line("k")                                          # the clip: the hatch opens, and it rumbles
        self.assertEqual((core.y, core.rolling), (1, (0, 1)))
        self.assertIn("rumble", told(lv))
        hp = lv.player.hp
        lv.run_line("w")
        lv.run_line("w")                                          # it rolls a cell a beat: standing still is a mistake
        self.assertLess(lv.player.hp, hp)
        self.assertIn("rolls into you", told(lv))

    def test_a_ball_holds_a_plate_down(self):
        lv = room_with(["#######",
                        "#@x.^D#",
                        "#######"], {"x": {"monster": "xantrium"}, "^": {"plate": "p"},
                                     "D": {"door": True, "open_while": "p"}})
        lv.player.facing = 1
        lv.run_line("k")
        self.assertEqual(ball(lv).x, 4)
        self.assertTrue(lv.cell(4, 1).down)
        self.assertEqual(lv.cell(5, 1).open, 1.0)

    def test_it_turns_as_it_rolls(self):
        data = GameData(ROOTLESS)
        from engine import model
        mdl = model.load({"x": data.models["xantrium_ball"]})["x"]
        v = fp.View(60, 16)
        cam = (0.0, 1.5, 0, -1, 1, 0)
        one = [[None] * v.PW for _ in range(v.PH)]
        two = [[None] * v.PW for _ in range(v.PH)]
        v.draw_model(one, mdl, 0.0, 0.0, 0.0, "idle", 0, cam)
        v.draw_model(two, mdl, 0.0, 0.0, 0.0, "idle", 0, cam, roll=0.8)
        self.assertNotEqual(one, two)


class FlyingTests(unittest.TestCase):
    def setUp(self):
        self.lv = room_with(["#########",
                             "#...~~~.#",
                             "#.@H~~~.#",
                             "#...~~~.#",
                             "#...F...#",
                             "#########"], {"H": {"monster": "hopper"}, "F": "fuel", "~": {"toxic": True}})
        self.lv.player.facing = 1

    def test_dry_tanks_will_not_lift(self):
        lv = self.lv
        lv.run_line("k")                                          # board
        v = lv.player.vehicle
        self.assertIsNotNone(v)
        self.assertIn("tanks are dry", told(lv))
        lv.run_line("k")
        self.assertEqual(lv.player.x, 3)
        self.assertFalse(v.started)

    def test_fuel_goes_in_and_burns_once_it_lifts(self):
        lv = self.lv
        put(lv, 3, 4, 1)
        lv.run_line("k")                                          # a fuel cell, carried
        self.assertEqual(lv.player.fuel, 12)
        put(lv, 2, 2, 1)
        lv.run_line("k")                                          # boarding pours it in
        v = lv.player.vehicle
        self.assertEqual((v.fuel, lv.player.fuel), (12, 0))
        lv.run_line("k")                                          # over the acid: no harm, and the fuel burns
        lv.run_line("k")
        self.assertTrue(v.started)
        self.assertEqual((lv.player.x, lv.player.hp, v.fuel), (5, 100, 10))
        lv.run_line("out")                                        # not over acid
        self.assertIn("dry floor", told(lv))
        self.assertIs(lv.player.vehicle, v)

    def test_the_gun_never_runs_dry_and_an_empty_tank_can_end_the_level(self):
        lv = self.lv
        z = lv.add_monster("zombie", 7, 2)
        z.awake = True
        lv.run_line("k")
        v = lv.player.vehicle
        v.fuel = 3
        bullets = dict(lv.player.ammo)
        lv.run_line("k")
        lv.run_line("f")
        self.assertLess(z.hp, 20)
        self.assertEqual(lv.player.ammo, bullets)
        lv.run_line("w")
        self.assertEqual(lv.over, "exit")                         # the Swamp Hopper's "on_empty": "exit"
        self.assertIn("settles on the swamp", told(lv))


class SkyTests(unittest.TestCase):
    def test_open_cells_show_the_sky(self):
        rows = ["#######", "#.....#", "#.....#", "#..@..#", "#######"]
        shut = room_with(rows)
        sky = room_with(rows, {".": {"sky": True}, "@": {"start": True, "sky": True}})
        self.assertIsNone(shut.sky_look)
        self.assertIsNotNone(sky.sky_look)
        v = fp.View(80, 20)
        a, b = v.render(shut, fp.FX(), 0), v.render(sky, fp.FX(), 0)
        self.assertTrue(a[:3] != b[:3], "the top of the picture: ceiling against sky")
        self.assertTrue(a[-3:] == b[-3:], "the floor is the same")

    def test_the_look_of_a_sky(self):
        look = fp.sky_spec({"top": "#000010", "horizon": [200, 100, 50], "stars": 0.05,
                            "sun": {"at": 0.0, "height": 0.5, "size": 0.2, "color": "#ffffff", "bands": "#aa0000"},
                            "ridges": [{"color": "#101010", "height": 0.3}], "clouds": {"amount": 0.5}})
        self.assertEqual((look["top"], look["horizon"]), ((0, 0, 16), (200, 100, 50)))
        pic = fp.sky_picture(look, 40, 12, 0, 0.0, 0)
        self.assertEqual((len(pic), len(pic[0])), (12, 40))
        bare = fp.sky_picture(dict(look, ridges=[]), 40, 12, 0, 0.0, 0)
        self.assertNotEqual(pic[-1], bare[-1])                    # the ridge along the bottom
        self.assertEqual(pic, fp.sky_picture(look, 40, 12, 0, 0.0, 0))
        self.assertNotEqual(pic, fp.sky_picture(look, 40, 12, 1, 0.0, 0))   # another way, another sky
        data = with_level({"map": ["#E#", "#@#", "###"], "sky": "blue"})
        self.assertTrue(any("sky should be an object" in p for p in validate(data)))


class CheckTests(unittest.TestCase):
    def test_new_keys_are_checked(self):
        data = with_level({"map": ["#E#", "#x#", "#@#", "###"], "legend": {"x": {"monster": "zombie", "roll": "s"}}})
        data.monsters = dict(data.monsters, bad={"name": "bad", "kind": "ball", "roll": 0, "crush": 5, "model": "xantrium_ball",
                                                 "vehicle": {"fuel": -1, "on_empty": "fly", "gun": "yes"}})
        data.items = dict(data.items, can={"pickup": {"fuel": 0}})
        found = " | ".join(validate(data))
        for words in ("only a ball", "roll should be a whole number", "crush should be", "fuel should be a number of beats",
                      "on_empty should be", "gun should be a weapon", "item 'can': fuel should be"):
            self.assertIn(words, found)

    def test_a_ride_that_ends_the_level_is_an_exit(self):
        data = with_level({"map": ["###", "#H#", "#@#", "###"], "legend": {"H": {"monster": "hopper"}}})
        self.assertFalse(any("no exit" in p for p in validate(data)))
        data = with_level({"map": ["###", "#.#", "#@#", "###"]})
        self.assertTrue(any("no exit" in p for p in validate(data)))


class DroneRefitTests(unittest.TestCase):
    def test_the_bot_flies_out(self):
        data = GameData(ROOTLESS)
        for seed in (0, 3):
            outcome, lv = levelbot.play(data, "e1m3", seed)
            self.assertEqual(outcome, "exit", "seed %d" % seed)
            self.assertIsNotNone(lv.player.vehicle)                # it ended in the air: the fuel ran out
            self.assertEqual(lv.player.vehicle.fuel, 0)
            self.assertTrue(lv.cell(24, 0).pressed)               # the launch gate's switch was thrown

    def test_played_back_it_ends_as_it_did(self):
        data = GameData(ROOTLESS)
        outcome, lv = levelbot.play(data, "e1m3", 1)
        again = Level(data, "e1m3", seed=1)
        again.replay(lv.journal)
        self.assertEqual(state(again), state(lv))
        self.assertEqual(again.over, outcome)

    def test_the_escape_down_the_chute(self):
        lv = Level(GameData(ROOTLESS), "e1m3", seed=2)
        from test_levels import Quiet
        lv.console = Quiet()
        for m in lv.monsters:                                     # nothing else to stop for
            if not m.ball:
                m.gone = True
        put(lv, 16, 4, 0)
        lv.run_line("k")                                          # the x key: the hatch opens
        self.assertIn("x", lv.player.keys)
        lv.run_line("turn around")
        for _ in range(11):
            lv.run_line("k")
        lv.run_line("turn left; k")                               # out of the chute at the bottom, to the east
        hp = lv.player.hp
        for _ in range(6):
            lv.run_line("w")
        self.assertEqual(lv.player.hp, hp)                        # it went by
        core = next(m for m in lv.monsters if m.kind == "xantrium_core")
        self.assertEqual((core.x, core.y), (16, 18))              # through the hollow wall, into the secret
        self.assertEqual(lv.cell(16, 15).kind, "floor")

    def test_stills_of_models_for_the_editor(self):
        from engine.editor import levels as editor_levels
        info = editor_levels.info(ROOTLESS) if hasattr(editor_levels, "info") else None
        data = GameData(ROOTLESS)
        from engine import model
        rows = fp.model_still(model.load({"h": data.models["hopper"]})["h"])
        self.assertTrue(rows and 0 < len(rows) <= 24 and len(rows[0]) <= 24)
        if info is not None:
            self.assertIsNotNone(info["things"]["hopper"]["picture"])


if __name__ == "__main__":
    unittest.main()
