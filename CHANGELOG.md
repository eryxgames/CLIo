# Changelog

Notable changes to CLIo. Versions follow [semantic versioning](https://semver.org).

## Unreleased

First-person levels: a scene can hold a map that the player walks through, seen through
his eyes and redrawn in place, with monsters that move a beat at a time. A third demo
game, RØØTLESS, shows them.

### Added

- **First-person levels** (`levels.json`, a scene's `"level"`). A map of characters with a
  legend: walls in four textures, doors, doors that need the r, w or x key, toxic floor,
  secrets that open to a punch or a shot, an exit switch. **Events** tie a level together:
  stepping on a cell or taking an item opens walls and doors, slams doors shut and wakes
  monsters (closets, traps, sealed arenas). `on_level_exit` in the scene says what follows.
  Health, armour, weapons and ammunition go on to the next level; each level's kills,
  items, secrets and beats are kept in the variable `levels`.
- **Monsters for levels** (`monsters.json`): `hitscan` (takes aim a beat, then fires),
  `projectile` (fire that flies and can be side-stepped), `melee`, `spawner`, `barrel`,
  and `cron`, a boss that works to a crontab - fire raining on patterns of the floor,
  marked a beat ahead, and monsters forked - that turns faster when hurt and can escape
  instead of dying (`escape`, which sets off an event). Monsters wake on sight, on
  gunfire they hear, when hurt or on an event, and fight each other when one hurts another.
- **Pick-ups and weapons**: items with a `pickup` block (health, armour, ammunition, keys,
  weapons, `sudo` - nothing hurts for a while, `boots` - toxic floor does not hurt for a
  number of beats spent on it), and `first_person` in game.json for the
  weapons (fist, pistol, shotgun with pellets, chaingun with bursts) and the player's start.
- **The picture**: walls in perspective with textures, a floor and ceiling that stay put
  as the player moves, sprites drawn smaller with distance and hidden behind walls, the
  gun in the player's hands, muzzle flashes, fire, blood, hits that shake the picture,
  an automap (Tab). Three styles: `pixel` (half blocks), `dots` and `dots-fill` (braille).
- **Frame mode** (`engine/frame.py`, `engine/keys.py`): on a real terminal a level has its
  own screen, redrawn in place, with the prompt on the last lines. Keys act at once while
  nothing is typed: arrow keys step and turn, Ctrl/Alt/Shift+arrows or `,` `.` strafe,
  Space fires, Enter uses, Tab shows the map, 1-7 choose a weapon, the numpad works with
  NumLock off; `"keymap"` changes them. Anything else is typed as a command. The picture is
  drawn again as soon as the window changes size, on Windows as on Linux and macOS.
  Piped, with `--scroll` or on a screen under 40 x 18 a level is played in scrolling text.
- **Commands joined as in a shell**: `a; b`, `a && b`, `a || b`, `!!`, `!3`, `alias`; a
  surprise stops the rest of a line. `ps`, `man`, `kill -9`, `history`, `whoami`.
- **Far versions of sprites** (`lod`, `keep`): far away a sprite is drawn from a smaller
  drawing that keeps the pixels that matter (the letters in `keep`, then the rarest
  colours). The engine makes them when a level starts; a sprite can have its own.
- **Monsters grown on a body plan**: `sprite.monster(seed, body, size)` - biped, beast,
  floater, crawler, brute - with eyes kept in the far versions.
- **Things that move**: crates to push (cover from shots; pushed into acid they sink and
  make a step), pressure plates that hold doors and walls open while something heavy
  stands on them, teleporter pads (the picture dissolves into braille dots and back),
  lifts between two places (a ride in dots, the shaft going by) and a level ending in a
  lift (`exit_ride`), secret areas counted when entered. A barrel's blast throws crates
  and monsters a cell away; the shotgun at point blank throws its target back; monsters
  burn on toxic floor. In the picture only, drawn from dice of their own: debris, gibs,
  sparks, acid splashing, spent cases, items bouncing out. TTY goggles (`power:
  "goggles"`): the level in green braille dots, secret walls showing. `push`, `plate` and
  `lift` sounds.
- **An end screen** (`"end_screen"` in game.json): a won game of levels ends on a screen
  of its own - banner, picture, the totals counting up, the ending, what comes next,
  credits and a crontab line still ticking.
- **Tiles** (`tiles.json`): the walls, floors and ceilings of levels drawn from a game's own
  pictures, in the sprites' format and of any size; a tile named like one of the engine's
  takes its place; `frames` change a beat at a time; clear pixels show what is behind a
  wall. A level's `"floor"` and `"ceiling"`, and a legend entry's, lay them.
- **Weapons** in their own file, `weapons.json` (over `first_person` in game.json).
- **The editor**: *Levels* opens a map painter - the map in its tiles with the monsters
  and items drawn, a palette of the level's characters and the engine's, what each one
  means made with a form (walls and their tiles, doors and keys, secrets, monsters,
  items, events), the level seen from any cell and walked through, and the level bot
  playing it five times. *Tiles* are painted like sprites, from the engine's own if you
  like, and seen in a small room on walls, floor or ceiling. *Weapons* have a form and
  are shown in the player's hands, firing. Under Sprites, *Grow a monster* grows one on a
  body plan, and *Far away, in a first-person level* shows the sprite one to six cells
  away, keeps its far versions to paint over them pixel by pixel, makes them again, or
  leaves them to the game.
- **RØØTLESS** (`games/rootless`), the third demo game: E1M1 *Boot Sector*, a first-person
  level with zombie processes, orphans, daemons, a spawner, barrels, five secrets (hazmat
  boots behind a vent, TTY goggles behind a door a crate must hold open), an acid vat with
  ring-0 armour on an island and a teleporter back, a lift from the boots down to the vat,
  a locked arena and Cron, who rains fire on a schedule and escapes to be the final boss
  of the whole game (the flag `cron_escaped`); the exit is a lift down. Its own riff,
  sounds, 28 sprites, a tile and an end screen.
- `--view STYLE`, `--lines` (every command typed, no single keys), `--scroll`.
  `--check` also counts levels and monsters, and checks their maps and references.
- `engine/levelbot.py`: a simple player that walks a level by its `"bot"` goals - if it can
  finish, a person can (`python tests/levelbot.py`, and in the editor). 48 more tests.
- **Sound sets** (`sounds.NAME.json`): other sets of sound effects over a game's own, chosen
  with `--sounds NAME`, `CLIO_SOUNDS`, `"sound_set"` in game.json, or `sound set NAME` while
  playing (in levels too).
- **Sounds from Ballistic Foley Lab** (`engine/audio/ballistic`): a sound can be one of
  Ballistic's physical models - shots, ricochets, blasts, impacts, arcs, energy fields - with
  its parameters, its finishing for games (`"action": "game"`) and several takes that shots
  in a row take turns with. Node.js renders them in the background into the audio cache;
  `--bake-sounds SET` writes them into the game as WAV files that play without Node; with
  neither, the game's own sound plays. `--check` knows Ballistic's presets and parameters.
- Levels play `hit_body` (a shot or blow lands; a monster's own `sounds.hit` first),
  `hit_wall` (a shot meets a wall, or misses) and `fly_by` (a monster's shot goes wide),
  silent unless a game gives them. RØØTLESS has a Ballistic set for its weapons, hits,
  fire, souls, explosions and Cron: `python clio.py rootless --sounds ballistic`. 17 more tests.
- **Ballistic's C engine** ([Ballistic Engine](https://github.com/eigensoundlab/ballistic-engine)): where its library
  is found (`CLIO_BALLISTIC_LIB`, or `engine/audio/ballistic/lib/`; download it from its releases), Ballistic sounds
  of the kinds it has ported (since its 0.4.0, every weapon, blast and energy kind) render through it,
  in the game's process, without Node.js; Node renders the rest. A field's hum stays a seamless loop. `sound` says
  which renders what. 5 more tests, run when the library is there.
- **Ballistic's game sounds**: `engine.js` follows Ballistic 3603078, which adds liquids, mechanisms (doors, locks,
  switches, turrets), heat, fire, footsteps, creature and robot voices, and handling (pickups, coins, potions). Its C
  engine 0.5.0 follows the same commit; it renders RØØTLESS's weapons and Node renders these until they are ported.
  A level plays `footstep` at every step, silent unless the game or its sound set has one; a step into acid plays
  `wade`, and acid that burns `acid_burn`. RØØTLESS's Ballistic set
  gains 29 sounds: footsteps, wading through acid and acid burning, its doors, secret walls, locks, switches,
  alarm and computer, pickups, coins, healing and boots put on, the player's pain, and the sight, attack and
  death calls of its zombies, orphan, daemon and spawner.

### Changed

- The banner font has `Ø`, `ø`, `Æ`, `æ`; in plain ASCII they become `0`, `o`, `AE`, `ae`.

## 2.2.2 - 2026-11-18

Music with more colours: instruments that can be overdriven, detuned, filtered and put in
a room, and generated music whose sound and length a game's designer chooses.

### Added

- **Overdrive in songs.** An instrument can have `"drive"` (0 to 1): its track is
  flattened as by a guitar amplifier, so a root and its fifth on a `saw` wave sound as a
  power chord, and a kit can be made to crack. With `lowpass` after it, the fizz goes.
  Songs without it sound exactly as they did. `docs/AUTHORING.md` now also names the
  other things an instrument can have: `gate`, `lowpass`, `echo`.
- **Three more settings for instruments**, for strings, brass, pads and acid lines:
  `detune` (two more oscillators a few cents above and below), `filter` (a resonant
  low-pass whose cutoff moves over every note: `[from Hz, to Hz, resonance, seconds]`)
  and `room` (a cluster of early echoes). Songs without them sound exactly as they did.
- **Generated music: a sound and a form to choose.** `"sound": "rich"` plays the same
  generated tune on other instruments - strings, a horn or a trumpet, a clarinet, plucked
  strings, an overdriven guitar, as the mood has them - each as loud as its chip
  counterpart; `"chip"`, the default, is CLIo as it has always sounded. `"form"` lays the
  tune's two halves out: `(A)` without the tune, `A-` quietly, `A+` a tone higher;
  `"long"` is `(A) A A B A B- A A+`, more than twice as long before it comes round. Both
  can be said in a track, or once with `music_sound` and `music_form` for the game, a
  scene or a dungeon floor - also in the editor - so a game keeps one sound.
- `synth.render_tracks(song)`: a song track by track, for a player that lets voices be
  switched on and off.

### Changed

- Rendered music and sounds are cached anew once, so that a song written with the new
  instrument settings is not played from an older, plainer render.

## 2.2.1 - 2026-11-17

New names in the demo games, and saved games that cope with a renamed conversation.

### Changed

- Derelict: the cargo hauler has a new name, the CH Erebus, and so has its ship's mind,
  EREBUS (`talk to erebus`). Ask it what the name stands for.
- The Hollow: the boss of the deeper Court is now the Remains of the Hollow King, and the
  quest down the endless floors is The Long Slumber.

### Fixed

- A save keeps each character's dialogue tree by name, so when a game renamed a tree the
  conversation stopped at the greeting. It now falls back to the tree the game names for
  that character. A Derelict game saved in 2.2.0 loads and plays on, under the old names
  until you start a new game.

## 2.2.0 - 2026-11-17

CLIo 2.2 is about how games look. A game can set its title in a graphic style without
drawing a thing, draw pictures and animations in the same styles, and bring any art to
life; the editor shows all of it as the game will draw it. CLIo itself has a new logo.
Games made for 2.1 run unchanged.

### Added

- **Banners.** Any text in one of nine graphic styles - `pixel`, `shadow`, `chrome`,
  `glitch`, `reflect`, `synthwave`, `led`, `dots`, `plain` - and thirteen palettes, or
  colours of your own. A game draws its title this way with `"title_banner"` in game.json,
  puts one up in the story with the `banner` effect (`{"banner": "Chapter II", "style":
  "led"}`), and ends with `"win_banner"` / `"lose_banner"`. Banners wrap and shrink to fit,
  down to a 24-column phone; lower case is drawn as small capitals. Each theme has a style
  of its own for banners that name none. `clio.py --banner TEXT` shows one; `--export FILE`
  writes it as an `.art` file to draw over.
- **A game's own palettes and house style.** `"palettes"` in game.json names colours of the
  game's own, used like the built-in ones; `"banner_defaults"` sets what every banner uses
  unless it says otherwise.
- **Pictures in the styles.** A sprite can be drawn as half blocks (as before), big square
  `blocks`, fine braille `dots`, an `led` panel or `ascii` letters, and can hold more
  drawings that play in turn (`"frames"`, `"fps"`, `"loops"`) or any animation
  (`"effect"`). Every sprite is a picture too: `"art": "torch"` in a scene, a portrait, the
  story's `art` effect and a sprite called `title` all find it when there is no `.art` file
  of that name. Enemies fight in their sprite's style.
- **Animated art.** Effects that play over any art once it is shown: `glitch`, `flicker`,
  `shine`, `twinkle`, `pulse`, `cycle`, `type`, and `frames`, which plays the `@frame`
  drawings an `.art` file has always been able to hold (they were read but never shown).
  Named in the file (`@effect glitch`, `@fps 12`), in game.json (`"title_effect"`) or in
  an effect (`{"art": "door", "effect": "flicker"}`). Only on a real terminal, never with
  `--fast`; Ctrl-C skips.
- **A new CLIo logo**: a little terminal window that types its own name at the prompt. It
  shows in the launcher and on the title screen of games without title art, keeps its window
  without Unicode and fits a 24-column screen in one line.
- **Fourteen more CLIo logos** in `engine/art/logos/`, most with an animation of their own,
  the old logo among them as `classic`. A game picks one with `"logo"`; the launcher with
  `--logo NAME` or `CLIO_LOGO`. `--looks` lists the logos, styles, palettes and animations.
- **The editor draws it all.** Banner fields of game.json are drawn by the engine as you
  type - on a desktop, a phone or a 24-column screen, with a note when a style has to fall
  back to plain letters. The sprite editor has drawings (add, copy, remove, with the one
  before showing faintly underneath), boards up to 64 x 64, a style and an animation, and
  the picture as the game draws it, with *Play the animation*. Palettes are edited as forms;
  the `banner` effect is in the list of effects.
- **`@ascii`** in `.art` files: a hand-made version for terminals without Unicode.

### Changed

- Games without title art, and the launcher, show the new logo. `"logo": "classic"` in
  game.json (or `--logo classic`) brings back the old one.

### Fixed

- In an `.art` palette, `a = #ff8800` read as a comment and gave no colour. A comment now
  needs a space after the `#` (or anything that is not a hex colour).
- Without Unicode, accented letters became the letter and a `?` (`ř` -> `r?`), which also
  pushed lines one column wider per accent. They now just lose the accent.
- Without Unicode, braille dots became `?`; they now become `. ' : #` by how many dots are
  set. The quadrant blocks `▖▗▘▝▚▞` got ASCII stand-ins too.

## 2.1.0 - 2026-11-14

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
- **The editor on the web.** The repository is its own site: opened from a web address
  (GitHub Pages; nothing is built), the editor's page runs the engine in the browser
  (Pyodide) and asks it the same questions it asks the local server
  (`engine/editor/service.py`). Open a game folder, a zip, a new game from the starter, or
  a demo game. In Chrome and Edge it saves straight into the opened folder; elsewhere
  a game is kept by the browser on every save and offered again on the next visit
  (*Carry on with*). The game never leaves the computer. `python -m engine.editor.hosted
  --pack FILE.zip` writes the site as one zip for hosts that take an upload (itch.io);
  shown inside another site's page the editor says so and works without folder access.
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
  the demo games Bolt, the ship's mind, the replicator and Maren now greet you differently the
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
