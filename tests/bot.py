"""A simple automatic player for the dungeon crawler.

It is not clever - it explores, loots, drinks potions and follows the basic
combat advice the game gives (guard a charged blow, hit during a wind-up).
The tests use it to prove that generated dungeons can be finished, and it is
handy for tuning difficulty:

    python tests/bot.py            # 30 runs per class, prints win rates
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import Session        # noqa: E402

HEALS = ("greater_draught", "healing_draught")


class DepthsBot(Session):
    def __init__(self, seed=1, klass=1, name="Bot", verbose=False):
        super().__init__("depths", commands=[name, str(klass)], seed=seed, width=70)
        self.steps = 0
        self.verbose = verbose

    # ---- answering prompts -------------------------------------------- #
    def _next(self, prompt):
        if self.queue:
            return self.queue.pop(0)
        if "Action>" in prompt:
            return self.battle_action()
        return "1"

    def heal_index(self, items):
        for want in HEALS:
            for i, iid in enumerate(items):
                if iid.split("#")[0] == want:
                    return i
        return None

    def battle_action(self):
        b = self.game.battle
        p, e = b.player, b.enemy
        t = (b.intent or {}).get("type")
        items = b.usable_items()
        if t == "release":
            return "guard"
        if p.hp < p.max_hp * 0.38:
            i = self.heal_index(items)
            if i is not None:
                self.queue.append(str(i + 1))
                return "item"
            for aid, spec in b.available_abilities():
                if spec.get("kind") == "heal" and b.focus >= spec.get("cost", 1):
                    return spec["name"].lower()
        if p.has("poison") or p.has("burn"):
            for i, iid in enumerate(items):
                if iid == "antidote" and p.hp < p.max_hp * 0.6:
                    self.queue.append(str(i + 1))
                    return "item"
        if e.hp > 40 and "firebomb" in items and not e.has("burn"):
            self.queue.append(str(items.index("firebomb") + 1))
            return "item"
        for aid, spec in b.available_abilities():
            if spec.get("kind") in ("attack", "debuff") and b.focus >= spec.get("cost", 1):
                if spec.get("kind") == "debuff" and (e.has(spec["status"]["name"]) or e.hp < 20):
                    continue
                if (spec.get("status") or {}).get("name") in (b.char.get("immune") or []) and spec.get("kind") == "debuff":
                    continue
                return spec["name"].lower()
        if t == "guard":
            return "focus"
        if t == "heavy":
            return "heavy"
        return "strike"

    # ---- exploring ----------------------------------------------------- #
    def cmd(self, line):
        self.steps += 1
        if self.verbose:
            print(">>", line)
        self.game.execute(line)

    def tidy(self):
        """Loot the room, gear up, patch up."""
        g, w = self.game, self.world
        sc = w.scene
        if sc.get("items"):
            self.cmd("take all")
        for fid in list(sc.get("passive_items", [])):
            it = w.items[fid]
            tpl = it.get("template")
            if tpl == "chest" and it.get("current_state") in ("closed", "locked"):
                if it["current_state"] == "closed" or any(w.items[i].get("lockpick") for i in w.inventory):
                    self.cmd("open chest")
                    if sc.get("items"):
                        self.cmd("take all")
            if tpl == "shrine" and it.get("current_state") == "lit" \
                    and w.stats["health"] < w.stats["max_health"] * 0.7:
                self.cmd("pray")
        # equip anything better
        for iid in list(dict.fromkeys(w.inventory)):
            it = w.items[iid]
            if not it.get("equippable"):
                continue
            score = sum(v * (60 if isinstance(v, float) else 1) for v in it.get("effect", {}).values())
            cur = [e for e in w.equipped if w.items[e].get("slot") == it.get("slot")]
            cur_score = sum(sum(v * (60 if isinstance(v, float) else 1) for v in w.items[e].get("effect", {}).values())
                            for e in cur)
            if score > cur_score:
                self.cmd("equip " + it["name"])
        for iid in list(w.inventory):
            if iid in ("whetstone", "iron_tonic", "heart_root") and iid in w.inventory:
                self.cmd("use " + w.items[iid]["name"])
        self.patch_up(0.55)
        # shopping: keep a few draughts in the pack
        if g._shopkeeper() and not self.game.over:
            while w.player["gold"] >= 15 and sum(1 for i in w.inventory if i in HEALS) < 4:
                self.queue.extend(["1", "1", "0"])     # Buy -> first item (healing draught) -> leave
                self.cmd("trade")

    def patch_up(self, threshold):
        w = self.world
        while w.stats["health"] < w.stats["max_health"] * threshold and not self.game.over:
            have = [h for h in HEALS if h in w.inventory]
            if not have:
                break
            self.cmd("use " + w.items[have[-1]]["name"])

    def guarded(self, ex):
        return bool(self.game.exit_guard(ex))

    def path_to(self, want):
        """First step (an exit) toward the nearest scene satisfying ``want``."""
        w = self.world
        start = w.scene_id
        seen = {start}
        queue = [(start, None)]
        while queue:
            sid, first = queue.pop(0)
            if sid != start and want(sid):
                return first
            for ex in w.scenes[sid].get("exits", []):
                to = ex.get("scene_id")
                if to in seen or to not in w.scenes:
                    continue
                if sid == start and self.guarded(ex):
                    continue
                if w.scenes[to].get("floor") != w.scenes[start].get("floor"):
                    continue
                seen.add(to)
                queue.append((to, first or ex))
        return None

    def play(self, max_steps=900):
        g, w = self.game, self.world
        g.begin_story()
        self.cmd("talk to maren")
        self.queue.extend(["3", "0"])
        self.cmd("talk to maren")
        self.cmd("down")
        while not g.over and self.steps < max_steps:
            self.tidy()
            if g.over:
                break
            sc = w.scene
            if "ember_crown" in sc.get("items", []):
                self.cmd("take crown")
                break
            ex = self.path_to(lambda sid: sid not in w.visited
                              and not (w.scenes[sid].get("kind") == "boss"))
            if ex is None:
                # floor explored: deal with the stair's keeper, then go down / face the boss
                hostile = [c for c in g.chars_here() if g.is_hostile(w.characters[c])]
                if hostile:
                    self.patch_up(0.8)
                    self.cmd("fight " + w.characters[hostile[0]]["name"])
                    continue
                down = [e for e in sc.get("exits", []) if e.get("dir") == "d"]
                if down:
                    self.cmd("down")
                    continue
                ex = self.path_to(lambda sid: w.scenes[sid].get("kind") in ("stairs", "boss")
                                  and not (sid in w.visited and w.scenes[sid].get("kind") == "boss"))
                if ex is None:
                    ex = self.path_to(lambda sid: any(e.get("dir") == "d" for e in w.scenes[sid].get("exits", [])))
                if ex is None:
                    break
                if w.scenes[ex["scene_id"]].get("kind") == "boss":
                    self.patch_up(0.9)
            self.cmd("go " + ex["dir"])
        return g.over


def trial(runs=30):
    for klass, label in ((1, "warrior"), (2, "rogue"), (3, "mystic")):
        wins, levels, turns, deaths = 0, [], [], {}
        for seed in range(1, runs + 1):
            bot = DepthsBot(seed=seed, klass=klass)
            result = bot.play()
            w = bot.world
            if result == "win":
                wins += 1
                levels.append(w.player["level"])
                turns.append(w.turn)
            else:
                floor = w.scene.get("floor", 0)
                killer = bot.game.battle.enemy.name if bot.game.battle else "?"
                key = "%s f%s %s" % (result, floor, killer)
                deaths[key] = deaths.get(key, 0) + 1
        print("%-8s wins %2d/%d  avg level %.1f  avg turns %d" % (
            label, wins, runs, (sum(levels) / len(levels)) if levels else 0,
            (sum(turns) / len(turns)) if turns else 0))
        for k, v in sorted(deaths.items(), key=lambda kv: -kv[1])[:6]:
            print("      %2d x %s" % (v, k))


if __name__ == "__main__":
    trial(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
