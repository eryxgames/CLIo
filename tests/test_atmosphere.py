# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Light and weather (engine/atmosphere.py): how lit a level is, lamps, light that changes with events and the
time of day, rain, snow and fog - in the picture, and in what can be seen."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from engine import atmosphere, picture  # noqa: E402
from engine.firstperson import FX, View  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import Quiet, put, with_level  # noqa: E402

HALL = ["###########",
        "#.........#",
        "#.........#",
        "#....L....#",
        "#.........#",
        "#....s....#",
        "#.........#",
        "#....@....#",
        "###########"]
LEGEND = {"L": {"lamp": {"colour": [255, 120, 60], "reach": 3, "power": 1.5}},
          "s": {"sky": True}, "z": "zombie"}


def level(rows=HALL, render="mesh", **more):
    spec = {"map": rows, "legend": LEGEND, "render": render}
    spec.update(more)
    lv = Level(with_level(spec), "t", seed=1)
    lv.console = Quiet()
    return lv


def picture_of(lv, frame=False, t=0.0, W=60, VR=20):
    v = View(W, VR, "pixel", "high")
    v.use_frame = frame
    lv.beat = int(t)
    return v.render(lv, FX(tick=t - int(t), hands=False), 1)


def light(cells):
    """The picture's light: the sum of its pixels."""
    return sum(sum(fg) + sum(bg or (0, 0, 0)) for row in cells for _ch, fg, bg in row if fg)


def reds(cells):
    return sum(fg[0] - fg[2] for row in cells for _ch, fg, _bg in row if fg)


class LightTests(unittest.TestCase):
    def test_a_level_without_them_is_as_it_was(self):
        lv = level()
        self.assertIsNone(level(["#####", "#.@.#", "#####"]).atmosphere)
        self.assertIsNotNone(lv.atmosphere)                    # a lamp is enough

    def test_ambient_light_darkens_the_picture(self):
        for render in ("mesh", "classic"):
            bright = light(picture_of(level(render=render, lights={"ambient": 1.0})))
            dim = light(picture_of(level(render=render, lights={"ambient": 0.5})))
            self.assertLess(dim, bright * 0.75, render)
            self.assertGreater(dim, bright * 0.25, render)

    def test_a_lamp_lights_what_is_near_it(self):
        lv = level(lights={"ambient": 0.3})
        atm = lv.atmosphere
        atm.begin(0)
        near, far = atm.at(5, 3), atm.at(1, 7)
        self.assertGreater(near[0], far[0] + 0.5)              # its colour, warm
        self.assertGreater(near[0], near[2])
        self.assertEqual(far, (0.3, 0.3, 0.3))
        lv.cell(5, 2).kind = "wall"                            # what it cannot see, it does not light
        lv.atmosphere = atmosphere.Atmosphere(lv)
        lv.atmosphere.begin(0)
        self.assertEqual(lv.atmosphere.at(5, 1), (0.3, 0.3, 0.3))

    def test_events_change_the_light_and_switch_lamps(self):
        legend = dict(LEGEND, L={"lamp": {"reach": 3, "off_on": "cut"}})
        lv = level(legend=legend, lights={"ambient": 0.6, "events": {"alarm": {"tint": [255, 60, 40], "pulse": 0.5}}})
        before = picture_of(lv)
        lv.events.add("alarm")
        self.assertGreater(reds(picture_of(lv)), reds(before) + 1000)
        self.assertNotEqual(light(picture_of(lv, t=0.0)), light(picture_of(lv, t=1.0)))   # the alarm pulses
        atm = lv.atmosphere
        atm.begin(0)
        lit = atm.at(5, 4)
        lv.events.add("cut")
        atm.begin(0)
        self.assertLess(max(atm.at(5, 4)), max(lit))

    def test_the_day_goes_round(self):
        lv = level(lights={"day": {"beats": 100, "start": 0.0}})
        noon = lv.atmosphere.ambient(25)[0]
        night = lv.atmosphere.ambient(75)[0]
        self.assertGreater(noon, 0.9)
        self.assertLess(night, 0.3)
        self.assertGreater(lv.atmosphere.ambient(75)[1][2], lv.atmosphere.ambient(75)[1][0])   # moonlight: blue

    def test_in_the_dark_a_monster_further_off_is_not_seen(self):
        rows = list(HALL)
        rows[2] = "#....z....#"
        lv = level(rows, lights={"ambient": 0.1}, legend={"z": "zombie", "L": {}, "s": {}})
        put(lv, 5, 7, 0)
        self.assertFalse(lv.monsters[0].seen)
        lv.player.goggles = lv.player.goggles_on = 5           # the goggles see in the dark
        lv.update_seen()
        self.assertTrue(lv.monsters[0].seen)
        lit = level(rows, lights={"ambient": 0.1}, legend={"z": "zombie", "L": {"lamp": {"reach": 3}}, "s": {}})
        put(lit, 5, 7, 0)
        self.assertTrue(lit.monsters[0].seen)                  # by a lamp

    def test_clio_picture_and_the_python_light_it_alike(self):
        if picture.load() is None:
            self.skipTest("CLIo Picture is not installed")
        lv = level(lights={"ambient": 0.5}, weather={"kind": "rain", "amount": 0.7})
        for t in (0.0, 0.4):
            self.assertEqual(picture_of(lv, frame=True, t=t), picture_of(lv, frame=False, t=t))


class WeatherTests(unittest.TestCase):
    CYCLE = {"cycle": [{"beats": 10, "kind": "clear"}, {"beats": 5, "kind": "storm", "amount": 1.0}],
             "events": {"vent": {"kind": "fog", "fog": 0.4}}}

    def test_the_weather_goes_round_and_events_change_it(self):
        lv = level(weather=self.CYCLE)
        atm = lv.atmosphere
        self.assertEqual(atm.sky(3)[0], "clear")
        self.assertEqual(atm.sky(12)[0], "storm")
        self.assertEqual(atm.sky(17)[0], "clear")              # round again
        lv.events.add("vent")
        self.assertEqual(atm.sky(12)[:1] + (atm.sky(12)[3],), ("fog", 0.4))

    def test_fog_shortens_sight_both_ways(self):
        rows = list(HALL)
        rows[1] = "#....z....#"
        lv = level(rows, weather={"kind": "fog", "fog": 0.5}, legend={"z": "zombie", "L": {}, "s": {}})
        put(lv, 5, 7, 0)
        self.assertEqual(lv.atmosphere.sight(), 4)
        self.assertFalse(lv.sees(5, 7, 5, 1))
        self.assertFalse(lv.monsters[0].seen)
        self.assertTrue(lv.sees(5, 7, 5, 4))

    def test_a_storm_flashes_and_thunders(self):
        lv = level(weather={"kind": "storm", "amount": 1.0})
        flashes = [b for b in range(200) if lv.atmosphere.flash(b)]
        self.assertTrue(5 < len(flashes) < 60)
        self.assertEqual(flashes, [b for b in range(200) if lv.atmosphere.flash(b)])     # the same each time
        heard = []
        lv.sfx = lambda name, *fallback: heard.append(name)
        lv.beat = flashes[0] - 1
        lv.end_beat()
        self.assertIn("thunder", heard)
        dark = picture_of(lv, t=flashes[0] + 0.6)
        self.assertGreater(light(picture_of(lv, t=flashes[0])), light(dark))

    def test_rain_falls_only_where_the_sky_is_open(self):
        for rows, wet in ((HALL, True), ([r.replace("s", ".") for r in HALL], False)):
            dry = picture_of(level(rows, weather={"kind": "clear"}), t=0.3)
            rain = picture_of(level(rows, weather={"kind": "rain", "amount": 1.0, "fog": 0}), t=0.3)
            self.assertEqual(dry != rain, wet)

    def test_a_world_made_as_it_goes_has_its_weather(self):
        from engine.data import GameData
        from test_levels import ROOTLESS
        lv = Level(GameData(ROOTLESS), "sim1", seed=1)         # SIM-1: the fens, a world, weather going round
        self.assertIsNotNone(lv.atmosphere)
        kinds = {lv.atmosphere.sky(b)[0] for b in range(140)}
        self.assertEqual(kinds, {"clear", "rain", "storm", "fog"})
        clear = picture_of(lv, t=10.3)
        self.assertNotEqual(clear, picture_of(lv, t=75.3))     # a storm

    def test_fog_greys_what_is_far_off(self):
        clear = picture_of(level(weather={"kind": "clear"}))
        fog = picture_of(level(weather={"kind": "fog", "amount": 1.0}))
        self.assertNotEqual(clear, fog)
        self.assertEqual(clear[-1][30], fog[-1][30])           # the floor at his feet: hardly touched


class CheckTests(unittest.TestCase):
    def test_what_is_wrong_is_named(self):
        legend = dict(LEGEND, L={"lamp": {"reach": 0, "colour": "red", "flicker": 3}})
        data = with_level({"map": HALL, "legend": legend, "lights": {"ambient": "dim", "day": {"beats": 2}},
                           "weather": {"kind": "hail", "amount": 4, "cycle": [{"kind": "rain"}, "x"]}})
        got = " | ".join(q for q in validate(data) if "level 't'" in q)
        for want in ("ambient should be", "\"day\" should be", "kind 'hail'", "amount should be", "\"cycle\" should",
                     "lamp colour", "lamp reach", "lamp flicker"):
            self.assertIn(want, got)


if __name__ == "__main__":
    unittest.main()
