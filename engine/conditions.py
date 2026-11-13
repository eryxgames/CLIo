# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Conditions and effects: the small JSON "scripting language" of CLIo.

Wherever the data has an ``"if"`` it is a *condition*; wherever it has a
``"do"`` it is a list of *effects*.  Both are plain JSON so games stay data.

Conditions::

    "met_robot"                      flag is set          "!met_robot"   not set
    "has:keycard"   "visited:lab"    "defeated:droid"     "here:robot"
    {"flag": "x"}   {"has": "item"}  {"lacks": "item"}    {"equipped": "item"}
    {"stat": ["attack", ">=", 15]}   {"var": ["scrap", ">=", 3]}
    {"quest": ["power", "done"]}     {"item_state": ["locker", "open"]}
    {"in_scene": "bridge"}           {"chance": 0.25}     {"turns": [">=", 40]}
    {"all": [...]}  {"any": [...]}   {"not": ...}         (several keys = all)

Effects (a dict may carry several; they run in order)::

    {"say": "Text", "style": "story"}      {"set": "flag"}      {"clear": "flag"}
    {"give": "item"}  {"take": "item"}     {"add_item": ["item", "scene"]}
    {"stat": {"health": -10}}  {"heal": 20}  {"gold": 5}  {"xp": 10}
    {"goto": "scene"}  {"unlock": "scene"}  {"reveal": ["from", "to"]}
    {"spawn": ["char", "scene"]}  {"remove_char": "char"}  {"move_char": ["char", "scene"]}
    {"item_state": ["item", "state"]}  {"quest": ["id", "start"]}
    {"sfx": "name"}  {"music": "track"}  {"art": "name"}  {"fight": "char"}
    {"win": "text_key"}  {"lose": "text_key"}
    {"if": cond, "then": [...], "else": [...]}  {"random": [[...], [...]]}
"""
from __future__ import annotations

import operator

_OPS = {
    ">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt,
    "==": operator.eq, "=": operator.eq, "!=": operator.ne,
}


def _cmp(value, op, target):
    try:
        return _OPS.get(op, operator.ge)(value, target)
    except TypeError:
        return False


def _triple(arg, default_op=">="):
    """Accept [name, op, value], [name, value] or [op, value] shapes."""
    arg = list(arg)
    if len(arg) == 3:
        return arg[0], arg[1], arg[2]
    if len(arg) == 2:
        return arg[0], default_op, arg[1]
    return arg[0], default_op, 1


def check(cond, g):
    """True if the condition holds. ``None`` / missing conditions are true."""
    if cond is None or cond is True or cond == "" or cond == {} or cond == []:
        return True
    if cond is False:
        return False
    w = g.world
    if isinstance(cond, str):
        neg = cond.startswith("!")
        text = cond[1:] if neg else cond
        if ":" in text:
            kind, _, arg = text.partition(":")
            result = _check_one(kind.strip(), arg.strip(), g)
        else:
            result = bool(w.flags.get(text))
        return (not result) if neg else result
    if isinstance(cond, (list, tuple)):
        return all(check(c, g) for c in cond)
    if isinstance(cond, dict):
        for key, arg in cond.items():
            if not _check_one(key, arg, g):
                return False
        return True
    return bool(cond)


def _check_one(key, arg, g):
    w = g.world
    if key == "flag":
        return all(bool(w.flags.get(f)) for f in _aslist(arg))
    if key == "not_flag":
        return not any(w.flags.get(f) for f in _aslist(arg))
    if key == "has":
        return all(w.has(i) for i in _aslist(arg))
    if key == "lacks":
        return not any(w.has(i) for i in _aslist(arg))
    if key == "equipped":
        return all(i in w.equipped for i in _aslist(arg))
    if key in ("in_scene", "in"):
        return w.scene_id in _aslist(arg)
    if key == "visited":
        return all(s in w.visited for s in _aslist(arg))
    if key == "defeated":
        return all(g.is_defeated(c) for c in _aslist(arg))
    if key == "alive":
        return not any(g.is_defeated(c) for c in _aslist(arg))
    if key == "here":
        return all(g.char_here(c) for c in _aslist(arg))
    if key == "item_here":
        sc = w.scene
        return all(i in sc.get("items", []) or i in sc.get("passive_items", []) for i in _aslist(arg))
    if key == "quest":
        if isinstance(arg, str):
            qid, _, want = arg.partition(":")
            want = want or "active"
        else:
            qid, want = arg[0], (arg[1] if len(arg) > 1 else "active")
        return g.quests.is_state(qid, want)
    if key == "stat":
        name, op, value = _triple(arg)
        return _cmp(w.stats.get(name, 0), op, value)
    if key == "var":
        name, op, value = _triple(arg)
        return _cmp(w.vars.get(name, 0), op, value)
    if key == "gold":
        op, value = (arg if isinstance(arg, (list, tuple)) else (">=", arg))
        return _cmp(w.player.get("gold", 0), op, value)
    if key == "level":
        op, value = (arg if isinstance(arg, (list, tuple)) else (">=", arg))
        return _cmp(w.player.get("level", 1), op, value)
    if key == "turns":
        op, value = (arg if isinstance(arg, (list, tuple)) else (">=", arg))
        return _cmp(w.turn, op, value)
    if key in ("item_state", "state"):
        if isinstance(arg, str):
            iid, _, st = arg.partition(":")
        else:
            iid, st = arg[0], arg[1]
        return w.items.get(iid, {}).get("current_state") == st
    if key == "class":
        return w.player.get("class") in _aslist(arg)
    if key == "chance":
        return w.rng.random() < float(arg)
    if key == "all":
        return all(check(c, g) for c in arg)
    if key == "any":
        return any(check(c, g) for c in arg)
    if key == "not":
        return not check(arg, g)
    if key == "item_in":
        iid, sid = arg[0], arg[1]
        sc = w.scenes.get(sid, {})
        return iid in sc.get("items", []) or iid in sc.get("passive_items", [])
    if key == "char_in":
        return w.char_scene(arg[0]) == arg[1]
    # unknown keys are treated as flags so typos fail closed
    return bool(w.flags.get(key)) if arg in (True, None) else False


def _aslist(v):
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


# --------------------------------------------------------------------------- #
# Effects
# --------------------------------------------------------------------------- #

def run(effects, g, ctx=None):
    """Run an effect, or a list of them. Returns False if the game ended."""
    if not effects:
        return True
    if isinstance(effects, str):
        g.say(effects, "story")
        return True
    if isinstance(effects, dict):
        effects = [effects]
    for eff in effects:
        if g.over:
            return False
        if isinstance(eff, str):
            g.say(eff, "story")
            continue
        if isinstance(eff, (list, tuple)):
            run(list(eff), g, ctx)
            continue
        if not isinstance(eff, dict):
            continue
        if "if" in eff and ("then" in eff or "else" in eff):
            run(eff.get("then") if check(eff["if"], g) else eff.get("else"), g, ctx)
            continue
        if "if" in eff and not check(eff["if"], g):
            continue
        for key, arg in eff.items():
            fn = _EFFECTS.get(key)
            if fn:
                fn(g, arg, eff, ctx)
            if g.over:
                return False
    return True


def _e_say(g, arg, eff, ctx):
    g.say(arg, eff.get("style", "story"), effect=eff.get("effect"), title=eff.get("title"))


def _e_set(g, arg, eff, ctx):
    if isinstance(arg, dict):
        g.world.flags.update(arg)
    else:
        for f in _aslist(arg):
            g.world.flags[f] = True


def _e_clear(g, arg, eff, ctx):
    for f in _aslist(arg):
        g.world.flags.pop(f, None)


def _e_var(g, arg, eff, ctx):
    name, op, value = _triple(arg, "=")
    cur = g.world.vars.get(name, 0)
    if op in ("+=", "+"):
        cur += value
    elif op in ("-=", "-"):
        cur -= value
    else:
        cur = value
    g.world.vars[name] = cur


def _e_give(g, arg, eff, ctx):
    for i in _aslist(arg):
        g.give_item(i, quiet=bool(eff.get("quiet")))


def _e_take(g, arg, eff, ctx):
    for i in _aslist(arg):
        g.remove_item(i, quiet=eff.get("quiet", True))


def _e_add_item(g, arg, eff, ctx):
    arg = _aslist(arg)
    sid = arg[1] if len(arg) > 1 else g.world.scene_id
    if sid in g.world.scenes and arg[0] in g.world.items:
        key = "passive_items" if eff.get("fixture") else "items"
        g.world.scenes[sid].setdefault(key, []).append(arg[0])


def _e_remove_item(g, arg, eff, ctx):
    arg = _aslist(arg)
    scenes = [arg[1]] if len(arg) > 1 else list(g.world.scenes)
    for sid in scenes:
        sc = g.world.scenes.get(sid, {})
        for key in ("items", "passive_items"):
            if arg[0] in sc.get(key, []):
                sc[key].remove(arg[0])
                return


def _e_item_state(g, arg, eff, ctx):
    iid, st = arg[0], arg[1]
    if iid in g.world.items:
        g.world.items[iid]["current_state"] = st


def _e_item_set(g, arg, eff, ctx):
    iid, key, value = arg[0], arg[1], arg[2]
    if iid in g.world.items:
        g.world.items[iid][key] = value


def _e_stat(g, arg, eff, ctx):
    if isinstance(arg, dict):
        for k, v in arg.items():
            g.change_stat(k, v, announce=not eff.get("quiet"))
    else:
        g.change_stat(arg[0], arg[1], announce=not eff.get("quiet"))


def _e_heal(g, arg, eff, ctx):
    st = g.world.stats
    amount = st["max_health"] if arg in ("full", True) else int(arg)
    g.change_stat("health", amount, announce=not eff.get("quiet"))


def _e_damage(g, arg, eff, ctx):
    g.change_stat("health", -abs(int(arg)), announce=not eff.get("quiet"))


def _e_gold(g, arg, eff, ctx):
    g.add_gold(int(arg))


def _e_xp(g, arg, eff, ctx):
    g.add_xp(int(arg))


def _e_goto(g, arg, eff, ctx):
    g.enter_scene(arg, quiet=bool(eff.get("quiet")))


def _exit_refs(g, arg):
    """Exits matching "to", or ["from", "to"]."""
    arg = _aslist(arg)
    if len(arg) == 1:
        src, dst = g.world.scene_id, arg[0]
    else:
        src, dst = arg[0], arg[1]
    out = []
    for ex in g.world.scenes.get(src, {}).get("exits", []):
        if ex.get("scene_id") == dst or ex.get("door_name", "").lower() == str(dst).lower() \
                or ex.get("id") == dst:
            out.append(ex)
    return out


def _e_unlock(g, arg, eff, ctx):
    for ex in _exit_refs(g, arg):
        ex["locked"] = False
        ex["blocked"] = False
        ex["hidden"] = False


def _e_lock(g, arg, eff, ctx):
    for ex in _exit_refs(g, arg):
        ex["locked"] = True


def _e_reveal(g, arg, eff, ctx):
    for ex in _exit_refs(g, arg):
        ex["hidden"] = False
    g.world.positions = None


def _e_hide(g, arg, eff, ctx):
    for ex in _exit_refs(g, arg):
        ex["hidden"] = True


def _e_block(g, arg, eff, ctx):
    for ex in _exit_refs(g, arg):
        ex["blocked"] = True


def _e_spawn(g, arg, eff, ctx):
    arg = _aslist(arg)
    sid = arg[1] if len(arg) > 1 else g.world.scene_id
    if eff.get("copy", False) or "#" in arg[0]:
        g.world.spawn(arg[0], sid)
    elif arg[0] in g.world.characters and sid in g.world.scenes:
        _e_remove_char(g, arg[0], eff, ctx)
        g.world.characters[arg[0]].pop("defeated", None)
        g.world.scenes[sid].setdefault("characters", []).append(arg[0])


def _e_remove_char(g, arg, eff, ctx):
    for cid in _aslist(arg):
        for sc in g.world.scenes.values():
            if cid in sc.get("characters", []):
                sc["characters"].remove(cid)


def _e_move_char(g, arg, eff, ctx):
    cid, sid = arg[0], arg[1]
    if cid in g.world.characters and sid in g.world.scenes:
        _e_remove_char(g, cid, eff, ctx)
        g.world.scenes[sid].setdefault("characters", []).append(cid)


def _e_char_set(g, arg, eff, ctx):
    cid, key, value = arg[0], arg[1], arg[2]
    if cid in g.world.characters:
        g.world.characters[cid][key] = value


def _e_quest(g, arg, eff, ctx):
    if isinstance(arg, str):
        qid, _, action = arg.partition(":")
        action = action or "start"
    else:
        qid, action = arg[0], (arg[1] if len(arg) > 1 else "start")
    if action == "start":
        g.quests.start(qid)
    elif action == "advance":
        g.quests.advance(qid)
    elif action in ("complete", "done", "finish"):
        g.quests.complete(qid)
    elif action == "fail":
        g.quests.fail(qid)


def _e_sfx(g, arg, eff, ctx):
    g.audio.sfx(arg)


def _e_music(g, arg, eff, ctx):
    g.play_music(arg)


def _e_art(g, arg, eff, ctx):
    g.show_art(arg)


def _e_pause(g, arg, eff, ctx):
    if arg is True:
        g.ui.pause()
    else:
        g.ui.term.sleep(float(arg))


def _e_fight(g, arg, eff, ctx):
    g.start_fight(arg, can_flee=eff.get("can_flee", True))


def _e_dialogue(g, arg, eff, ctx):
    g.talk_to(arg)


def _e_win(g, arg, eff, ctx):
    g.end_game("win", arg)


def _e_lose(g, arg, eff, ctx):
    g.end_game("lose", arg)


def _e_random(g, arg, eff, ctx):
    if arg:
        run(g.world.rng.choice(list(arg)), g, ctx)


def _e_do(g, arg, eff, ctx):
    run(arg, g, ctx)


def _e_learn(g, arg, eff, ctx):
    for a in _aslist(arg):
        if a not in g.world.player["abilities"]:
            g.world.player["abilities"].append(a)
            name = g.abilities.get(a, {}).get("name", a)
            g.say("You learn a new technique: {key}%s{/}." % name, "success")


def _e_end_dialogue(g, arg, eff, ctx):
    if ctx is not None:
        ctx["end"] = True


def _e_turns(g, arg, eff, ctx):
    g.world.turn += int(arg)


def _e_shop(g, arg, eff, ctx):
    g.open_shop(arg)


def _e_story(g, arg, eff, ctx):
    g.story_text(arg)


def _e_transition(g, arg, eff, ctx):
    g.ui.transition()


def _e_save(g, arg, eff, ctx):
    # {"save": true} writes the slot of the current game mode; a string names a slot
    slot = arg if isinstance(arg, str) and arg not in ("", "save") else None
    if g.save_slot(slot, quiet=True) and not eff.get("quiet"):
        g.say("(progress saved)", "hint")


def _e_deepen(g, arg, eff, ctx):
    """Endless dungeons: build the next floor below the deepest one."""
    if g.cfg.get("generator"):
        from . import maze
        maze.extend(g)


def _e_look(g, arg, eff, ctx):
    g.describe_scene(full=True)


_EFFECTS = {
    "say": _e_say, "narrate": _e_say, "set": _e_set, "clear": _e_clear, "var": _e_var,
    "give": _e_give, "take": _e_take, "add_item": _e_add_item, "remove_item": _e_remove_item,
    "item_state": _e_item_state, "item_set": _e_item_set, "stat": _e_stat, "heal": _e_heal,
    "damage": _e_damage, "gold": _e_gold, "xp": _e_xp, "goto": _e_goto, "unlock": _e_unlock,
    "lock": _e_lock, "reveal": _e_reveal, "hide": _e_hide, "block": _e_block, "spawn": _e_spawn,
    "remove_char": _e_remove_char, "move_char": _e_move_char, "char_set": _e_char_set,
    "quest": _e_quest, "sfx": _e_sfx, "music": _e_music, "art": _e_art, "pause": _e_pause,
    "fight": _e_fight, "dialogue": _e_dialogue, "win": _e_win, "lose": _e_lose,
    "random": _e_random, "do": _e_do, "learn": _e_learn, "end_dialogue": _e_end_dialogue,
    "turns": _e_turns, "shop": _e_shop, "story": _e_story, "transition": _e_transition,
    "look": _e_look, "save": _e_save, "deepen": _e_deepen,
}
