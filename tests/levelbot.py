# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Let the level bot (engine/levelbot.py) play a first-person level a number of times.

    python tests/levelbot.py [runs] [game] [level]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import levelbot  # noqa: E402
from engine.data import GameData  # noqa: E402

Bot = levelbot.Bot


def play(game="rootless", level="e1m1", seed=1, verbose=False):
    return levelbot.play(GameData(os.path.join(ROOT, "games", game)), level, seed, verbose)


if __name__ == "__main__":
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    game = sys.argv[2] if len(sys.argv) > 2 else "rootless"
    level = sys.argv[3] if len(sys.argv) > 3 else "e1m1"
    results = []
    for seed in range(runs):
        outcome, lv = play(game, level, seed, verbose=runs == 1)
        results.append((outcome, lv.beat, lv.player.hp, lv.stats["kills"], lv.total_kills, lv.stats["secrets"],
                        lv.boss.gone if lv.boss else None))
        print(seed, *results[-1])
    wins = [r for r in results if r[0] == "exit"]
    print("finished %d of %d; beats %s" % (len(wins), runs, sorted(r[1] for r in wins)))
