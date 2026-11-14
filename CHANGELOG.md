# Changelog

Notable changes to CLIo. Versions follow [semantic versioning](https://semver.org).

## Unreleased

### Added

- **Slides and levels in songs.** A note can slide (`c3>c5:16`), be played at a level
  (`c4@5`, from `@0` to `@9`), or change level as it sounds (`c4@2>9:16`); together they
  make risers, falls and swells. Levels also work on chords and drum hits, slides on the
  `noise` wave. Songs written for 2.0 sound exactly as before.
- `synth.tone(..., glide=True)` slides evenly in pitch over the held part of a note.
- **An editor in the browser.** `python clio.py mygame --edit` opens the game as a page
  served by CLIo itself: forms for scenes, items, characters, quests and texts, built from
  a description of the data files (`engine/schema.py`); the engine's own check as you
  type; saving that changes only the lines you changed; a list of where each thing is
  used, and renaming that carries those places along. Standard library only. It is the
  first step towards replacing the tkinter entity editor in `utils/`, which still edits
  CLIo 1 games only.
- **All the text at once.** In the editor: find and replace across everything a player
  reads, and export of every such line to a CSV file - for a spreadsheet, a proofreader
  or a translator - with import to put it back. Ids, conditions and structure are never
  touched; rows that no longer match anything are reported. Also from the command line:
  `--export-text FILE`, `--import-text FILE`.
- **Making an enemy, and trying it.** In the editor: a new enemy of a chosen strength -
  measured as the dungeon generator measures it, against a floor and a rank - started
  from an existing character or a plain one, leaning tough or sharp. *Try in a fight*,
  for a new enemy or any character with stats, runs the engine's own battle code forty
  times per class and shows wins, health left and turns.
- **Pictures.** The editor shows the sprite a character will be drawn with, can grow a
  different creature for it, and has a pixel editor for sprites: paint with mouse or
  keyboard, mirrored or not, change colours and size, or grow one from any words. *Draw
  over it* turns a grown creature into a drawing of your own.
- **Forms for the parts of things.** Exits, stats, moves, quest stages, dialogue nodes and
  choices, item states and effects are edited as forms - add, remove, reorder - instead
  of JSON. Described, like everything else, in `engine/schema.py` (`group`, `rows`, `map`).
- **The map and the conversations.** The editor draws the rooms where the player's own map
  puts them (`automap.layout`), level by level, with locked ways, one-way ways and stairs
  marked; drag a room to pin it elsewhere. A dialogue is drawn as it runs: nodes in the
  order they are reached, choices and automatic jumps as arrows, unreachable nodes and
  jumps to nowhere pointed out.
- **Can it be finished?** A game can keep its way through in `walkthrough.txt` - commands
  as a player types them, `== name` for each further way. The editor plays them on the
  real engine, on the game as it is in the page, and says how each ends, where it stops,
  which lines were refused, and what no walkthrough reaches. `python clio.py mygame
  --walkthrough` does the same for scripts. Derelict has one for each of its three endings.
- **Effects and conditions as forms.** In the editor, what happens (`do`, `on_enter`,
  `on_complete`, what an item answers to being used, what a character does when given
  something...) is a list of lines - an effect chosen from all the engine knows, and its
  target chosen from the game's own things - and a condition (`if`, `when`, `done_when`...)
  is a question chosen the same way, with a tick for *not*. What is richer than a line
  (branches, several questions at once) stays as written and is edited as JSON. The two
  vocabularies are data in `engine/schema.py`, held equal to `engine/conditions.py` by a
  test. Parts only some things have wait under *Add…* instead of lengthening every form.
- Editor: *Check-up* lists rooms that cannot be reached and things nothing refers to.
- Editor: a light / dark / system theme switch, and *Download game* (the folder as a zip).
  The editor now opens at the same address each time (port 8420) when that is free.

### Changed

- The dungeon demo is now called *The Hollow* (it was *The Hollow Depths*). Its folder is
  still `games/depths`, so saves, records and commands are unchanged.

### Fixed

- The condition `talked:<character>` never held: the conversation was recorded, but the
  question was read as an unknown kind and answered no. So a conversation never opened
  with its "we have met" line a second time, and hints that should move on after a talk
  stayed. It is a condition of its own now (`"talked:robot"`, `{"talked": "robot"}`). In
  the demo games Bolt, Marigold, the replicator and Maren now greet you differently the
  second time, as they were written to.

## 2.0.0 - 2026-11-13

A rebuild of the engine. Games written for CLIo 1 still load.

### Added

- **Sound.** A built-in chiptune synthesizer: music and sound effects are written as
  JSON, with no audio files and no third-party packages. A composer writes a track from
  a mood and a seed. Ordinary audio files can still be used. Playback goes through
  whatever the machine has (PipeWire, PulseAudio, ALSA, `afplay`, `mpv`, `ffplay`,
  Termux `play-audio`, Windows multimedia) and stays silent when nothing is found.
- **ASCII art** files with colour masks and a narrow variant for small screens.
- **Pixel sprites** drawn with half-block characters, hand-made or generated from a name.
- **Auto-map** of the explored world (`map`).
- **Status bar** and working text effects: typewriter, fade, glitch, flash, wipes,
  animated title screens.
- **Dialogue trees** with conditions, effects and one-time choices.
- **Quests** with stages that track themselves, a journal, and triggers.
- **Conditions and effects**: a small JSON vocabulary for game logic, so games stay data.
- **Tactical combat**: enemies telegraph their next move; guard, focus, heavy blows,
  skills, status effects, items, fleeing.
- **Fights against groups**: every hostile in the room joins in and shows its own intent;
  targets are picked by number (`strike 2`); skills and items can hit everyone (`area`)
  or spill over onto the rest (`splash`).
- **RPG systems**: levels, experience, gold, character classes, a character generator, shops.
- **Spawning** of characters and a **maze generator** for procedural dungeons, with
  monster packs and **endless dungeons** whose floors are scaled to get harder with depth.
- **Game modes** chosen at the start or with `--mode`, **permadeath** (the run is saved as
  it goes, there is no loading back, the save is erased at the end), **scores** and a
  **records table** (`records`).
- **Saves of the whole world** (opened containers, moved characters, unlocked doors) in
  named slots.
- Parser: directions, `use X on Y`, game-defined verbs, typo suggestions, `again`.
- Two demo games, *Derelict* and *The Hollow Depths* (with a story mode and a rogue mode),
  and a starter template to copy.
- A launcher (`clio.py`) with `--style`, `--no-sound`, `--ascii`, `--width`, `--seed`,
  `--check` and more.
- `--test-display`, a page for checking frames, symbols, colours and sprites on a given
  terminal, and `--glyphs safe` for fonts that lack some symbols.
- An authoring guide (`docs/AUTHORING.md`) and 71 automated tests.
- Apache-2.0 licence for the engine and everything it ships for games to use.

### Changed

- Runs on the Python standard library alone (3.8+). pygame is no longer required.
- Layout adapts from 36 columns (a phone in Termux) to wide terminals, and degrades from
  truecolor to monochrome and from Unicode to plain ASCII.
- The seven themes keep their names and file schema; colours and timings were retuned,
  and not every message is framed any more.
- Conversations in the original `dialogue_options` format continue until the player leaves.
- Unlocking a container also opens it. Repair tools are kept unless marked consumable.
- Saves moved to the user data folder and are not compatible with CLIo 1.

### Removed

- The CLIo 1 engine modules. Early prototypes moved to `legacy/prototypes/`.
- Hard-coded demo behaviour (the `bent_wire` lockpick, fixed passcodes); these are now data.
- Built-in `push` / `pull`: define verbs per item with `actions`.

### Known limitations

- Tested on Linux and on Windows (with and without pygame), with layouts from 24
  columns up. Not yet run on a phone.
- The Tkinter data editor still edits only the CLIo 1 layout in `game_files/`.
- Combat is one enemy at a time.

## 1.0.0-pre - 2025-01-08

The original experimental framework, kept as a reference point before the rebuild.

- JSON-driven scenes, items and characters with a verb parser.
- Inventory, combining, crafting and repairing; characters that craft from given items.
- Simple dialogues, item interactions (trade, information, quest, replicate), wandering
  and following characters.
- A basic attack / defend battle and simple RPG stats.
- Seven console styles with framed, coloured text.
- A Tkinter entity data editor (alpha).
- Requires pygame.
