# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""First-person levels in Rootless: the picture, the level's rules, the game played through."""
import copy
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import keys as keys_mod  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.firstperson import FX, STYLES, View  # noqa: E402
from engine.level import Level, TextConsole, validate  # noqa: E402
from engine.term import Term  # noqa: E402

ROOTLESS = os.path.join(ROOT, "games", "rootless")


class Quiet(TextConsole):
    """A console that answers from a list and keeps what it was told."""

    def __init__(self, lines=()):
        self.lines = list(lines)
        self.told = []
        super().__init__(self.told.append, lambda prompt: self.lines.pop(0) if self.lines else None)

    def page(self, lv, lines, automap=False):
        self.told.append(lines)


def level(seed=1):
    lv = Level(GameData(ROOTLESS), "e1m1", seed=seed)
    lv.console = Quiet()
    return lv


def put(lv, x, y, facing):
    lv.player.x, lv.player.y, lv.player.facing = x, y, facing
    lv.update_seen()


class LevelTests(unittest.TestCase):
    def test_the_map(self):
        lv = level()
        self.assertEqual((lv.player.x, lv.player.y, lv.player.facing), (15, 28, 0))
        self.assertEqual(lv.total_secrets, 5)
        z1 = next(m for m in lv.monsters if m.tag == "z1")
        self.assertEqual((z1.x, z1.y), (16, 25))              # numbered in the order they are met
        self.assertIsNotNone(lv.boss)
        self.assertEqual(validate(lv.data), [])

    def test_turning_is_free_and_walking_is_a_beat(self):
        lv = level()
        lv.run_line("turn right")
        self.assertEqual((lv.player.facing, lv.beat), (1, 0))
        lv.run_line("j")
        self.assertEqual(((lv.player.x, lv.player.y), lv.beat), ((14, 28), 1))
        lv.run_line("h")                                       # strafe left = north when facing east
        self.assertEqual((lv.player.x, lv.player.y), (14, 27))

    def test_doors_and_keys(self):
        lv = level()
        put(lv, 15, 25, 0)
        lv.run_line("k")                                       # bump: the door opens
        self.assertEqual(lv.cell(15, 24).open, 1.0)
        put(lv, 15, 12, 0)
        lv.run_line("use")
        self.assertLess(lv.cell(15, 11).open, 1.0)
        self.assertIn("Permission denied", lv.log[-1][0])
        lv.player.keys.add("x")
        lv.run_line("use")
        self.assertEqual(lv.cell(15, 11).open, 1.0)

    def test_pickups(self):
        lv = level()
        med = next(it for it in lv.items if it.iid == "medkit")
        put(lv, med.x, med.y + 1, 0)
        lv.player.x, lv.player.y = med.x, med.y
        lv.arrive()
        self.assertFalse(med.taken)                            # full health: left for later
        lv.player.hp = 50
        lv.arrive()
        self.assertTrue(med.taken)
        self.assertEqual(lv.player.hp, 75)
        gun = next(it for it in lv.items if it.iid == "shotgun")
        lv.player.x, lv.player.y = gun.x, gun.y
        lv.arrive()
        self.assertIn("3", lv.player.weapons)
        self.assertEqual(lv.player.ammo["shells"], 8)

    def test_secrets(self):
        lv = level()
        put(lv, 18, 26, 1)                                     # facing the hollow wall of the boot bay
        lv.run_line("1")
        lv.run_line("f")
        self.assertEqual(lv.cell(19, 26).kind, "floor")
        self.assertEqual(lv.stats["secrets"], 1)
        put(lv, 12, 17, 3)                                     # the vent in the hall, three cells away
        for m in lv.monsters:
            m.dead = True                                      # nothing else to aim at
        lv.run_line("2")
        lv.run_line("f")
        self.assertEqual(lv.cell(9, 17).kind, "floor")
        self.assertEqual(lv.stats["secrets"], 2)

    def test_hazmat_boots_and_the_acid_vat(self):
        lv = level()
        put(lv, 15, 22, 3)                                     # the dented vent in the corridor's wall
        for m in lv.monsters:
            m.dead = True
        lv.run_line("f")
        self.assertEqual(lv.cell(14, 22).kind, "floor")
        self.assertEqual(lv.stats["secrets"], 1)
        boots = next(it for it in lv.items if it.iid == "boots")
        self.assertEqual((boots.x, boots.y), (12, 23))
        lv.player.x, lv.player.y = boots.x, boots.y
        lv.arrive()
        self.assertEqual(lv.player.boots, 20)
        self.assertEqual(lv.player.keep()["boots"], 20)       # they go on to the next level
        put(lv, 26, 23, 3)                                     # on the vat's ledge, the acid ahead
        hp = lv.player.hp
        for _ in range(3):
            lv.run_line("k")
        self.assertEqual((lv.player.x, lv.player.y, lv.player.hp, lv.player.boots), (23, 23, hp, 17))
        lv.player.boots = 1
        lv.run_line("j")                                       # the last beat the rubber holds
        self.assertEqual((lv.player.hp, lv.player.boots), (hp, 0))
        self.assertIn("eaten through", " ".join(str(t) for t in lv.console.told))
        lv.run_line("j")
        self.assertEqual(lv.player.hp, hp - 5)                 # and then it burns (armour 0)
        ring = next(it for it in lv.items if it.iid == "armor_ring0")
        lv.player.x, lv.player.y = ring.x, ring.y
        lv.arrive()
        self.assertEqual(lv.player.armor, 200)

    def test_the_key_room_closets(self):
        lv = level()
        key = next(it for it in lv.items if it.iid == "key_x")
        daemon = next(m for m in lv.monsters if m.kind == "daemon")
        self.assertFalse(daemon.awake)
        lv.player.x, lv.player.y = key.x, key.y
        lv.arrive()
        self.assertIn("keyroom", lv.events)
        self.assertEqual(lv.cell(29, 14).kind, "floor")
        self.assertTrue(daemon.awake)

    def test_cron_waits_then_fights_then_escapes(self):
        lv = level()
        cron = lv.boss
        put(lv, 15, 12, 0)
        lv.player.keys.add("x")
        lv.run_line("use")
        lv.damage([(cron, 50)])
        self.assertEqual(cron.hp, cron.max_hp)                 # not time yet
        put(lv, 15, 11, 0)
        lv.run_line("k")                                       # onto the trap: the door shuts
        self.assertIn("arena", lv.events)
        self.assertLess(lv.cell(15, 11).open, 1.0)
        self.assertTrue(cron.awake)
        for _ in range(3):
            lv.end_beat()
        self.assertTrue(lv.marks)                              # the crontab's rain, a beat ahead
        lv.damage([(cron, int(cron.max_hp * 0.6))])
        self.assertTrue(cron.enraged)
        lv.damage([(cron, int(cron.max_hp * 0.3))])
        self.assertTrue(cron.gone)
        self.assertFalse(cron.dead)                            # escaped, not killed
        self.assertEqual(lv.cell(15, 3).open, 1.0)             # the sealed door to the exit
        self.assertEqual(lv.cell(15, 11).open, 1.0)

    def test_the_exit(self):
        lv = level()
        put(lv, 15, 1, 0)
        lv.run_line("use")
        self.assertEqual(lv.over, "exit")
        self.assertTrue(any("FINISHED" in t for t, _r in lv.end_lines()))


class ShellLineTests(unittest.TestCase):
    def test_and_or_alias_history(self):
        lv = level()
        put(lv, 13, 28, 0)
        lv.run_line("k && k")
        self.assertEqual((lv.player.x, lv.player.y), (13, 26))
        put(lv, 12, 28, 0)
        lv.run_line("h || l")                                  # a wall on the left: go right instead
        self.assertEqual((lv.player.x, lv.player.y), (13, 28))
        lv.run_line("alias two='k; k'")
        lv.run_line("two")
        self.assertEqual((lv.player.x, lv.player.y), (13, 26))
        lv.run_line("!!")
        self.assertEqual((lv.player.x, lv.player.y), (13, 25))   # blocked by the wall after one step
        lv.run_line("xyzzy; k")
        self.assertIn("command not found", lv.log[-1][0])

    def test_a_surprise_stops_the_line(self):
        lv = level()
        lv.player.keys.add("x")
        put(lv, 15, 12, 0)
        lv.run_line("use")
        put(lv, 15, 11, 0)
        lv.run_line("k; k; k")                                 # the first step springs the arena's trap
        self.assertEqual((lv.player.x, lv.player.y), (15, 10))
        self.assertIn("^C", " ".join(t for t, _r in lv.log))

    def test_sudo(self):
        lv = level()
        lv.run_line("sudo rm -rf /")
        self.assertIn("sudoers", lv.log[-1][0])


class CombatTests(unittest.TestCase):
    def test_no_barrel_at_arms_length(self):
        lv = level()
        for m in lv.monsters:
            if not m.barrel:
                m.dead = True
        put(lv, 17, 26, 0)                                     # the barrel b1 right in front
        self.assertEqual(lv.cone()[0].tag, "b1")
        lv.run_line("f")
        self.assertFalse(lv.monster_at(17, 25).dead)
        lv.run_line("f b1")                                    # on purpose: it goes off, and it hurts
        self.assertLess(lv.player.hp, 100)

    def test_a_barrel_takes_its_neighbours(self):
        lv = level()
        put(lv, 15, 28, 0)
        b1 = lv.monster_at(17, 25)
        z1 = lv.monster_at(16, 25)
        lv.damage([(b1, 5)])
        self.assertTrue(z1.dead)


class PictureTests(unittest.TestCase):
    def test_walls_beside_the_player_run_off_the_picture(self):
        for x, y, f in ((15, 22, 0), (15, 21, 0), (15, 23, 2)):  # a corridor, a doorway, the corridor turned round
            lv = level()
            lv.cell(15, 21).open = 1.0
            put(lv, x, y, f)
            v = View(80, 17, "pixel")
            v.render(lv, FX(), 0)
            for col in (0, 79):                                # what is seen at both edges is the near wall
                self.assertLess(v.cover[(8, col)], 0.0, (x, y, col))
        lv = level()
        put(lv, 15, 26, 0)                                     # in a room: the far wall is what is seen there
        v = View(80, 17, "pixel")
        v.render(lv, FX(), 0)
        self.assertGreater(v.cover[(8, 40)], 0.5)

    def test_a_punch_keeps_the_arm_on(self):
        lv = level()
        put(lv, 15, 27, 0)
        lv.player.weapon = "1"
        sleeve = set(lv.sprites["w_fist"].rows[-1]) - {None}
        for rec in (0, -3):
            bottom = View(80, 17, "pixel").render(lv, FX(recoil=rec), 0)[-1]
            self.assertTrue({bottom[40][1], bottom[40][2]} <= sleeve, rec)


    def test_every_style(self):
        lv = level()
        put(lv, 15, 20, 0)
        for style in STYLES:
            for W, VR in ((80, 17), (40, 11)):
                cells = View(W, VR, style).render(lv, FX(hurt=0.5, booms=[(15, 17, 0.3)], shake=1), 1)
                self.assertEqual(len(cells), VR, style)
                self.assertTrue(all(len(r) == W for r in cells), style)

    def test_labels_behind_walls_are_hidden(self):
        lv = level()
        put(lv, 15, 28, 0)
        lv.update_seen()
        self.assertTrue(lv.monster_at(16, 25).seen)
        put(lv, 13, 22, 0)                                     # inside the wall west of the corridor: no sight
        self.assertFalse(any(m.seen for m in lv.monsters if m.kind == "zombie"))


def with_level(lv_spec, tiles=None, weapons=None):
    """Rootless's data with one more level (and tiles, weapons) in it, as the editor's demo room does."""
    data = GameData(ROOTLESS)
    data.levels = dict(data.levels, t=lv_spec)
    if tiles is not None:
        data.tiles = dict(data.tiles, **tiles)
    if weapons is not None:
        data.weapons = weapons
    return data


SOLID = {"pixels": ["aa", "aa"], "palette": {"a": "#ff0000"}}


class TileTests(unittest.TestCase):
    ROOM = ["#####", "#...#", "#...#", "#.@.#", "#####"]

    def picture(self, data, style="pixel"):
        lv = Level(data, "t", seed=1)
        lv.weapons = {}
        return View(80, 17, style).render(lv, FX(), 0)

    def test_the_engines_tiles_as_data_and_back(self):
        from engine.firstperson import TEXTURES, tile_data, tile_frames
        for name in ("steel", "door_x", "hazard", "exit"):
            self.assertEqual(tile_frames(tile_data(name))[0], TEXTURES[name], name)

    def test_a_games_tile_on_walls_floor_and_ceiling(self):
        reds = lambda cells: sum(1 for row in cells for c in row for col in c[1:] if col and col[0] > 2 * (col[1] + col[2]) and col[0] > 60)  # noqa: E731
        plain = reds(self.picture(with_level({"map": self.ROOM})))
        self.assertEqual(plain, 0)
        walls = reds(self.picture(with_level({"map": self.ROOM, "legend": {"#": {"wall": "red"}}}, {"red": SOLID})))
        floor = reds(self.picture(with_level({"map": self.ROOM, "floor": "red"}, {"red": SOLID})))
        ceiling = reds(self.picture(with_level({"map": self.ROOM, "ceiling": "red"}, {"red": SOLID})))
        mine = reds(self.picture(with_level({"map": self.ROOM}, {"steel": SOLID})))     # the engine's steel, replaced
        self.assertTrue(walls > 1000 and floor > 300 and ceiling > 300 and mine > 1000, (walls, floor, ceiling, mine))
        self.assertGreater(walls, floor)

    def test_clear_pixels_show_what_is_behind(self):
        bars = {"pixels": ["a.a.", "a.a.", "a.a.", "a.a."], "palette": {"a": "#808080"}}
        room = ["#####", "#...#", "#=#=#", "#.@.#", "#####"]
        solid = self.picture(with_level({"map": room, "legend": {"=": {"wall": "steel"}}}))
        seen = self.picture(with_level({"map": room, "legend": {"=": {"wall": "bars"}}}, {"bars": bars}))
        self.assertNotEqual(solid, seen)
        lv = Level(with_level({"map": room, "legend": {"=": {"wall": "bars"}}}, {"bars": bars}), "t")
        self.assertIn("bars", lv.see_through)
        self.assertTrue(lv.cell(1, 2).solid)                  # it still stops the player, shots and sight

    def test_tiles_change_a_beat_at_a_time(self):
        blink = {"pixels": ["a"], "frames": [["b"]], "palette": {"a": "#ff0000", "b": "#0000ff"}}
        lv = Level(with_level({"map": self.ROOM, "legend": {"#": {"wall": "blink"}}}, {"blink": blink}), "t")
        self.assertEqual(View.texture(lv, "blink", 0), [[(255, 0, 0)]])
        self.assertEqual(View.texture(lv, "blink", 1), [[(0, 0, 255)]])

    def test_problems_with_tiles_and_weapons(self):
        data = with_level({"map": ["#####", "#.@.E", "#####"], "legend": {".": {"floor": "nowhere"}}, "ceiling": "nada"},
                          {"odd": {"pixels": ["ab"], "palette": {"a": "#fff"}}},
                          {"9": {"name": "x", "damage": 5, "kind": "laser", "sprite": "w_none"}})
        said = " | ".join(validate(data))
        for words in ("unknown tile 'nowhere'", "unknown tile 'nada'", "tile 'odd' uses letters", "damage should be",
                      "kind should be gun, melee, rocket or grenade", "no sprite 'w_none'"):
            self.assertIn(words, said)

    def test_weapons_json_over_game_json(self):
        data = GameData(ROOTLESS)
        self.assertNotIn("weapons", data.config["first_person"])
        lv = Level(data, "e1m1")
        self.assertEqual(lv.weapons["3"]["pellets"], 7)
        data.weapons = dict(data.weapons, **{"5": {"name": "nail gun", "ammo": "nails", "damage": [3, 6]}})
        self.assertEqual(Level(data, "e1m1").weapons["5"]["name"], "nail gun")

    def test_the_bot_finds_an_exit_on_any_wall(self):
        from engine import levelbot
        data = with_level({"map": ["#######", "#.....#", "#.@...E", "#######"]})
        outcome, lv = levelbot.play(data, "t", 1)
        self.assertEqual(outcome, "exit")


class PhysicsTests(unittest.TestCase):
    def test_a_crate_on_the_plate_holds_the_door(self):
        lv = level()
        door, plate = lv.cell(21, 19), lv.cell(17, 20)
        self.assertTrue(lv.cell(17, 19).crate and door.solid)
        put(lv, 17, 21, 0)                                     # from the plate's south side: stand on it
        lv.player.x, lv.player.y = 17, 20
        lv.plates()
        self.assertTrue(plate.down and door.open == 1.0)       # a person is weight too
        lv.player.x, lv.player.y = 16, 20
        lv.plates()
        self.assertTrue(not plate.down and door.open == 0.0)   # off it: the door shuts
        put(lv, 17, 18, 2)                                     # north of the crate, facing south
        lv.run_line("k")                                       # push it onto the plate
        self.assertEqual(((lv.player.x, lv.player.y), lv.cell(17, 20).crate, plate.down, door.open), ((17, 19), True, True, 1.0))
        lv.run_line("k")                                       # it will not go into the wall
        self.assertEqual((lv.player.x, lv.player.y), (17, 19))
        put(lv, 20, 19, 1)
        lv.run_line("k")                                       # into the doorway: a secret area
        self.assertEqual(lv.stats["secrets"], 1)
        lv.run_line("k")
        self.assertEqual(lv.player.goggles, 39)                # 40 beats, one gone already
        self.assertEqual(door.open, 1.0)

    def test_a_crate_sinks_into_acid(self):
        lv = level()
        put(lv, 28, 23, 3)
        lv.run_line("k")
        c = lv.cell(26, 23)
        self.assertTrue(c.sunk and not c.toxic and not c.crate and not lv.cell(27, 23).crate)
        hp = lv.player.hp
        lv.run_line("k")                                       # onto the crate's step: no burn
        self.assertEqual(((lv.player.x, lv.player.y), lv.player.hp), ((26, 23), hp))

    def test_the_lift_and_the_teleporter(self):
        lv = level()
        put(lv, 11, 23, 0)
        lv.run_line("use")
        self.assertEqual((lv.player.x, lv.player.y), (31, 23))
        lv.run_line("use")
        self.assertEqual((lv.player.x, lv.player.y), (11, 23))
        put(lv, 23, 25, 2)
        lv.run_line("k")                                       # onto the island's pad: to the ledge, facing west
        self.assertEqual((lv.player.x, lv.player.y, lv.player.facing), (30, 23, 3))
        put(lv, 29, 23, 1)
        lv.run_line("k")                                       # the ledge's pad only receives
        self.assertEqual((lv.player.x, lv.player.y), (30, 23))

    def test_knocked_back_into_acid(self):
        lv = level()
        z = next(m for m in lv.monsters if m.tag == "z1")
        for m in lv.monsters:
            if m is not z:
                m.dead = True
        z.x, z.y, z.hp, z.awake = 23, 17, 200, True
        put(lv, 24, 17, 3)                                     # in the acid corridor, facing west
        lv.player.weapons.append("3"); lv.player.weapon = "3"; lv.player.ammo["shells"] = 9
        lv.cell(23, 17).toxic = False                          # z1 stands at the edge; behind it, acid
        lv.cell(22, 17).toxic = True
        lv.run_line("f z1")
        self.assertIn("thrown back into the acid", " ".join(str(t) for t in lv.console.told))
        z.x, z.y, z.awake, z.wake_on = 22, 17, False, "never"  # held there a beat
        hp = z.hp
        lv.run_line("w")
        self.assertLess(z.hp, hp)                              # it burns there

    def test_a_blast_throws_and_tears(self):
        lv = level()
        b = next(m for m in lv.monsters if m.barrel and (m.x, m.y) == (17, 25))
        z = next(m for m in lv.monsters if (m.x, m.y) == (16, 25))
        for m in lv.monsters:
            if m not in (b, z):
                m.dead = True
        z.hp = 300
        lv.explode(b)
        self.assertEqual((z.x, z.y), (15, 25))                 # thrown a cell away
        z.hp = 10
        lv.damage([(z, 60)], lead="BLAM.")                    # overkill: it comes apart (only seen; nothing else changes)
        self.assertTrue(z.dead)

    def test_problems_with_pairs(self):
        data = with_level({"map": ["#######", "#.@.ab#", "#..h.E#"],
                           "legend": {"a": {"teleport": "one"}, "b": {"lift": "solo"}, "h": {"door": True, "open_while": "nobody"}}})
        said = " | ".join(validate(data))
        for words in ("teleporter 'one' has one pad", "lift 'solo' should have two ends", "no plate called 'nobody'"):
            self.assertIn(words, said)

    def test_new_things_in_the_picture(self):
        from engine.firstperson import Bits
        lv = level()
        put(lv, 17, 17, 2)                                     # looking at the crate and the plate
        plain = View(80, 17, "pixel").render(lv, FX(), 0)
        bits = Bits(lv.vrng).burst(17, 19, 0.5, [(255, 0, 255)], n=20).frames(2)
        flying = View(80, 17, "pixel").render(lv, FX(parts=bits[1], casing=0.5), 0)
        self.assertNotEqual(plain, flying)
        self.assertTrue(any((255, 0, 255) in c for row in flying for c in row))
        lv.player.goggles, lv.player.goggles_on = 5, True
        green = View(80, 17, "dots").render(lv, FX(), 0)
        self.assertEqual(len(green), 17)

    def test_low_detail_draws_the_floor_at_half_width(self):
        lv = level()
        put(lv, 15, 22, 0)
        high = View(120, 20, "pixel", "high")
        low = View(120, 20, "pixel", "low")
        self.assertEqual(View(120, 20, "pixel").render(lv, FX(), 0), high.render(lv, FX(), 0))   # high by default
        floor = low._backdrop(lv, 15, 22, 0, 0)
        row = floor[-1]
        self.assertTrue(all(row[x] == row[x + 1] for x in range(0, len(row) - 1, 2)))         # pairs of pixels
        self.assertNotEqual(floor, high._backdrop(lv, 15, 22, 0, 0))
        self.assertEqual(len(low.render(lv, FX(), 0)[0]), 120)
        self.assertEqual(View(120, 20, "pixel", "auto").detail, "high")                          # a small picture
        self.assertEqual(View(300, 34, "dots", "auto").detail, "low")                            # 600 x 136 dots
        from engine.level import FrameConsole
        con = FrameConsole(Term(out=io.StringIO(), width=80, height=24, color=3, unicode=True, animate=False,
                                env={}), "pixel", keys=False, detail="nonsense")
        self.assertEqual(con.detail, "auto")

    def test_the_goggles_go_on_and_off(self):
        lv = level()
        p = lv.player
        lv.run_line("goggles")
        self.assertIn("no goggles", told(lv))
        p.goggles, p.goggles_on, p.had_goggles = 10, True, True
        self.assertTrue(p.nightvision)
        lv.run_line("w")
        self.assertEqual(p.goggles, 9)                         # on: the battery runs down
        lv.run_line("goggles off")
        self.assertFalse(p.nightvision)
        beat = lv.beat
        lv.run_line("w; w; w")
        self.assertEqual((p.goggles, lv.beat), (9, beat + 3))  # off: it keeps; taking them off costs no beat
        lv.run_line("goggles")                                 # a toggle
        self.assertTrue(p.nightvision)
        lv.run_line("goggles on")
        self.assertIn("already on", told(lv))
        p.goggles = 1
        lv.run_line("w")
        self.assertFalse(p.goggles or p.goggles_on)
        lv.run_line("goggles")
        self.assertIn("battery is flat", told(lv))
        from engine.level import KEYMAP
        self.assertEqual(KEYMAP["f2"], "goggles")


def room_with(rows, legend=None, monsters=None, seed=1):
    """A small level of its own (Rootless's monsters, items and sounds), with the player told quietly."""
    data = with_level({"map": rows, "legend": dict({"b": "barrel", "z": "zombie"}, **(legend or {}))})
    if monsters:
        data.monsters = dict(data.monsters, **monsters)
    lv = Level(data, "t", seed=seed)
    lv.console = Quiet()
    return lv


def told(lv):
    return " | ".join(str(t) for t in lv.console.told)


class FloorAndFireTests(unittest.TestCase):
    def test_sliding_on_slick_floor(self):
        lv = room_with(["########",
                        "#@;;m;.#",
                        "########"], {"m": {"item": "medkit", "slick": True}}, seed=1)
        lv.player.facing, lv.player.hp = 1, 50
        lv.run_line("k")                                       # on to the slick: on and on, to the dry floor
        self.assertEqual((lv.player.x, lv.player.y), (6, 1))
        self.assertGreater(lv.player.hp, 50)                   # the medkit on the way is taken
        self.assertIn("You slide on the slick floor", told(lv))
        put(lv, 6, 1, 3)
        lv.run_line("k")
        self.assertEqual((lv.player.x, lv.player.y), (1, 1))   # and back to the wall

    def test_a_crate_slides_and_a_barrel_rolls(self):
        lv = room_with(["#########",
                        "#@&;;;..#",
                        "#.b;;;..#",
                        "#########"])
        lv.player.facing = 1
        lv.run_line("k")                                       # the crate slides across the slick part
        self.assertTrue(lv.cell(6, 1).crate and not lv.cell(2, 1).crate)
        b = next(m for m in lv.monsters if m.barrel)
        put(lv, 1, 2, 1)
        lv.run_line("k")                                       # a barrel rolls the same way
        self.assertEqual(((b.x, b.y), (lv.player.x, lv.player.y)), ((6, 2), (2, 2)))
        self.assertIn("You roll the barrel and it slides", told(lv))

    def test_fire_runs_along_oil_and_burns_out(self):
        lv = room_with(["#########",
                        "#@.::::.#",
                        "#########"])
        self.assertTrue(lv.cell(3, 1).oil and lv.cell(3, 1).slick)
        self.assertFalse(lv.ignite(0, 1))                      # walls do not burn
        lv.ignite(3, 1)
        self.assertEqual(lv.fires[(3, 1)], 5)                  # oil burns longer
        lv.end_beat()
        self.assertIn((4, 1), lv.fires)                        # along the oil...
        self.assertNotIn((2, 1), lv.fires)                     # ...not over bare floor
        for _ in range(12):
            lv.end_beat()
        self.assertFalse(lv.fires)
        self.assertTrue(all(lv.cell(x, 1).scorched and not lv.cell(x, 1).oil for x in range(3, 7)))
        self.assertIn("Fire runs along the oil", told(lv))

    def test_standing_in_fire_and_a_barrel_in_it(self):
        lv = room_with(["#######",
                        "#@..b.#",
                        "#######"])
        hp = lv.player.hp
        lv.ignite(1, 1)
        lv.ignite(4, 1)
        lv.end_beat()
        self.assertEqual(lv.player.hp, hp - 6)
        self.assertIn("standing in fire", told(lv))
        self.assertTrue(next(m for m in lv.monsters if m.barrel).dead)    # it went off

    def test_belts_carry_the_player_items_and_crates(self):
        lv = room_with(["##########",
                        "#@>>>>C>~#",
                        "#...m....#",
                        "##########"],
                       {">": {"conveyor": "e"}, "C": {"crate": True, "conveyor": "e"},
                        "m": {"item": "medkit", "conveyor": "w"}})
        put(lv, 2, 1, 0)
        lv.end_beat()
        self.assertEqual((lv.player.x, lv.player.y), (3, 1))
        self.assertTrue(lv.cell(7, 1).crate)                   # the crate one on
        medkit = next(it for it in lv.items if it.iid == "medkit")
        self.assertEqual((medkit.x, medkit.y), (3, 2))
        lv.end_beat()
        self.assertTrue(lv.cell(8, 1).sunk and not lv.cell(8, 1).toxic)   # into the acid: a step
        self.assertIn("The belt carries you on", told(lv))

    def test_a_monster_rides_a_teleporter(self):
        lv = room_with(["###########",
                        "#@.......z#",
                        "#.#######T#",
                        "#T........#",
                        "###########"], {"T": {"teleport": "pad"}})
        z = next(m for m in lv.monsters if m.tag == "z1")
        z.awake = True
        for _ in range(3):
            lv.end_beat()
            if (z.x, z.y) == (1, 3) or z.y == 3 and z.x < 4:
                break
        self.assertEqual(z.y, 3)                               # it took the pad by the player, not the long way
        self.assertLess(z.x, 4)


class NewEnemyTests(unittest.TestCase):
    def test_the_flamethrower_sprays_when_in_line(self):
        shred = copy.deepcopy(GameData(ROOTLESS).monsters["shred"])
        shred["attack"]["eager"] = 1.0
        lv = room_with(["########",
                        "#@...f.#",
                        "########"], {"f": "shred"}, {"shred": shred})
        f = next(m for m in lv.monsters if m.kind == "shred")
        f.awake = True
        put(lv, 2, 1, 1)
        hp = lv.player.hp
        lv.end_beat()
        self.assertEqual(f.intent, "windup")
        self.assertIn("levels its nozzle", told(lv))
        lv.end_beat()
        self.assertLess(lv.player.hp, hp)
        self.assertIn((3, 1), lv.fires)                        # the floor it sprayed burns on
        f.hp = 1
        lv.player.facing = 1
        lv.run_line("f")
        self.assertTrue(f.dead)
        self.assertIn("tanks burst", told(lv))
        self.assertIn((f.x, f.y), lv.fires)

    def test_the_minigun_spins_up_and_winds_down(self):
        lv = room_with(["##########",
                        "#@......L#",
                        "#.########",
                        "##########"], {"L": "spinlock"})
        L = next(m for m in lv.monsters if m.kind == "spinlock")
        L.awake = L.seen = True
        hp = lv.player.hp
        lv.end_beat()
        self.assertEqual((L.spin, L.spun, L.intent), (1, False, "spin"))
        self.assertIn("barrels start to spin", told(lv))
        lv.end_beat()
        self.assertTrue(L.spun)
        self.assertEqual(lv.player.hp, hp)                     # two beats of warning
        put(lv, 1, 2, 0)                                       # out of its sight
        lv.end_beat()
        self.assertEqual((L.spin, L.spun), (0, False))       # unseen, so untold

    def test_kworker_sidesteps(self):
        kw = copy.deepcopy(GameData(ROOTLESS).monsters["kworker"])
        kw["dodge"] = 1.0
        lv = room_with(["#######",
                        "#.....#",
                        "#@..k.#",
                        "#.....#",
                        "#######"], {"k": "kworker"}, {"kworker": kw})
        k = next(m for m in lv.monsters if m.kind == "kworker")
        k.awake = True
        put(lv, 1, 2, 1)
        lv.run_line("f")
        self.assertEqual(k.hp, kw["hp"])
        self.assertIn("sidesteps your shot", told(lv))
        self.assertEqual(k.x, 4)
        self.assertNotEqual(k.y, 2)

    def test_the_new_monsters_have_pictures_pages_and_sounds(self):
        data = GameData(ROOTLESS)
        for kind in ("shred", "kswapd", "kworker", "crawler", "spinlock"):
            spec = data.monsters[kind]
            self.assertIn(spec["sprite"], data.sprites)
            self.assertTrue(spec["man"] and spec["death"])
            for snd in (spec.get("sounds") or {}).values():
                self.assertIn(snd, data.sounds, "%s: %s" % (kind, snd))
        self.assertIn("recruit", data.sprites)
        self.assertNotIn("marine", data.sprites)
        for kind in ("shred", "kswapd", "kworker", "crawler", "spinlock"):   # drawn small, like the others
            self.assertLessEqual(len(data.sprites[kind]["pixels"]), 21)
        self.assertEqual(validate(data), [])


class AnimationTests(unittest.TestCase):
    def test_walk_frames_from_a_standing_sprite(self):
        from engine.sprite import walk_frames
        zombie = GameData(ROOTLESS).sprites["zombie"]["pixels"]
        a, b = walk_frames(zombie)
        self.assertEqual((len(a), len(a[0])), (len(zombie), len(zombie[0])))
        self.assertEqual(a[-1], "........kkk.")                # the left foot is up...
        self.assertEqual(b[-1], "..kkk.......")                # ...then the right
        self.assertEqual(a[:10], zombie[:10])                  # the body stays as it was
        self.assertEqual(walk_frames(GameData(ROOTLESS).sprites["barrel"]["pixels"]), [])   # no feet, no walk
        self.assertEqual(walk_frames(["..xx..", ".xxxx.", "xxxxxx", ".xxxx.", "..xx..", "..xx.."]), [])

    def test_a_level_loads_steps_attacks_and_muzzles(self):
        lv = Level(GameData(ROOTLESS), "e1m9", seed=1)
        shred = lv.sprites["shred"]
        self.assertEqual(len(shred.walk), 2)
        self.assertIsNotNone(shred.attack)
        self.assertTrue(shred.walk[0].lods)                    # far versions of the steps too
        self.assertAlmostEqual(shred.muzzle[0], 15.5 / 16)
        self.assertEqual(lv.sprites["barrel"].walk, [])
        self.assertIsNone(lv.sprites["crawler"].attack)
        lv = room_with(["#########", "#@.....r#", "#########"], {"r": "crawler"})
        r = lv.monsters[0]
        r.awake = True
        lv.end_beat()
        self.assertEqual((r.x, r.stride), (5, 2))              # two steps a beat, counted: which foot to show

    def test_the_picture_shows_steps_and_aim(self):
        lv = room_with(["#######",
                        "#.....#",
                        "#..@..#",
                        "#..f..#",
                        "#######"], {"f": "shred"})
        lv.player.facing = 2
        f = next(m for m in lv.monsters if m.kind == "shred")
        f.seen = True
        view = View(60, 17, "pixel")
        still = view.render(lv, FX(), 0)
        step = view.render(lv, FX(pos={f.id: (f.x, f.y)}), 0)
        self.assertNotEqual(still, step)
        f.intent = "windup"
        aim = view.render(lv, FX(), 0)
        self.assertNotEqual(still, aim)


class MeleeWeaponTests(unittest.TestCase):
    def armed(self, rows, legend=None, weapons=("1", "2", "shovel", "chainsaw")):
        lv = room_with(rows, legend)
        lv.player.weapons = list(weapons)
        return lv

    def test_a_weapon_sprite_drawn_with_more_detail_is_as_big(self):
        """The shovel is drawn with finer pixels ("scale"): in hand it stands about as tall as the fist."""
        from engine.firstperson import FX, View
        lv = self.armed(["#####", "#.@.#", "#####"])
        self.assertAlmostEqual(lv.sprites["w_shovel"].scale, 0.62)
        self.assertEqual(lv.sprites["w_fist"].scale, 1.0)
        for name in ("w_gauntlet", "w_knuckles", "w_etool"):       # in the game, kept for later levels
            self.assertIn(name, lv.data.sprites)

        def height(weapon):
            lv.player.weapon = weapon
            v = View(60, 20, "pixel")
            bare = View(60, 20, "pixel")
            lv.player.weapon, keep = "none", weapon
            empty = bare.render(lv, FX(), 0)
            lv.player.weapon = keep
            full = v.render(lv, FX(), 0)
            rows = [i for i, (a, b) in enumerate(zip(full, empty)) if a != b]
            return (max(rows) - min(rows) + 1) if rows else 0
        fist, shovel = height("1"), height("shovel")
        self.assertGreater(shovel, 0)
        self.assertLessEqual(abs(shovel - fist), fist)                 # not twice as tall

    def test_key_1_goes_round_the_melee_weapons(self):
        lv = self.armed(["#####", "#@..#", "#####"])
        said = []
        for _ in range(4):
            lv.run_line("1")
            said.append(lv.player.weapon)
        self.assertEqual(said, ["chainsaw", "shovel", "1", "chainsaw"])
        lv.run_line("2")
        lv.run_line("shovel")                                 # by name, typed
        self.assertEqual(lv.player.weapon, "shovel")
        self.assertEqual(lv.slot_of("shovel"), "1")
        self.assertEqual(lv.beat, 0)                           # choosing takes no time

    def test_the_shovel_shoves(self):
        lv = self.armed(["#######", "#@z...#", "#######"])
        lv.weapons["shovel"] = dict(lv.weapons["shovel"], accuracy=1.0)
        z = next(m for m in lv.monsters if m.kind == "zombie")
        z.hp, z.awake = 200, True
        lv.player.facing, lv.player.weapon = 1, "shovel"
        lv.run_line("f")
        self.assertLess(z.hp, 200)
        self.assertIn("CLANG", told(lv))
        self.assertIn("thrown back", told(lv))

    def test_the_chainsaw_staggers(self):
        lv = self.armed(["######", "#@z..#", "######"])
        z = next(m for m in lv.monsters if m.kind == "zombie")
        z.hp, z.awake = 200, True
        lv.player.facing, lv.player.weapon = 1, "chainsaw"
        hp = lv.player.hp
        for _ in range(4):
            lv.run_line("f")
        self.assertEqual(lv.player.hp, hp)                     # it never got its aim back
        self.assertLess(z.hp, 200 - 4 * 9 + 1)                 # every bite lands
        self.assertEqual((z.x, z.y), (2, 1))                   # and it stayed put

    def test_out_of_ammo_goes_to_the_best_melee_weapon(self):
        lv = self.armed(["#####", "#@..#", "#####"], weapons=("1", "2", "shovel"))
        lv.player.weapon, lv.player.ammo["bullets"] = "2", 1
        lv.run_line("f")
        self.assertEqual(lv.player.weapon, "shovel")

    def test_picking_up_the_shovel_in_e1m1(self):
        lv = level()
        put(lv, 14, 28, 3)
        lv.run_line("k")
        self.assertEqual(((lv.player.x, lv.player.y), lv.player.weapon), ((13, 28), "shovel"))
        self.assertIn("shovel", lv.player.weapons)
        rows = Level(GameData(ROOTLESS), "e1m9").spec["map"]
        self.assertEqual(rows[1][4], "n")                      # the chainsaw: E1M9's closet

    def test_problems_with_keys_and_frames(self):
        data = with_level({"map": ["#####", "#@.E#", "#####"]},
                          weapons={"axe": {"name": "axe", "kind": "melee"}, "saw": {"name": "saw", "key": "1"}})
        data.sprites = dict(data.sprites, odd={"pixels": ["aa", "aa"], "palette": {"a": "#fff"}, "walk": [["a"]]})
        said = " | ".join(validate(data))
        self.assertIn("weapon 'axe': key should be one of 1-9", said)
        self.assertNotIn("weapon 'saw'", said)
        self.assertIn("sprite 'odd': its walk and attack frames should be 2 x 2", said)


def armed(lv, weapon, **ammo):
    lv.player.weapons = sorted(set(lv.player.weapons) | {weapon})
    lv.player.weapon = weapon
    lv.player.ammo.update(ammo)
    return lv


class ExplosiveTests(unittest.TestCase):
    def test_a_rocket_bursts_on_what_it_hits(self):
        lv = armed(room_with(["#########",
                              "#...b...#",
                              "#...z...#",
                              "#.......#",
                              "#.......#",
                              "#...@...#",
                              "#########"]), "5", rockets=3)
        lv.player.facing = 0
        z, b = lv.monster_at(4, 2), lv.monster_at(4, 1)
        lv.run_line("f z1")
        self.assertTrue(z.dead and b.dead)                     # hit, and the barrel behind it went up too
        self.assertEqual(lv.player.ammo["rockets"], 2)
        self.assertTrue(lv.cell(4, 2).scorched)                # a black mark where it burst
        self.assertEqual(lv.player.hp, 100)                    # far enough away

    def test_a_rocket_at_arms_length_hurts(self):
        lv = armed(room_with(["#####",
                              "#...#",
                              "#.@.#",
                              "#####"]), "5", rockets=3)
        lv.player.facing = 2
        lv.run_line("f")
        self.assertIn("arm's length", told(lv))
        self.assertLess(lv.player.hp, 100)

    def test_out_of_bullets_it_never_takes_up_explosives_by_itself(self):
        lv = armed(room_with(["#####",
                              "#.@.#",
                              "#####"]), "2", bullets=1, rockets=5, grenades=5)
        lv.player.weapons = ["1", "2", "5", "6"]
        lv.run_line("f")
        self.assertEqual(lv.player.weapon, "1")

    def test_a_grenade_bounces_slides_and_goes_off_a_beat_later(self):
        lv = armed(room_with(["#######",
                              "#.....#",
                              "#.....#",
                              "#..@..#",
                              "#######"]), "6", grenades=3)
        lv.player.facing = 0
        lv.run_line("f")                                       # three cells: the wall is two away
        self.assertIn("bounces off the wall", told(lv))
        self.assertEqual([(g.x, g.y, g.fuse) for g in lv.grenades], [(3, 1, 1)])
        lv.run_line("w")                                       # two cells off: out of its reach
        self.assertEqual(lv.grenades, [])
        self.assertIn("The grenade", told(lv))
        self.assertTrue(lv.cell(3, 1).scorched)
        lv = armed(room_with(["#######",
                              "#.....#",
                              "#..;..#",
                              "#.....#",
                              "#..@..#",
                              "#######"]), "6", grenades=3)
        lv.weapons["6"] = dict(lv.weapons["6"], range=2)
        lv.player.facing = 0
        lv.run_line("f")
        self.assertIn("skids on", told(lv))
        self.assertEqual((lv.grenades[0].x, lv.grenades[0].y), (3, 1))

    def test_a_grenade_rides_a_belt_and_sets_off_its_neighbours(self):
        lv = room_with(["#########",
                        "#>>>>...#",
                        "#.......#",
                        "#...@...#",
                        "#########"], {">": {"conveyor": "e"}})
        from engine.level import Grenade
        lv.grenades = [Grenade(1, 1, 3, 50), Grenade(6, 2, 9, 50)]
        lv.run_line("w")
        self.assertEqual((lv.grenades[0].x, lv.grenades[0].y), (2, 1))
        lv.grenades[0].fuse = 1
        lv.grenades[0].x = 5
        lv.run_line("w")                                       # it goes off next to the other: both go
        self.assertEqual(lv.grenades, [])

    def test_shots_leave_holes_in_the_wall(self):
        from engine.level import HOLES
        lv = armed(room_with(["#######",
                              "#.....#",
                              "#.....#",
                              "#..@..#",
                              "#######"]), "3", shells=40)
        lv.player.facing = 0
        plain = View(80, 17, "pixel").render(lv, FX(), 0)
        lv.run_line("f")
        self.assertTrue(lv.holes and all((x, y, n) == (3, 0, 2) for x, y, n, _a, _d in lv.holes))
        self.assertNotEqual(View(80, 17, "pixel").render(lv, FX(), 0), plain)   # they show
        for _ in range(30):
            lv.run_line("f")
        self.assertEqual(len(lv.holes), HOLES)                 # the oldest go
        lv = armed(room_with(["#########",
                              "#.......#",
                              "#...z...#",
                              "#.......#",
                              "#.......#",
                              "#.......#",
                              "#.......#",
                              "#...@...#",
                              "#########"], seed=4), "2", bullets=50)
        lv.player.facing = 0
        for _ in range(8):
            lv.run_line("f z1")
            if lv.holes:
                break
        self.assertTrue(lv.holes)                              # a miss went on into the wall behind
        self.assertEqual(lv.holes[0][1], 0)


class LoaderTests(unittest.TestCase):
    ROOM = ["###########",
            "#.........#",
            "#~~~~~~~~~#",
            "#....H....#",
            "#....V....#",
            "#....@....#",
            "#####+#####",
            "#.........#",
            "###########"]

    def loader(self, rows=None, legend=None):
        lv = room_with(rows or self.ROOM, dict({"V": {"monster": "loader"}, "H": {"crate": "heavy"}}, **(legend or {})))
        lv.player.facing = 0
        return lv

    def test_climb_in_shove_a_container_wade_and_climb_down(self):
        lv = self.loader()
        v = lv.monster_at(5, 4)
        put(lv, 5, 5, 0)
        lv.run_line("k")
        self.assertIs(lv.player.vehicle, v)
        self.assertNotIn(v, lv.monsters)
        lv.run_line("2")
        self.assertIn("levers", told(lv))                      # no guns from the cage
        lv.run_line("k")                                       # the container: shoved into the acid, a step
        self.assertTrue(lv.cell(5, 2).sunk)
        lv.run_line("h; k")                                    # into the acid beside it: steel feet
        self.assertEqual(((lv.player.x, lv.player.y), lv.player.hp), ((4, 2), 100))
        lv.run_line("j; j; j; l")
        self.assertEqual((lv.player.x, lv.player.y), (5, 5))
        lv.player.facing = 2
        lv.run_line("k")                                       # the door: it will not fit
        self.assertIn("will not fit", told(lv))
        lv.run_line("use")                                     # Enter climbs down
        self.assertIsNone(lv.player.vehicle)
        self.assertIn(v, lv.monsters)
        self.assertEqual(((v.x, v.y), (lv.player.x, lv.player.y)), ((5, 5), (5, 4)))

    def test_on_foot_a_container_will_not_budge(self):
        lv = self.loader(legend={"V": {}})
        put(lv, 5, 4, 0)
        lv.run_line("k")
        self.assertTrue(lv.cell(5, 3).crate)
        self.assertIn("will not budge", told(lv))

    def test_it_treads_on_monsters_and_its_claws_throw_them(self):
        lv = self.loader(["#########",
                          "#.......#",
                          "#...d...#",
                          "#...z...#",
                          "#...V...#",
                          "#...@...#",
                          "#########"], {"d": "daemon"})
        z, d = lv.monster_at(4, 3), lv.monster_at(4, 2)
        lv.run_line("k")
        z.x, z.y, z.stun = 4, 3, 2
        lv.run_line("k")                                       # the zombie: crushed, and the loader on its cell
        self.assertTrue(z.dead)
        self.assertEqual((lv.player.x, lv.player.y), (4, 3))
        d.x, d.y, d.stun, d.hp = 4, 2, 3, 200                  # right ahead, reeling, tough
        lv.run_line("f")
        self.assertEqual((d.hp < 200, (d.x, d.y)), (True, (4, 1)))   # clawed, and flung back

    def test_it_takes_the_hits_and_blows_up_when_it_gives_out(self):
        lv = self.loader()
        put(lv, 5, 5, 0)
        lv.run_line("k")
        v = lv.player.vehicle
        lv.hurt(30, "A test hit.")
        self.assertEqual((lv.player.hp, v.hp), (100, 120))
        lv.hurt(200, "A big one.")
        self.assertIsNone(lv.player.vehicle)
        self.assertTrue(v.dead)
        self.assertIn("goes up", told(lv))
        self.assertLess(lv.player.hp, 100)                     # thrown clear - but not far

    def test_riding_draws_the_cage_and_the_claws(self):
        lv = self.loader()
        put(lv, 5, 5, 0)
        on_foot = View(80, 17, "pixel").render(lv, FX(), 0)
        lv.run_line("k")
        riding = View(80, 17, "pixel").render(lv, FX(), 0)
        yellow = (214, 168, 48)
        self.assertTrue(any(yellow in c for row in riding for c in row))
        self.assertFalse(any(yellow in c for row in on_foot for c in row))

    def test_the_bot_finishes_e1m2_with_the_loader(self):
        from engine import levelbot
        for seed in (0, 1, 2):
            outcome, lv = levelbot.play(GameData(ROOTLESS), "e1m2", seed)
            self.assertEqual(outcome, "exit", "seed %d" % seed)
            self.assertIn("w", lv.player.keys)


class SecretLevelTests(unittest.TestCase):
    def test_the_secret_exit_switch(self):
        lv = level()
        self.assertEqual(lv.cell(25, 20).exit_kind, "secret")
        put(lv, 24, 20, 1)
        lv.run_line("use")
        self.assertEqual(lv.exit_kind, "secret")

    def test_the_secret_exit_leads_to_e1m9(self):
        from unittest import mock
        from engine import level as level_mod
        from engine.audio import Silent
        from engine.game import Game
        term = Term(out=io.StringIO(), inp=lambda p: "", width=80, height=24, color=0, unicode=True, animate=False, env={})
        g = Game(ROOTLESS, term=term, audio=Silent())
        played = []

        def run(lv, console):                                 # each level is left at once by its own exit
            played.append(lv.id)
            lv.exit_kind = "secret" if len(played) == 1 else "exit"
            return "exit"
        with mock.patch.object(level_mod.Level, "run", run):
            level_mod.play_scene(g, g.world.scenes["boot_sector"])
        self.assertEqual(played, ["e1m1", "e1m9", "e1m2", "e1m3", "e1m4", "e1m5", "e1m6", "e1m7", "e1m8"])
        self.assertEqual(g.world.scene_id, "aspiration_central")
        self.assertEqual(g.over, "win")
        out = term.out.getvalue().lower()
        self.assertIn("swap partition", out)
        self.assertIn("loading dock", out)

    def test_the_normal_exit_leads_to_e1m2(self):
        from unittest import mock
        from engine import level as level_mod
        from engine.audio import Silent
        from engine.game import Game
        term = Term(out=io.StringIO(), inp=lambda p: "", width=80, height=24, color=0, unicode=True, animate=False, env={})
        g = Game(ROOTLESS, term=term, audio=Silent())
        played = []

        def run(lv, console):
            played.append(lv.id)
            lv.exit_kind = "exit"
            return "exit"
        with mock.patch.object(level_mod.Level, "run", run):
            level_mod.play_scene(g, g.world.scenes["boot_sector"])
        self.assertEqual(played, ["e1m1", "e1m2", "e1m3", "e1m4", "e1m5", "e1m6", "e1m7", "e1m8"])
        self.assertIn("pod six", term.out.getvalue().lower())
        self.assertIn("user space", term.out.getvalue().lower())

    def test_the_bot_finishes_e1m9(self):
        import levelbot
        for seed in (1, 6, 8):                       # the secret level is hard: the bot finishes it about three times in five
            outcome, lv = levelbot.play("rootless", "e1m9", seed)
            self.assertEqual(outcome, "exit", "seed %d" % seed)

    def test_the_coolant_closet(self):
        lv = Level(GameData(ROOTLESS), "e1m9", seed=1)
        lv.console = Quiet()
        for m in lv.monsters:
            if not m.barrel:
                m.dead = True
        put(lv, 2, 11, 0)
        lv.run_line("k")                                       # up the west wall: stops on the dry patch
        put(lv, lv.player.x, lv.player.y, 1)
        lv.run_line("k")                                       # east: slides up to the crate
        lv.run_line("k")                                       # and pushes it across, on to the plate
        self.assertTrue(lv.cell(10, 6).crate and lv.cell(10, 6).down and lv.cell(3, 2).open == 1.0)
        put(lv, 3, 11, 0)
        lv.run_line("k")
        lv.run_line("k")
        self.assertEqual(((lv.player.x, lv.player.y), lv.stats["secrets"]), ((3, 1), 1))

    def test_problems_with_belts_and_exits(self):
        data = with_level({"map": ["#####", "#@>E#", "#####"], "legend": {">": {"conveyor": "up"}, "E": {"exit": "maybe"}}})
        said = " | ".join(validate(data))
        self.assertIn("should be n, e, s or w", said)
        self.assertIn("should be true or \"secret\"", said)


class EndScreenTests(unittest.TestCase):
    def test_totals_and_the_screen(self):
        from engine import ending
        from engine.frame import Painter
        from engine.term import strip_ansi, visible_len
        t = ending.totals({"a": {"kills": 3, "kills_total": 4, "beats": 50, "par": 60, "fired": 10, "hits": 5},
                           "b": {"kills": 2, "kills_total": 2, "secrets": 1, "secrets_total": 3, "beats": 20, "par": 30}})
        self.assertEqual((t["kills"], t["kills_total"], t["secrets_total"], t["beats"], t["par"]), (5, 6, 3, 70, 90))

        class Game:                                          # what the screen asks of a game
            data = GameData(ROOTLESS)
            cfg = data.config
            term = None
            make_banner = staticmethod(lambda *a, **k: None)
        spec = Game.cfg["end_screen"]
        rows = ending.rows_of(Game, spec, "The end text.", t, 1.0, 0.0, 80, 30, Painter(3))
        text = "\n".join(strip_ansi(r) for r in rows)
        for words in ("RØØTLESS", "ROASTED IN THE SHELL", "5 / 6", "par 90", "The end text.", "Next: User Space"):
            self.assertIn(words, text)
        self.assertNotIn("items", text)                        # nothing to count: no line
        self.assertTrue(all(visible_len(r) <= 80 for r in rows))
        half = "\n".join(strip_ansi(r) for r in ending.rows_of(Game, spec, "The end text.", t, 0.5, 0.0, 80, 30, Painter(3)))
        self.assertIn("2 / 6", half)                           # counting up
        self.assertNotIn("The end text.", half)
        self.assertIn("next run in", strip_ansi(ending.tick_line(spec, 1.2, Painter(3), 80)))
        self.assertLessEqual(len(ending.picture(Game.data, "cron", 10)), 10)    # shrunk to fit
        self.assertEqual(len(ending.picture(Game.data, "cron", 16)), 15)         # at its own size
        self.assertEqual(Game.cfg["end_screen"]["picture"], ["helmet_recruit", "helmet_hazmat"])   # the hero's helmet
        self.assertEqual(len(ending.picture(Game.data, "helmet_recruit", 14)), 13)
        spec = dict(Game.cfg["end_screen"])
        first, later = ending.pictures(Game.data, spec, 20, 0.0), ending.pictures(Game.data, spec, 20, 4.5)
        self.assertNotEqual(first, later)                                          # in turn, every 4 seconds
        self.assertEqual((len(first), len(first[0])), (len(later), len(later[0]))) # on the same block: the text stays
        both = ending.pictures(Game.data, dict(spec, picture_every=0), 20)
        self.assertEqual(len(both[0]), 30 + 2 + 28)                                # side by side
        big = ending.pictures(Game.data, dict(spec, picture="helmet_recruit", picture_lines=28), 40)
        self.assertEqual(len(big), 26)                                             # twice as big, when it fits

    def test_piped_the_usual_ending(self):
        from engine.game import Game
        term = Term(out=io.StringIO(), width=80, color=0, unicode=True, animate=False, env={})
        g = Game(ROOTLESS, term=term, seed=1)
        g.audio.enabled = False
        g.end_game("win", "outro_demo")
        self.assertIn("THE END", term.out.getvalue())


class EditorTests(unittest.TestCase):
    def test_level_pictures_and_checks(self):
        from engine.editor import service
        info = service.handle(ROOTLESS, "/api/levels")
        self.assertTrue(info["tiles"]["grate"]["own"] and not info["tiles"]["steel"]["own"])
        self.assertEqual(info["things"]["zombie"]["kind"], "monster")
        self.assertEqual(info["legend"]["~"], {"toxic": True})
        v = service.handle(ROOTLESS, "/api/view", {"level": "e1m1", "x": 15, "y": 22, "facing": "w"})
        self.assertEqual((v["cols"], v["lines"], len(v["rows"]), v["facing"], v["inside"]), (80, 17, 17, "w", False))
        self.assertEqual(sum(len(run[0]) for run in v["rows"][0]), 80)
        self.assertTrue(service.handle(ROOTLESS, "/api/view", {"level": "e1m1", "x": 0, "y": 0})["inside"])
        at = {"level": "e1m1", "x": 15, "y": 22, "facing": "w"}
        mesh = service.handle(ROOTLESS, "/api/view", dict(at, render="mesh"))      # the rooms in the mesh view
        self.assertNotEqual(mesh["rows"], v["rows"])
        self.assertEqual(service.handle(ROOTLESS, "/api/view", dict(at, render="classic"))["rows"], v["rows"])
        self.assertEqual(service.handle(ROOTLESS, "/api/view", dict(at, render="odd"))["rows"], v["rows"])
        sim = service.handle(ROOTLESS, "/api/view", {"level": "sim12"})                # a level drawn as a mesh
        self.assertEqual(sim["rows"], service.handle(ROOTLESS, "/api/view", {"level": "sim12", "render": "mesh"})["rows"])
        t = service.handle(ROOTLESS, "/api/tileview", {"name": "grate", "where": "floor"})
        self.assertEqual(len(t["rows"]), 17)
        w = service.handle(ROOTLESS, "/api/weaponview", {"weapon": "1"})
        self.assertEqual((len(w["frames"]), w["drawn"]), (4, True))
        self.assertEqual(len(service.handle(ROOTLESS, "/api/tile", {"name": "steel"})["pixels"]), 32)
        c = service.handle(ROOTLESS, "/api/levelcheck", {"level": "e1m1", "runs": 1})
        self.assertEqual((c["runs"], c["secrets"], c["games"][0]["outcome"]), (1, 5, "exit"))
        from engine import schema
        self.assertEqual(schema.BY_FILE["levels"]["editor"], "level")
        self.assertIn("tiles", schema.BY_FILE)
        self.assertIn("weapons", schema.BY_FILE)


    def test_monster_far_versions_and_distances(self):
        from engine.editor import service
        made = service.handle(ROOTLESS, "/api/monster", {"seed": "x", "body": "floater", "size": 20})
        self.assertTrue(made["pixels"] and made["lod"])
        self.assertIn("crawler", made["bodies"])
        far = service.handle(ROOTLESS, "/api/far", {"pixels": made["pixels"], "keep": made["keep"]})
        self.assertEqual(far["lod"], made["lod"])
        seen = service.handle(ROOTLESS, "/api/distances", {"sprite": made})["distances"]
        self.assertEqual([d["cells"] for d in seen], [1, 2, 3, 4, 5, 6])
        heights = [len(d["pixels"]) for d in seen]
        self.assertEqual(heights, sorted(heights, reverse=True))
        self.assertTrue(any(d["drawing"] for d in seen))         # far away, a far version is used

    def test_levels_and_monsters_are_kinds(self):
        from engine import schema
        self.assertIn("levels", schema.BY_FILE)
        self.assertIn("monsters", schema.BY_FILE)


class ChecksAndGameTests(unittest.TestCase):
    def test_validate_finds_mistakes(self):
        data = GameData(ROOTLESS)
        data.levels = copy.deepcopy(data.levels)
        data.levels["e1m1"]["legend"]["z"] = {"monster": "nobody"}
        data.levels["e1m1"]["map"][1] = data.levels["e1m1"]["map"][1].replace(".", "?", 1)
        problems = " ".join(validate(data))
        self.assertIn("unknown monster 'nobody'", problems)
        self.assertIn("does not explain", problems)

    def test_played_through_clio_in_text(self):
        from engine.audio import Silent
        from engine.game import Game
        answers = iter(["", "k", "map", "ps", "man zombie", "turn right", "q"])
        term = Term(out=io.StringIO(), inp=lambda p: next(answers, None), width=80, height=24, color=0,
                    unicode=True, animate=False, env={})
        g = Game(ROOTLESS, term=term, audio=Silent())
        g.run()
        out = term.out.getvalue()
        self.assertIn("BOOT SECTOR", out)
        self.assertIn("ZOMBIE_PROCESS(6)", out)
        self.assertIn("simulator pod", out)                     # the frame: a recruit's first battle simulation
        self.assertIn("facing east", out)

    def test_played_with_keys_in_a_redrawn_screen(self):
        from engine.level import KEYMAP, FrameConsole
        term = Term(out=io.StringIO(), width=80, height=24, color=3, unicode=True, animate=False, env={})
        con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False)
        # Enter past the intro; a step, a look round, a shot, the map and back, the fist, a typed line
        con.screen.keys = keys_mod.ScriptedKeys(["enter", "up", "right", "left", "space", "tab", "esc", "1",
                                                 "f", "space", "z", "1", "enter"])
        lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
        start = (lv.player.x, lv.player.y)
        self.assertEqual(lv.run(con), "quit")                  # the keys ran out: Ctrl-D
        self.assertEqual(lv.beat, 3)                           # step, shot, punch; turning is free
        self.assertEqual((lv.player.x, lv.player.y), (start[0], start[1] - 1))
        self.assertEqual((lv.player.weapon, lv.player.ammo["bullets"]), ("1", 49))
        out = term.out.getvalue()
        self.assertTrue(out.startswith("\x1b[?1049h"))           # its own screen...
        self.assertIn("\x1b[?1049l", out[-100:])                # ...given back at the end
        self.assertNotIn("command not found", out)

    def test_played_with_taps_and_swipes(self):
        from engine.level import KEYMAP, FrameConsole
        term = Term(out=io.StringIO(), width=90, height=30, color=3, unicode=True, animate=False, env={})
        con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False, touch=True)
        con.screen.size = lambda: (90, 30)                     # the picture: rows 1-23, thirds at 30 and 60
        self.assertEqual([con.touch_key(t) for t in ("mouse:0:45:3", "mouse:0:5:3", "mouse:0:80:12", "mouse:0:45:12",
                                                      "mouse:0:45:20", "mouse:0:2:22", "mouse:0:88:22", "mouse:0:45:0",
                                                      "mouse:0:45:26", "mouseup:0:45:3", "mouse:2:45:3")],
                         ["up", "left", "right", "space", "enter", ",", ".", "]", "tab", None, None])
        clock = [100.0]
        con.screen.now = lambda: clock[0]
        self.assertEqual(con.touch_key("mouse:65:40:10"), "up")    # a finger moving up: forward
        self.assertIsNone(con.touch_key("mouse:65:40:10"))         # the same swipe's next wheel step
        clock[0] += 0.5
        self.assertEqual(con.touch_key("mouse:64:40:10"), "down")  # moving down: back

        con.screen.keys = con.keys = keys_mod.ScriptedKeys([
            "enter", "mouse:0:45:3", "mouseup:0:45:3", "mouse:0:80:12", "mouse:0:5:12", "mouse:0:45:12",
            "mouse:0:45:0", "mouse:0:45:26", "mouse:0:10:10"])     # the map, closed by a tap
        lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
        start = (lv.player.x, lv.player.y)
        self.assertEqual(lv.run(con), "quit")
        self.assertEqual((lv.player.x, lv.player.y), (start[0], start[1] - 1))   # a step; turning is free
        self.assertEqual(lv.player.ammo["bullets"], 49)                      # a shot
        self.assertEqual(lv.player.weapon, "1")                              # the next weapon after the pistol: round to the fist
        out = term.out.getvalue()
        self.assertIn("\x1b[?1000h\x1b[?1006h", out)
        self.assertIn("\x1b[?1000l", out[-200:])                             # the mouse given back
        self.assertNotIn("command not found", out)

    def test_touch_help_and_next(self):
        from engine.level import KEYMAP, TOUCH_HELP, FrameConsole
        term = Term(out=io.StringIO(), width=90, height=30, color=3, unicode=True, animate=False, env={})
        shown = []
        for touch in (False, True):
            con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False, touch=touch)
            con.page = lambda lv, lines, automap=False: shown.append(lines)
            lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
            lv.console = con
            lv.run_line("help")
        self.assertNotIn(TOUCH_HELP[1], shown[0])
        self.assertIn(TOUCH_HELP[1], shown[1])
        self.assertEqual(KEYMAP["]"], "next")

    def test_the_bot_finishes_the_level(self):
        import levelbot
        for seed in (0, 1, 2):
            outcome, lv = levelbot.play(seed=seed)
            self.assertEqual(outcome, "exit", "seed %d" % seed)
            self.assertTrue(lv.boss.gone)


if __name__ == "__main__":
    unittest.main()
