# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Making an enemy of a chosen strength, and finding out how a fight with it goes.

Strength is measured the way the dungeon generator measures it
(``maze.floor_power``): health times hitting power, ``max_health * (6 + attack)``.
A new enemy is an existing one (or a plain one) scaled to a target with the
generator's own rule (``maze.scaled``), so what is made here sits on the same
curve as what the game spawns by itself.

Whether that is *fair* is not calculated but tried: the real battle code is run
many times with a player who fights sensibly and without flair - guards against
a wound-up blow, heals when low, uses a skill when there is focus for it, and
otherwise strikes.  A person will do better or worse; the figures compare
enemies with each other more reliably than they predict any one fight.
"""
import copy
import io
import re

from .. import maze
from ..data import GameData
from . import EditorError, workdir

RANKS = {"minion": 0.6, "regular": 1.0, "elite": 2.2, "boss": 4.0}    # against the average monster of the floor
BLANK = {"name": "New enemy", "type": "hostile", "description": "",
         "stats": {"health": 20, "max_health": 20, "attack": 5, "defense": 0, "critical_hit_chance": 0.05},
         "moves": [{"type": "attack", "name": "a blow", "weight": 4},
                   {"type": "heavy", "name": "A heavy blow", "mult": 1.8, "weight": 1,
                    "tell": "It draws back for a heavy blow."}],
         "show_hostile": True}
MAX_ANSWERS = 600           # a fight that needs more prompts than this is called undecided


def power(stats):
    return float(stats.get("max_health", stats.get("health", 20))) * (6.0 + float(stats.get("attack", 5)))


class _Holder:
    """What the generator's functions want of a game: its data."""
    def __init__(self, data):
        self.data = data


def floors(data, deeper=3):
    """The strengths an enemy can be measured against: ``[{"n", "name", "power"}, ...]``.

    For a game with a dungeon, its floors and a few below the last (as the
    endless dungeon would make them); otherwise one entry, the average of the
    game's own enemies.
    """
    game = _Holder(data)
    written = (data.dungeon or {}).get("floors") or []
    out = []
    if written:
        for n in range(1, len(written) + 1 + (deeper if (data.dungeon or {}).get("endless") else 0)):
            fl, factor, _rank, _hazard = maze.floor_plan(game, n)
            out.append({"n": n, "name": fl.get("name", "Floor %d" % n), "power": round(maze.floor_power(game, fl) * factor * factor)})
        return out
    own = [power(ch["stats"]) for ch in data.characters.values()
           if isinstance(ch.get("stats"), dict) and ch.get("type") in ("hostile", "aggressive")]
    return [{"n": 0, "name": "this game's enemies", "power": round(sum(own) / len(own)) if own else 220}]


def scale(stats, factor):
    """Stats ``factor`` times tougher - the rule of ``maze.scaled``, usable downwards too."""
    hp = max(1, int(round(float(stats.get("max_health", stats.get("health", 20))) * factor)))
    out = dict(stats, health=hp, max_health=hp,
               attack=max(0, int(round((6 + float(stats.get("attack", 5))) * factor - 6))),
               defense=max(0, int(round(float(stats.get("defense", 0)) * (1 + (factor - 1) * 0.5)))))
    return out


def make_enemy(game_dir, like=None, floor=None, rank="regular", lean=0.0, name=None, pending=None):
    """A new enemy for the editor to show, try and add. Nothing is written.

    ``like``   the id of a character to start from (its moves, tags and looks are kept), or None for a plain one
    ``floor``  which floor's monsters to measure against (see ``floors``); None is the first
    ``rank``   minion, regular, elite or boss: how it compares with that floor's average
    ``lean``   -1 (tough: more health, softer hits) to 1 (sharp: less health, harder hits), at the same strength
    """
    if rank not in RANKS:
        raise EditorError("A rank is one of: %s." % ", ".join(RANKS))
    lean = max(-1.0, min(1.0, float(lean or 0.0)))
    with workdir(game_dir, pending) as work:
        data = GameData(work)
        scale_to = floors(data)
        chosen = next((f for f in scale_to if f["n"] == floor), scale_to[0])
        if like:
            if not isinstance(data.characters.get(like, {}).get("stats"), dict):
                raise EditorError("'%s' is not a character with stats to start from." % like)
            base = copy.deepcopy(data.characters[like])
            for key in ("unique", "dialogue_tree", "on_defeat", "solo"):
                base.pop(key, None)                         # what made the original one of a kind stays with it
        else:
            base = copy.deepcopy(BLANK)
        target = chosen["power"] * RANKS[rank]
        factor = (target / max(1.0, power(base["stats"]))) ** 0.5
        stats = scale(base["stats"], factor)
        tilt = 1.5 ** lean
        hp = max(1, int(round(stats["max_health"] / tilt)))
        stats.update(health=hp, max_health=hp, attack=max(0, int(round((6 + stats["attack"]) * tilt - 6))))
        base["stats"] = stats
        base["xp"] = max(1, int(round(base["xp"] * factor * factor))) if base.get("xp") else max(1, int(round(target / 25.0)))
        gold = base.get("gold")
        if isinstance(gold, (list, tuple)):
            base["gold"] = [int(round(g * factor)) for g in gold]
        elif gold:
            base["gold"] = int(round(gold * factor))
        else:
            base["gold"] = [int(round(target / 250.0)), max(1, int(round(target / 60.0)))]
        base["name"] = (name or "").strip() or ("%s (%s)" % (base["name"], rank) if like else "New enemy")
        slug = re.sub(r"[^a-z0-9]+", "_", base["name"].lower()).strip("_") or "enemy"
        new_id, n = slug, 2
        while new_id in data.characters:
            new_id, n = "%s_%d" % (slug, n), n + 1
        return {"id": new_id, "enemy": base, "power": round(power(stats)), "target": round(target),
                "floor": chosen, "floors": scale_to, "ranks": list(RANKS),
                "like": [{"id": cid, "name": ch.get("name", cid)} for cid, ch in data.characters.items()
                         if isinstance(ch.get("stats"), dict)]}


class _TooLong(Exception):
    pass


class _Player:
    """Answers the game's prompts: the plain, sensible fighter described at the top of this file."""

    def __init__(self):
        self.queue, self.game, self.aim, self.turns, self.answers = [], None, 1, 0, 0

    def answer(self, prompt):
        self.answers += 1
        if self.answers > MAX_ANSWERS:
            raise _TooLong()
        if self.queue:
            return self.queue.pop(0)
        if "Action>" in prompt:
            self.turns += 1
            return self.act()
        if "Target>" in prompt:
            return str(self.aim)
        return "1"

    def act(self):
        b = self.game.battle
        p, alive = b.player, b.alive
        e = min(alive, key=lambda f: (f.guarding, f.hp))    # the weakest enemy that is not braced
        self.aim = alive.index(e) + 1
        aim = " %d" % self.aim if len(alive) > 1 else ""
        intent = (e.intent or {}).get("type")
        if any((f.intent or {}).get("type") == "release" for f in alive):
            return "guard"
        if p.hp < p.max_hp * 0.38:
            items = b.usable_items()
            heals = [(float((self.game.world.items.get(i.split("#")[0], {}).get("effect") or {}).get("health", 0)), k)
                     for k, i in enumerate(items)]
            best = max(heals, default=(0, 0))
            if best[0] > 0:
                self.queue.append(str(best[1] + 1))
                return "item"
            for _aid, spec in b.available_abilities():
                if spec.get("kind") == "heal" and b.focus >= spec.get("cost", 1):
                    return spec["name"].lower()
        skills = b.available_abilities()
        if len(alive) > 1:                                  # against several, what reaches all of them goes first
            skills = sorted(skills, key=lambda s: 0 if s[1].get("area") or s[1].get("splash") else 1)
        for _aid, spec in skills:
            if spec.get("kind") in ("attack", "debuff") and b.focus >= spec.get("cost", 1):
                status = (spec.get("status") or {}).get("name")
                if spec.get("kind") == "debuff" and (e.has(status) or e.hp < 20 or status in (e.char.get("immune") or [])):
                    continue
                return spec["name"].lower() + aim
        if intent == "guard":
            return "focus"
        if intent == "heavy":
            return "heavy" + aim
        return "strike" + aim


def _one_fight(work, enemies, klass, level, seed):
    from ..audio import Audio
    from ..audio.backends import NullBackend
    from ..combat import Battle
    from ..game import Game
    from ..term import Term
    player = _Player()
    term = Term(out=io.StringIO(), inp=player.answer, width=80, height=40, color=0, unicode=False, animate=False, env={})
    game = Game(work, term=term, audio=Audio(backend=NullBackend(), enabled=False), seed=seed)
    player.game = game
    game.mode_request = next(iter(game.modes), None)
    try:
        game.choose_mode()
        cc = game.cfg.get("character_creation")
        if cc:
            classes = list(cc.get("classes") or {})
            if cc.get("ask_name", True):
                player.queue.append("Tester")
            if classes:
                player.queue.append(str(classes.index(klass) + 1 if klass in classes else 1))
            game.create_character(cc)
        who = game.world.player
        while who.get("level", 1) < level and game.cfg.get("rpg", True):
            before = who.get("level", 1)
            game.add_xp(game.xp_needed(before) - who.get("xp", 0))
            if who.get("level", 1) == before:
                break
        player.answers = 0
        battle = Battle(game, list(enemies), can_flee=False)
        game.battle = battle
        result = battle.run()
    except (_TooLong, EOFError):
        return "undecided", 0.0, player.turns
    left = max(0.0, battle.player.hp / float(max(1, battle.player.max_hp)))
    return result, left, player.turns


def odds(game_dir, enemies, pending=None, extra=None, level=1, fights=30, seed=1):
    """How fights against ``enemies`` (character ids, fought together) go, for each class the game has.

    ``extra`` is ``{id: character}`` to try without adding it to the game.
    Returns ``{"level", "fights", "rows": [{"class", "name", "wins", "health_left", "turns", "undecided"}]}``;
    ``wins`` and ``health_left`` (after a win) are shares from 0 to 1.
    """
    fights = max(1, min(200, int(fights)))
    level = max(1, min(60, int(level)))
    pending = dict(pending or {})
    if extra:
        with workdir(game_dir, pending) as work:
            import json
            import os
            from . import paths
            name = os.path.basename(paths(game_dir)["characters"])
            with open(os.path.join(work, name), encoding="utf-8") as f:
                everyone = json.load(f) if os.path.getsize(os.path.join(work, name)) else {}
        everyone.update(extra)
        pending["characters"] = everyone
    with workdir(game_dir, pending) as work:
        data = GameData(work)
        for cid in enemies:
            if not isinstance(data.characters.get(cid, {}).get("stats"), dict):
                raise EditorError("'%s' is not a character with stats, so it cannot be fought." % cid)
        classes = (data.config.get("character_creation") or {}).get("classes") or {}
        rows = []
        for klass in (list(classes) or [None]):
            won = undecided = 0
            left, turns = [], []
            for i in range(fights):
                result, health, took = _one_fight(work, enemies, klass, level, seed * 100003 + i)
                turns.append(took)
                if result == "win":
                    won += 1
                    left.append(health)
                elif result == "undecided":
                    undecided += 1
            rows.append({"class": klass, "name": (classes.get(klass) or {}).get("name", "The player") if klass else "The player",
                         "wins": round(won / float(fights), 3),
                         "health_left": round(sum(left) / len(left), 3) if left else None,
                         "turns": round(sum(turns) / float(len(turns)), 1), "undecided": undecided})
        return {"level": level, "fights": fights, "rows": rows}
