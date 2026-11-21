#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""CLIo launcher.

    python clio.py                 choose a game
    python clio.py derelict        play a game by folder name (or a path)
    python clio.py --list          list the games
    python clio.py depths --seed 7 a reproducible dungeon
    python clio.py --looks         the logos, banner styles, palettes and animations
    python clio.py rootless --sounds ballistic   play with another set of sound effects
    python clio.py --banner "The Hollow" --banner-style reflect --export art/title.art

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


def walkthrough(game_dir):
    """--walkthrough: play walkthrough.txt; 0 when every walkthrough is won."""
    from engine.editor import finish
    result = finish.play(game_dir)
    if not result["walkthroughs"]:
        print("This game has no %s yet. One command per line; '== name' starts another way through." % finish.FILE)
        return 2
    for w in result["walkthroughs"]:
        print("%s %s: %s in %d turns" % ("ok  " if w["won"] else "FAIL", w["name"], w["result"] or "not finished", w["turns"]))
        if w["stopped"]:
            print("     line %s, '%s': %s" % (w["stopped"]["line"], w["stopped"]["command"], w["stopped"]["why"]))
        for r in w["refused"]:
            print("     line %d, '%s' was refused: %s" % (r["line"], r["command"], r["said"]))
    for what, cover in result["coverage"].items():
        if cover["missing"]:
            print("No walkthrough reaches these %s: %s" % (what, ", ".join(cover["missing"])))
    return 0 if result["finished"] else 1


def bake_sounds(game_dir, name):
    """--bake-sounds: render a set's Ballistic sounds into the game as WAV files, which play without Node.js."""
    from engine.audio import ballistic
    data = GameData(game_dir)
    want = name.strip().lower()
    table = data.sounds if want == "default" else data.sound_sets.get(want)
    if table is None:
        print("'%s' has no sound set called '%s' (it has: %s)."
              % (data.title, name, ", ".join(["default"] + sorted(data.sound_sets))))
        return 2
    found = [(n, s) for n, s in table.items() if ballistic.is_spec(s)]
    if not found:
        print("The %s sounds of %s have no Ballistic sounds to bake." % (want, data.title))
        return 0
    problems = [p for n, s in found for p in ballistic.problems(s, "sound '%s'" % n)]
    if problems:
        for p in problems:
            print("  ! " + p)
        print("Nothing was baked: %d problem(s)." % len(problems))
        return 1
    sounds = ballistic.Sounds(lambda: game_dir, lambda: game_dir, sync=True)
    if not sounds.available():
        print("Baking needs Node.js, which was not found. Install it, or set CLIO_NODE to the node program.")
        return 2
    folder = sounds.baked_dir(None if want == "default" else want)
    near = os.path.relpath(folder)
    print("Baking %d sounds into %s" % (len(found), folder if near.startswith("..") else near))
    try:
        bad = sounds.bake(None if want == "default" else want, found, report=lambda line: print("  " + line))
    finally:
        sounds.close()
    for b in bad:
        print("  ! " + b)
    if bad:
        return 1
    print("Done. These files play without Node.js; bake again after changing a sound.")
    return 0


def text_table(game_dir, out_file=None, in_file=None):
    """--export-text / --import-text: the game's texts as a CSV file, out or back in."""
    from engine import editor
    from engine.editor import texts
    if out_file:
        table = editor.text_table(game_dir)
        with open(out_file, "w", encoding="utf-8-sig", newline="") as f:      # with a mark so spreadsheets read it as UTF-8
            f.write(texts.to_csv(table))
        print("%d texts written to %s" % (len(table), out_file))
        return 0
    try:
        with open(in_file, encoding="utf-8-sig", newline="") as f:
            table = texts.from_csv(f.read())
    except (OSError, ValueError) as err:
        print("Cannot read %s: %s" % (in_file, err))
        return 2
    result = editor.put_texts(game_dir, table)
    report = result["report"]
    problems = editor.check(game_dir, result["files"])
    if problems:
        print("Nothing was changed: with these texts the game would have problems.")
        for p in problems:
            print("  ! " + p["text"])
        return 1
    for key, data in result["files"].items():
        editor.save(game_dir, key, data)
    print("%d texts changed in %d file(s), %d unchanged." % (report["changed"], len(report["files"]), report["same"]))
    for where in report["missing"]:
        print("  ? no text at %s" % where)
    return 0


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


def launcher_logo(term, ui, name=None, effect=None):
    """The logo the launcher shows (--logo, or CLIO_LOGO) and its animation."""
    from engine.art import load_logo
    logo = load_logo(name or os.environ.get("CLIO_LOGO")) or load_logo(None)
    if not logo:
        return [], [], False
    lines = logo.render(term, ui.width - 4)
    frames, reveals = ([], False)
    if ui.animated:
        frames, reveals = logo.animation(term, ui.width - 4, None, effect, seed="clio")
    return lines, frames, reveals


def choose_game(term, logo=None, effect=None):
    games = find_games(ROOT)
    if not games:
        term.line("No games found. Put a game folder under 'games/'.")
        return None
    if len(games) == 1:
        return games[0][0]
    ui = UI(term, load_theme("default"))
    lines, frames, reveals = launcher_logo(term, ui, logo, effect)
    ui.clear()
    ui.title_screen(lines, "", "the stylish command-line game engine",
                    "version %s %s %s" % (__version__, ui.g("dot"), __url__.split("//")[-1]), frames, reveals)
    labels = []
    for _path, title, desc in games:
        labels.append("{key}%s{/}%s" % (title, (" {hint}%s %s{/}" % (ui.g("dot"), desc)) if desc else ""))
    from engine import demo
    tech = demo.tech() if term.is_tty and term.ansi and term.inp is None else None
    if tech:                                      # the tech demo: chosen, or after a while with no key
        labels.append("{key}Tech demo{/} {hint}%s CLIo shows what it can do{/}" % ui.g("dot"))
    from engine import downloads
    extras = term.is_tty and term.inp is None and downloads.wanted()
    if extras:                                    # what is not here yet: asked about, never fetched unasked
        labels.append("{key}Downloads{/} {hint}%s faster pictures, sounds without Node.js - optional{/}" % ui.g("dot"))
    idle = demo.idle_play(term, tech)
    while True:
        pick = ui.menu(labels, title="Choose a game:", cancel_label="Quit", idle=idle)
        if pick is not None and tech and pick == len(games):
            demo.play(term, tech)
            continue
        if pick is not None and extras and pick == len(labels) - 1:
            downloads.menu(term, ui)
            continue
        return games[pick][0] if pick is not None else None


def looks():
    """--looks: what a game can choose for its title screen."""
    from engine import banner, fx
    from engine.art import logo_names
    print("Logos (\"logo\" in game.json, --logo, CLIO_LOGO):")
    print("  " + ", ".join(logo_names()))
    print("Banner styles (\"title_banner\": {\"style\": ...}, --banner-style):")
    for name, what in banner.STYLES.items():
        print("  %-10s %s" % (name, what))
    print("Palettes (\"palette\", --palette):")
    print("  " + ", ".join(banner.PALETTES))
    print("Animations (\"title_effect\", \"effect\", --effect, @effect in an .art file):")
    for name, what in fx.EFFECTS.items():
        print("  %-10s %s" % (name, what))
    return 0


def draw_banner(term, text, style=None, palette=None, effect=None, export=None):
    """--banner: draw a banner (and play its animation), or write it as an .art file."""
    from engine import banner
    ui = UI(term, load_theme("default"))
    spec = {"text": text}
    for key, value in (("style", style), ("palette", palette), ("effect", effect)):
        if value:
            spec[key] = value
    if style and style not in banner.STYLES:
        print("No banner style called '%s'. There are: %s" % (style, ", ".join(banner.STYLES)))
        return 2
    if palette and "#" in palette:
        spec.pop("palette")
        spec["colors"] = [c.strip() for c in palette.split(",")]
    elif palette and palette not in banner.PALETTES:
        print("No palette called '%s'. There are: %s (or give colours: \"#fff07a,#ff6f91\")"
              % (palette, ", ".join(banner.PALETTES)))
        return 2
    if export:
        art = banner.export(spec)
        if art is None:
            print("Nothing to draw.")
            return 2
        with open(export, "w", encoding="utf-8") as f:
            f.write(art.to_text("banner: %s" % text))
        print("Wrote %s (%s). Put it in a game's art/ folder; title.art becomes the title screen."
              % (export, ", ".join("%s %dx%d" % ((k,) + art.size(k)) for k in art.variants)))
        return 0
    art = banner.make(spec, ui.width - 4)
    if art is None:
        print(text)
        return 0
    lines = art.render(term)
    frames, reveals = art.animation(term, ui.width - 4, None, None, seed=text) if ui.animated else ([], False)
    ui.play_art(lines, frames, reveals)
    return 0


def play_demo(term, game=None, loop=False):
    """--demo: a game's own demo, or CLIo's tech demo."""
    from engine import demo
    if game:
        game_dir = resolve_game(game)
        if not game_dir:
            print("No game called '%s'. Try --list." % game)
            return 2
        spec = demo.of_game(game_dir)
        if spec is None:
            print("This game has no demo yet (demo.json; see docs/AUTHORING.md).")
            return 2
    else:
        spec = demo.tech()
    if demo.play(term, spec, loop=loop) is None:
        print("A demo needs a terminal it can draw on (not a pipe, not TERM=dumb).")
        return 2
    return 0


TERMUX_KEYS = r"""# Extra keys for playing CLIo's first-person levels in Termux. Put these lines in
# ~/.termux/termux.properties (mkdir -p ~/.termux first), then run: termux-reload-settings
# Swipe up on a key for the key above it. Volume Up + Q shows or hides the row; Volume Up +
# W A S D are the arrows. In a level, taps on the picture act too (clio.py --touch off: not).
#
#   ESC (F1 help)  <<  strafe  UP  >>  strafe   FIRE        NEXT weapon (1 fist)  SAVE (LOAD)
#   MAP            LEFT turn   DOWN RIGHT turn  USE (open)  TTY goggles           KEYBOARD
extra-keys = [[   {key: ESC, popup: F1},   {key: ',', display: '<<', popup: '<'},   {key: UP},   {key: '.', display: '>>', popup: '>'},   {key: SPACE, display: FIRE},   {key: ']', display: NEXT, popup: '1'},   {key: F5, display: SAVE, popup: F9} ], [   {key: TAB, display: MAP},   {key: LEFT},   {key: DOWN},   {key: RIGHT},   {key: ENTER, display: USE},   {key: F2, display: TTY},   {key: KEYBOARD} ]]"""


def display_test(term, logo_name=None):
    """Draw a page that shows at a glance whether this terminal renders CLIo correctly."""
    from engine.sprite import generate
    from engine.term import is_termux, pad_to
    ui = UI(term, load_theme("default"))
    w = ui.width
    cols, rows = term.size()
    depth = {0: "none", 1: "16", 2: "256", 3: "truecolor"}[term.color_depth]
    where = "Termux" if is_termux() else sys.platform
    ui.heading("DISPLAY TEST")
    ui.say("Terminal %dx%d, layout width %d. Colours: %s. Unicode: %s. Symbols: %s. System: %s."
           % (cols, rows, w, depth, "yes" if term.unicode else "no", term.glyph_mode, where), "system")

    ui.say("{key}1. Ruler{/} - the line below should end at the mark, with no wrapping:", "default")
    ruler = "".join("|" if i % 10 == 0 else "-" for i in range(w - 1)) + "#"
    ui.line(ruler)

    ui.say("{key}2. Frames{/} - corners joined, right edge straight:", "default")
    for frame in ("ROUNDED", "DOUBLE"):
        ui.say("The quick brown fox jumps over the lazy dog.", "default", frame=frame, title=frame.title())

    ui.say("{key}3. Symbols{/} - each should be one clear character, not a box, '?' or a picture. "
           "The right edge must stay straight on every row:", "default")
    names = ["heart", "note", "star", "bullet", "arrow", "check", "cross", "flag", "coin", "shield",
             "sword", "dot", "up", "down", "bar_full", "bar_empty"]
    cells = ["%-9s %s" % (n, term.glyphs[n]) for n in names]
    per_row = max(1, (w - 4) // 14)
    body = ["   ".join(pad_to(c, 11) for c in cells[i:i + per_row]) for i in range(0, len(cells), per_row)]
    for l in ui.box_lines(body, "default", None, "SINGLE", 1):
        ui.line(l)
    ui.gap()

    ui.say("{key}4. Fine shapes{/} - bars rising, eight arrows turning, dots - no '?' or boxes:", "default")
    from engine.frame import Screen
    heading = Screen(term).glyphs["heading"]
    ui.line("   " + "▁▂▃▄▅▆▇█" + "   " + " ".join(heading) + "   " + "".join(chr(0x2800 + b) for b in
                                                                         (0x01, 0x09, 0x1B, 0x3F, 0x7F, 0xFF)))
    if term.glyph_mode == "console":
        ui.say("Drawn for the Windows console's fonts: fine bars, diagonal arrows and dots are swapped for "
               "the nearest they have. Windows Terminal shows them all.", "dim")

    ui.say("{key}5. Colours{/} - a smooth run of colour, and readable roles:", "default")
    if term.color_depth >= 2:
        ui.line(" " + "".join(term.paint(term.glyphs["block"], str(c)) for c in
                              ([196, 202, 208, 214, 220, 226, 190, 154, 118, 82, 46, 47, 48, 49, 50, 51, 45, 39,
                                33, 27, 21, 57, 93, 129, 165, 201, 200, 199, 198, 197] * 3)[:w - 2]))
    ui.say("{item}item{/} {character}character{/} {exit}exit{/} {error}error{/} {success}success{/} "
           "{quest}quest{/} {hint}hint{/}", "default")

    ui.say("{key}6. Pixel sprite and art{/} - a small creature with two eyes, and the CLIo logo:", "default")
    for l in generate("display test", 12).render(term):
        ui.line("   " + l)
    from engine.art import load_logo
    logo = load_logo(logo_name or os.environ.get("CLIO_LOGO")) or load_logo(None)
    for l in (logo.render(term, w - 4) if logo else []):
        ui.line("   " + l)
    ui.gap()
    ui.say("If symbols look wrong, run with {key}--glyphs console{/} (the old Windows console fonts) or "
           "{key}--glyphs safe{/} (or set CLIO_GLYPHS). "
           "If frames or the sprite look wrong, use {key}--ascii{/}. If colours look wrong, use {key}--no-color{/}. "
           "In a game, {key}art off{/} hides art and sprites.", "hint")
    return 0


def compact_json(obj, indent=0):
    """JSON as a person reads it, with long lists of numbers kept on one line each (a vertex, a frame)."""
    import json
    pad = " " * (indent + 1)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        inner = (",\n").join("%s%s: %s" % (pad, json.dumps(k, ensure_ascii=False), compact_json(v, indent + 1))
                              for k, v in obj.items())
        return "{\n%s\n%s}" % (inner, " " * indent)
    if isinstance(obj, list) and obj and all(isinstance(x, list) for x in obj):
        inner = (",\n").join(pad + compact_json(x, indent + 1) for x in obj)
        return "[\n%s\n%s]" % (inner, " " * indent)
    return json.dumps(obj, ensure_ascii=False, separators=(", ", ": ") if not isinstance(obj, list) else (",", ":"))


def import_model(game_dir, path, name=None, scale=0.4):
    """``--import-model``: a glTF file into the game's models.json (a model of that name keeps how it was set
    to move - bob, turning, smooth, spin, scale - and takes the rest from the file)."""
    import json
    from collections import OrderedDict
    from engine import gltf, model
    try:
        spec, notes = gltf.to_model(path, scale=scale)
    except (OSError, gltf.GltfError, KeyError, IndexError, struct_error()) as e:
        print("Cannot read %s: %s" % (path, e))
        return 2
    name = name or "".join(c if c.isalnum() or c in "-_" else "_" for c in
                           os.path.splitext(os.path.basename(path))[0].lower())
    target = os.path.join(game_dir, "models.json")
    table = OrderedDict()
    if os.path.isfile(target):
        with open(target, encoding="utf-8") as f:
            table = json.load(f, object_pairs_hook=OrderedDict)
    old = table.get(name) or {}
    new = OrderedDict((k, v) for k, v in old.items() if k in ("bob", "turning", "smooth", "spin", "scale"))
    new.update(spec)
    new.pop("notes", None)
    table[name] = new
    wrong = model.problems({name: new})
    if wrong:
        print("The model does not come out right:\n  " + "\n  ".join(wrong))
        return 2
    with open(target + ".tmp", "w", encoding="utf-8") as f:
        f.write(compact_json(table) + "\n")
    os.replace(target + ".tmp", target)
    m = model.Model(name, new)
    clips = ", ".join("%s (%d)" % (k, len(v)) for k, v in (new.get("frames") or {}).items()) or "none"
    print("Model '%s' in %s: %d triangles, %d materials, %.2f cells high; animations: %s."
          % (name, target, len(m.faces), len(m.materials), m.height, clips))
    for n in notes:
        print("  note: " + n)
    print('A monster or a vehicle uses it with "model": "%s" in monsters.json; an item in its "pickup".' % name)
    return 0


def struct_error():
    import struct
    return struct.error


def write_sheet(game_dir, what, scale, out=None):
    """``--sheet``: the game's pictures on one PNG, and its atlas beside it."""
    import json
    from engine import sheets
    try:
        data = GameData(game_dir)
    except GameDataError as e:
        print("Cannot read the game: %s" % e)
        return 2
    png, atlas = sheets.sheet(data, what, scale)
    out = out or "%s-%s.png" % (data.id, what)
    if not out.lower().endswith(".png"):
        out += ".png"
    atlas["meta"]["image"] = os.path.basename(out)
    with open(out, "wb") as f:
        f.write(png)
    side = out[:-4] + ".json"
    with open(side, "w", encoding="utf-8") as f:
        json.dump(atlas, f, indent=1)
    size = atlas["meta"]["size"]
    print("Wrote %s (%d pictures, %dx%d) and %s." % (out, len(atlas["frames"]), size["w"], size["h"], side))
    return 0


def read_sheet(game_dir, png_file):
    """``--import-sheet``: an edited sheet back into the game - only the pictures that were changed."""
    import json
    from engine import editor, sheets
    side = (png_file[:-4] if png_file.lower().endswith(".png") else png_file) + ".json"
    try:
        with open(png_file, "rb") as f:
            _w, _h, rows = sheets.read_png(f.read())
        with open(side, encoding="utf-8") as f:
            atlas = json.load(f)
        result = sheets.import_sheet(editor.current(game_dir), rows, atlas)
    except (OSError, ValueError) as err:
        print("Cannot take the sheet back: %s" % err)
        return 2
    report = result["report"]
    if result["files"]:
        problems = editor.check(game_dir, result["files"])
        if problems:
            print("Nothing was changed: with these pictures the game would have problems.")
            for p in problems:
                print("  ! " + p["text"])
            return 1
    for key, data in result["files"].items():
        editor.save(game_dir, key, data)
    print("%d picture(s) changed, %d the same." % (len(report["changed"]), report["same"]))
    for name in report["changed"]:
        print("  * " + name)
    for note in report["skipped"]:
        print("  ? left out: " + note)
    for name in report["unknown"]:
        print("  ? not in the game: " + name)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clio", description="CLIo - a stylish command-line game engine.")
    ap.add_argument("game", nargs="?", help="game folder name or path")
    ap.add_argument("--list", action="store_true", help="list available games and exit")
    ap.add_argument("--check", action="store_true", help="validate the game's data files and exit")
    ap.add_argument("--edit", action="store_true", help="open the game in the editor (a page in your browser)")
    ap.add_argument("--port", type=int, help="port for the editor (default: 8420, or any free one)")
    ap.add_argument("--walkthrough", action="store_true",
                    help="play the game's walkthrough.txt and say whether every way through still ends in a win")
    ap.add_argument("--export-text", metavar="FILE", help="write every line a player can read to a CSV file and exit")
    ap.add_argument("--import-text", metavar="FILE", help="put the texts of such a CSV file back into the game and exit")
    ap.add_argument("--no-browser", action="store_true", help="with --edit: print the address, do not open it")
    ap.add_argument("--style", help="visual style (%s)" % ", ".join(available_themes()))
    ap.add_argument("--no-sound", action="store_true", help="run silently")
    ap.add_argument("--sounds", metavar="SET",
                    help="play another set of sound effects, from the game's sounds.SET.json (also CLIO_SOUNDS)")
    ap.add_argument("--get-ballistic", action="store_true",
                    help="download Ballistic Engine's library for this machine into your data folder and exit")
    ap.add_argument("--get-picture", action="store_true",
                    help="download CLIo Picture's library (faster land and dots pictures) for this machine and exit")
    ap.add_argument("--bake-sounds", metavar="SET",
                    help="render the set's Ballistic sounds into the game as WAV files (needs Node.js) and exit")
    ap.add_argument("--no-color", action="store_true", help="plain text, no colours")
    ap.add_argument("--ascii", action="store_true", help="ASCII only (no box-drawing or block characters)")
    ap.add_argument("--glyphs", choices=("full", "console", "safe", "ascii"),
                    help="symbol set: 'console' keeps to the old Windows console fonts (the default there); "
                         "'safe' keeps frames but uses plain symbols (for fonts that lack them)")
    ap.add_argument("--test-display", action="store_true",
                    help="show a test page to check frames, symbols, colours and sprites on this terminal")
    ap.add_argument("--no-art", action="store_true", help="hide ASCII art and sprites")
    ap.add_argument("--view", choices=("pixel", "dots", "dots-fill"),
                    help="how first-person levels are drawn: pixel (half blocks), dots or dots-fill (braille)")
    ap.add_argument("--render", choices=("classic", "mesh"),
                    help="first-person rooms: classic (each cell 0.64 the size of the one before) or mesh (a true "
                         "perspective, floors at their own heights, as open land is drawn)")
    ap.add_argument("--detail", choices=("auto", "high", "low"),
                    help="first-person levels: low draws the floor and ceiling at half width (faster in a big "
                         "window); auto (the default) does so only for a very big picture")
    ap.add_argument("--lines", action="store_true", help="in first-person levels: typed lines only, no single keys")
    ap.add_argument("--touch", choices=("on", "off"),
                    help="first-person levels: taps on the picture turn, step, fire and use, swipes step "
                         "(on by default in Termux; it takes the mouse, so text cannot be selected)")
    ap.add_argument("--demo", action="store_true",
                    help="play a demo and exit: the game's own (its demo.json), or CLIo's tech demo when no game "
                         "is named")
    ap.add_argument("--attract", action="store_true",
                    help="like --demo, but over and over until a key is pressed (a kiosk, a shop window)")
    ap.add_argument("--termux-keys", action="store_true",
                    help="print a row of extra keys for Termux's keyboard that plays first-person levels, and exit")
    ap.add_argument("--realtime", nargs="?", type=float, const=0.8, metavar="SECONDS",
                    help="play first-person levels in real time: a beat passes every SECONDS (0.8) when no key "
                         "is pressed; 0 turns it off for levels that ask for it")
    ap.add_argument("--keys", action="store_true",
                    help="show how this terminal reports keys to a game in real time (held, let go) and exit")
    ap.add_argument("--dev", action="store_true",
                    help="for making a game: in levels *ID jumps to a level and saves are not counted (also CLIO_DEV=1)")
    ap.add_argument("--level", metavar="ID", help="start a new game in the scene that plays level (or stage, skirmish or sim) ID (implies --dev)")
    ap.add_argument("--scroll", action="store_true", help="play first-person levels in scrolling text")
    ap.add_argument("--fast", action="store_true", help="no text animation")
    ap.add_argument("--width", type=int, help="force the layout width in columns")
    ap.add_argument("--seed", type=int, help="random seed (same seed, same dungeon)")
    ap.add_argument("--mode", help="game mode, for games that have several (e.g. story, rogue)")
    ap.add_argument("--logo", help="the CLIo logo the launcher shows (see --looks; also CLIO_LOGO)")
    ap.add_argument("--effect", help="animation for --logo or --banner (see --looks; 'none' for none)")
    ap.add_argument("--looks", action="store_true",
                    help="list the logos, banner styles, palettes and animations a game can use")
    ap.add_argument("--banner", metavar="TEXT", help="draw TEXT in a graphic style and exit")
    ap.add_argument("--banner-style", metavar="NAME", help="with --banner: the style (see --looks)")
    ap.add_argument("--palette", metavar="NAME", help="with --banner: the colours (see --looks), or '#fff07a,#ff6f91'")
    ap.add_argument("--export", metavar="FILE",
                    help="with --banner: write it as an .art file to edit by hand; with --sheet: the PNG's name")
    ap.add_argument("--sheet", choices=("monsters", "sprites", "tiles"),
                    help="write a sheet of the game's pictures as PNG, with an atlas (JSON) of where each one is, and exit")
    ap.add_argument("--scale", type=int, default=4, help="with --sheet: how many times as big the pictures are (4)")
    ap.add_argument("--import-model", metavar="FILE",
                    help="bring a glTF model (.glb or .gltf, e.g. from Blender) into the game's models.json and exit")
    ap.add_argument("--model-name", metavar="NAME", help="with --import-model: its name (default: the file's)")
    ap.add_argument("--model-scale", type=float, default=0.4,
                    help="with --import-model: cells per metre (0.4: a 2.5 m room is a cell high)")
    ap.add_argument("--import-sheet", metavar="FILE",
                    help="take an edited sheet (FILE.png, with FILE.json beside it) back into the game and exit")
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
                animate=False if args.fast else None,
                glyphs=args.glyphs)
    if args.looks:
        return looks()
    if args.get_ballistic:
        from engine.audio.ballistic import fetch
        return fetch.get()
    if args.get_picture:
        from engine.picture import fetch as picture_fetch
        return picture_fetch.get()
    if args.banner:
        return draw_banner(term, args.banner, args.banner_style, args.palette, args.effect, args.export)
    if args.logo:
        from engine.art import load_logo, logo_names
        if load_logo(args.logo) is None:
            print("No logo called '%s'. There are: %s" % (args.logo, ", ".join(logo_names())))
            return 2
    if args.test_display:
        return display_test(term, args.logo)
    if args.termux_keys:
        print(TERMUX_KEYS)
        return 0
    if args.keys:
        from engine.realtime import key_test
        if not term.is_tty:
            print("--keys needs a terminal to read keys from.")
            return 2
        key_test()
        return 0
    if args.demo or args.attract:
        return play_demo(term, args.game, args.attract)
    try:
        game_dir = resolve_game(args.game) if args.game else choose_game(term, args.logo, args.effect)
    except QuitGame:
        return 0
    if not game_dir:
        if args.game:
            print("No game called '%s'. Try --list." % args.game)
            return 2
        return 0

    if args.edit:
        from engine.editor.server import serve
        return serve(game_dir, args.port, not args.no_browser)
    if args.walkthrough:
        return walkthrough(game_dir)
    if args.export_text or args.import_text:
        return text_table(game_dir, args.export_text, args.import_text)
    if args.sheet:
        return write_sheet(game_dir, args.sheet, args.scale, args.export)
    if args.import_sheet:
        return read_sheet(game_dir, args.import_sheet)
    if args.import_model:
        return import_model(game_dir, args.import_model, args.model_name, args.model_scale)
    if args.bake_sounds:
        try:
            return bake_sounds(game_dir, args.bake_sounds)
        except GameDataError as e:
            print("Cannot read the game: %s" % e)
            return 2
    try:
        if args.check:
            data = GameData(game_dir)
            problems = data.validate()
            print("%s: %d scenes, %d items, %d characters, %d dialogues, %d quests%s"
                  % (data.title, len(data.scenes), len(data.items), len(data.characters),
                     len(data.dialogues), len(data.quests),
                     (", %d levels, %d monsters, %d weapons, %d tiles" % (len(data.levels), len(data.monsters), len(data.weapons),
                                                                         len(data.tiles))) if data.levels else "")
                     + (", %d models" % len(data.models) if getattr(data, "models", None) else ""))
            for p in problems:
                print("  ! " + p)
            print("OK" if not problems else "%d problem(s)" % len(problems))
            return 1 if problems else 0
        audio = Silent() if args.no_sound else Audio()
        settings = {}
        if args.no_art:
            settings["art"] = False
        if args.view:
            settings["view"] = args.view
        if args.detail:
            settings["detail"] = args.detail
        if args.render:
            settings["render"] = args.render
        if args.dev or args.level or os.environ.get("CLIO_DEV", "").lower() in ("1", "yes", "true", "on"):
            settings["dev"] = True
        if args.level:
            settings["start_level"] = args.level
        if args.lines:
            settings["lines"] = True
        if args.realtime is not None:
            settings["realtime"] = max(0.0, args.realtime)
        if args.touch:
            settings["touch"] = args.touch == "on"
        if args.scroll:
            settings["scroll_levels"] = True
        if args.sounds:
            settings["sound_set"] = args.sounds
        game = Game(game_dir, term=term, audio=audio, seed=args.seed, settings=settings, mode=args.mode)
        if args.mode and args.mode not in game.modes:
            print("'%s' has no mode called '%s'%s." % (
                game.data.title, args.mode,
                (" (it has: %s)" % ", ".join(game.modes)) if game.modes else ""))
            return 2
        if args.sounds and not game.audio.set_sound_set(args.sounds):
            print("'%s' has no sound set called '%s' (it has: %s)." % (
                game.data.title, args.sounds, ", ".join(["default"] + sorted(game.data.sound_sets))))
            return 2
        if args.style:
            game.ui.apply_theme(load_theme(args.style, game.data.dir))
    except GameDataError as e:
        print("Cannot start: %s" % e)
        return 2
    game.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
