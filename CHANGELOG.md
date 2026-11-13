# Changelog

Notable changes to CLIo. Versions follow [semantic versioning](https://semver.org).

## 2.0.0 - unreleased

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
- **RPG systems**: levels, experience, gold, character classes, a character generator, shops.
- **Spawning** of characters and a **maze generator** for procedural dungeons.
- **Saves of the whole world** (opened containers, moved characters, unlocked doors) in
  named slots.
- Parser: directions, `use X on Y`, game-defined verbs, typo suggestions, `again`.
- Two demo games, *Derelict* and *The Hollow Depths*, and a starter template to copy.
- A launcher (`clio.py`) with `--style`, `--no-sound`, `--ascii`, `--width`, `--seed`,
  `--check` and more.
- `--test-display`, a page for checking frames, symbols, colours and sprites on a given
  terminal, and `--glyphs safe` for fonts that lack some symbols.
- An authoring guide (`docs/AUTHORING.md`) and 52 automated tests.
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
