#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""CLIo launcher.

    python clio.py                 choose a game
    python clio.py derelict        play a game by folder name (or a path)
    python clio.py --list          list the games
    python clio.py depths --seed 7 a reproducible dungeon

Needs only Python 3.8+.  Runs on Linux, macOS, Windows and Termux.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import __author__, __url__, __version__            # noqa: E402
from engine.audio import Audio, Silent                          # noqa: E402
from engine.data import GameData, GameDataError, config_path, find_games   # noqa: E402
from engine.game import Game                                    # noqa: E402
from engine.term import QuitGame, Term                          # noqa: E402
from engine.theme import available_themes, load_theme           # noqa: E402
from engine.ui import UI                                        # noqa: E402


def resolve_game(name):
    """A game folder from a name, a path, or None."""
    if not name:
        return None
    for cand in (name, os.path.join(ROOT, "games", name), os.path.join(ROOT, name)):
        if os.path.isdir(cand) and config_path(cand):
            return cand
    low = name.lower()
    for path, title, _desc in find_games(ROOT):
        if os.path.basename(path).lower().startswith(low) or title.lower().startswith(low):
            return path
    return None


def choose_game(term):
    games = find_games(ROOT)
    if not games:
        term.line("No games found. Put a game folder under 'games/'.")
        return None
    if len(games) == 1:
        return games[0][0]
    ui = UI(term, load_theme("default"))
    from engine.art import ArtLibrary
    logo = ArtLibrary(os.path.join(ROOT, "engine", "art")).get("clio_logo")
    ui.clear()
    ui.title_screen(logo.render(term, ui.width - 4) if logo else [], "",
                    "the stylish command-line game engine",
                    "version %s %s %s" % (__version__, ui.g("dot"), __url__.split("//")[-1]))
    labels = []
    for _path, title, desc in games:
        labels.append("{key}%s{/}%s" % (title, (" {hint}%s %s{/}" % (ui.g("dot"), desc)) if desc else ""))
    pick = ui.menu(labels, title="Choose a game:", cancel_label="Quit")
    return games[pick][0] if pick is not None else None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clio", description="CLIo - a stylish command-line game engine.")
    ap.add_argument("game", nargs="?", help="game folder name or path")
    ap.add_argument("--list", action="store_true", help="list available games and exit")
    ap.add_argument("--check", action="store_true", help="validate the game's data files and exit")
    ap.add_argument("--style", help="visual style (%s)" % ", ".join(available_themes()))
    ap.add_argument("--no-sound", action="store_true", help="run silently")
    ap.add_argument("--no-color", action="store_true", help="plain text, no colours")
    ap.add_argument("--ascii", action="store_true", help="ASCII only (no box-drawing or block characters)")
    ap.add_argument("--no-art", action="store_true", help="hide ASCII art and sprites")
    ap.add_argument("--fast", action="store_true", help="no text animation")
    ap.add_argument("--width", type=int, help="force the layout width in columns")
    ap.add_argument("--seed", type=int, help="random seed (same seed, same dungeon)")
    ap.add_argument("--version", action="version",
                    version="CLIo %s - %s, %s" % (__version__, __author__, __url__))
    args = ap.parse_args(argv)

    if args.list:
        for path, title, desc in find_games(ROOT):
            print("%-12s %s%s" % (os.path.basename(path), title, (" - " + desc) if desc else ""))
        return 0

    term = Term(width=args.width,
                color=0 if args.no_color else None,
                unicode=False if args.ascii else None,
                animate=False if args.fast else None)
    try:
        game_dir = resolve_game(args.game) if args.game else choose_game(term)
    except QuitGame:
        return 0
    if not game_dir:
        if args.game:
            print("No game called '%s'. Try --list." % args.game)
            return 2
        return 0

    try:
        if args.check:
            data = GameData(game_dir)
            problems = data.validate()
            print("%s: %d scenes, %d items, %d characters, %d dialogues, %d quests"
                  % (data.title, len(data.scenes), len(data.items), len(data.characters),
                     len(data.dialogues), len(data.quests)))
            for p in problems:
                print("  ! " + p)
            print("OK" if not problems else "%d problem(s)" % len(problems))
            return 1 if problems else 0
        audio = Silent() if args.no_sound else Audio()
        settings = {}
        if args.no_art:
            settings["art"] = False
        game = Game(game_dir, term=term, audio=audio, seed=args.seed, settings=settings)
        if args.style:
            game.ui.apply_theme(load_theme(args.style, game.data.dir))
    except GameDataError as e:
        print("Cannot start: %s" % e)
        return 2
    game.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
