# CLIo

**CLIo** is a stylish game engine for the command line: text adventures and RPGs
with themed frames, ASCII art, pixel-art sprites, an auto-map and a built-in
chiptune synthesizer. Games are folders of JSON; the engine is plain Python.

Created by **Daniel Sandner** · [eryxian.com](https://eryxian.com)

- **No dependencies.** Python 3.8+ and the standard library. Nothing to `pip install`.
- **Runs anywhere a terminal does.** Linux, macOS, Windows, and Android via Termux.
  The layout adapts from a 36-column phone screen to a wide desktop terminal.
- **Degrades gracefully.** Truecolor → 256 colours → 16 colours → monochrome;
  Unicode → plain ASCII; sound → silence. A game never fails because a terminal is modest.

```
python clio.py            # pick a game
python clio.py derelict   # sci-fi adventure
python clio.py depths     # dungeon crawler
python clio.py depths --mode rogue    # ...with one life and no bottom
python clio.py rootless   # first-person shooter in a terminal
```

## The demo games

| Game | What it shows |
| --- | --- |
| **Derelict** (`games/derelict`) | A complete short adventure aboard an abandoned cargo hauler. Puzzles, dialogue trees, quests, a wandering NPC, one tactical fight that can also be talked around, and three endings. |
| **The Hollow** (`games/depths`) | A dungeon crawler that is different on every run: three generated floors, three character classes, tactical combat against single monsters and packs, loot, shrines, a peddler, generated monster sprites and generated music. `--seed 7` replays the same dungeon. **Rogue mode** gives you one life and a dungeon that keeps going down, with a table of the best runs. **Deck mode** plays every fight as a card battle: a deck per class, a card to take after every win, and a Hollow King who plays his own deck and chooses his cards by Monte Carlo tree search. |
| **RØØTLESS** (`games/rootless`) | A first-person shooter drawn in the terminal, a beat at a time: a recruit's first battle simulation - E1M1 *Boot Sector*, E1M2 *Dynamic Loader*, E1M3 *Drone Refit Assembly*, E1M4 *Xantrium Fens* (open land to the horizon) and the secret level E1M9 *Swap Partition*, the start of a game in the making; and three free programs made new each run - SIM-1 *Long Fens* (open land without end), SIM-2 *Deep Swap* (floor after floor) and SIM-3 *Swap Sprawl* (rooms without end); and a training program, SIM-4 *Kill House* (a room for each kind of squad: bugrat packs, sweep squads, an ambush, commandos). Walk with the arrow keys, strafe, fire with Space; zombie processes, orphans, daemons, flamethrowers, a minigun, a shovel, a chainsaw, a rocket launcher and grenades that bounce, a cargo loader to ride across the acid, drones drawn as 3D models, balls of Xantrium that roll and crush, a hopper to fly out over a swamp under an alien sky, fens and hills to cross on foot or in the air, barrels to shoot or roll, crates to push, oil that burns, slick floor, belts, keys and locked doors, secrets to punch and shoot, and Cron, who rains fire on a schedule. Typed commands work too, joined as in a shell (`f z1 && w || h`). F5 saves (three times a level) and F9 loads. `--view dots` draws it in braille. |
| **Sandbox** (`game_files`) | The original CLIo 1 test bed, loaded unchanged by the new engine. |

## Features

- [x] Core engine: scenes, exits (locked, blocked, guarded, hidden), items, fixtures with state machines
- [x] Parser with synonyms, directions, `use X on Y`, `give X to Y`, game-defined verbs, typo suggestions
- [x] Inventory, equipment slots, crafting, combining, repairing
- [x] Simple dialogues (original format) **and** branching dialogue trees with conditions and effects
- [x] Character interaction: giving, trading, NPC crafting, shops
- [x] Character movement, followers, ambushes, guards
- [x] Character/enemy spawning (`spawn` effect, generated dungeons)
- [x] Quests with stages that track themselves, a journal, triggers
- [x] RPG features: stats, levels, experience, gold, classes
- [x] Tactical combat: telegraphed enemy moves, guard/focus/heavy, skills, status effects, items, fleeing
- [x] Fights against groups: every enemy shows its intent, targets by number, area skills and items
- [x] Character generator (name and class at the start of a game)
- [x] Sounds and music: synthesizer, generative composer, optional audio files
- [x] Sound sets, and physically modelled shots, ricochets and blasts from
      [Ballistic Foley Lab](https://github.com/eigensoundlab/ballistic)'s engine (rendered with Node.js, or baked)
- [x] Styling: seven themes, frames, typewriter / fade / glitch effects, HUD
- [x] ASCII art with colour masks, half-block pixel sprites, procedural sprites
- [x] Banners: a game's title (or any text) in nine graphic styles and thirteen palettes, with
      animation - glitch, flicker, shine, twinkle, pulse, colour cycle, typing, hand-drawn frames
- [x] A game's own palettes and house style for banners, drawn live in the editor
- [x] Pictures in the same styles - half blocks, square blocks, braille dots, LED, ASCII -
      with drawings that play in turn, drawn and played in the editor
- [x] Fifteen CLIo logos to choose from, most of them animated
- [x] Auto-map
- [x] Generative maze, monster packs, endless dungeons that scale with depth
- [x] Game modes (for example story and rogue), permadeath, scores and a records table
- [x] Card battles: decks, hands and energy, enemies that show what they will do, duellists with
      decks of their own that choose by search, card rewards; a mode or a character turns them on
- [x] First-person levels: a map drawn in perspective and redrawn in place (frame mode),
      textured walls, sprites that shrink with distance and keep their eyes, monsters that
      aim, throw fire, charge, spawn and fight each other, keys, doors, secrets, events,
      a boss on a schedule, an automap; arrow keys or typed commands, any window size;
      a game's own tiles for walls, floors and ceilings; crates, pressure plates, teleporters
      and lifts; debris and gibs; an end screen; a map painter in the editor
- [x] Monsters with brains that take cover, flank, hold and fall back, throw grenades and lay
      mines, in squads that share what they see - packs that swarm, sweeps, ambushes, assaults;
      open land and dungeons without end; saves that hold a level's state
- [x] Arcade stages in real time: platformers (jumps, platforms, ladders, doors and keys,
      checkpoints) and top-down chases, enemies that walk, hop, fly, hunt and shoot, drawn in
      half-block pixels; a bot that proves each stage can be cleared
- [x] Real-time strategy: skirmishes with workers, two resources, buildings, training, upgrades
      and tech, armies on flow fields, fliers and transports, control groups, fog of war, a
      computer player that builds, researches and attacks in waves; keys and the mouse; orders
      kept by tick, so a game plays back (the base for lockstep multiplayer)
- [x] Simulators: cars, boats, a hopper and planes in fixed steps over a map, instruments,
      fuel and systems as data (formulas), checkpoints and landings; systems sims with controls
      and charts; an autopilot that proves each one can be done
- [x] Save / load of the *whole* world, named slots
- [x] Three demo games, a starter template, over two hundred automated tests
- [x] Game editor in the browser: `python clio.py mygame --edit`, or
      [on the web](https://eryxgames.github.io/CLIo/) with nothing installed - forms for
      everything a game is made of, the map, conversations as graphs, all text as a
      table, an enemy workshop, a sprite editor, and a check that the game can be finished
- [ ] The older entity data editor (`utils/entity_editor.py`, Tkinter, desktop only - still alpha and
      still edits the CLIo 1 file layout in `game_files/`; its Project Map needs
      `pip install graphviz pillow` plus the Graphviz program)

## Running it

```
python clio.py [game] [options]

  --list          list the games
  --style NAME    default, elegant, minimal, modern, retro, techno, console
  --no-sound      run silently
  --sounds SET    another set of sound effects (rootless: ballistic, which needs Node.js or baked takes)
  --get-ballistic install Ballistic's C engine for this machine in your data folder (renders without Node.js)
  --get-picture   install CLIo Picture, a C library that draws the land, the sky, rooms and dots faster
  --import-model F  bring a glTF model (.glb/.gltf, e.g. from Blender) into a game's models.json
  --no-color      plain text
  --ascii         no box-drawing or block characters
  --glyphs MODE   full, safe (frames stay, symbols become plain) or ascii
  --test-display  draw a test page: frames, symbols, colours, a sprite
  --no-art        hide ASCII art and sprites
  --fast          no text animation
  --width N       force the layout width
  --seed N        reproducible random numbers (same seed, same dungeon)
  --mode NAME     game mode, for games that have several (depths: story, rogue)
  --view STYLE    how first-person levels are drawn: pixel, dots, dots-fill
  --detail D      first-person levels: low draws the floor at half width (faster), auto (default), high
  --lines         in a level, every command is typed and ended with Enter (no single keys)
  --realtime [S]  levels in real time: a beat passes every S seconds (0.8) when no key acts
  --keys          show how your terminal reports keys to games in real time (held, let go)
  --level ID      start a new game in first-person level (or arcade stage, skirmish or sim) ID
                  (rootless: e1m1, e1m2, e1m3, e1m4, e1m9, sim1, sim2, sim3, sim4; stages sim5, sim6;
                  skirmish sim7; sims sim8, sim9)
  --dev           for making games: *ID in a level jumps to level ID, saves are not counted
  --scroll        play levels in scrolling text instead of a redrawn picture
  --check         validate a game's data files and exit
  --looks         list the logos, banner styles, palettes and animations
  --logo NAME     the logo the launcher shows (or CLIO_LOGO=NAME); --effect NAME animates it
  --banner TEXT   draw TEXT in a style (--banner-style, --palette, --effect) or
                  write it as an .art file (--export FILE)
  --edit          open the game in the editor, a page in your browser
  --sheet WHAT    the game's pictures on one PNG with an atlas: monsters, sprites, tiles
                  (--scale N, --export FILE); --import-sheet FILE takes one back, edited
  --export-text F write every line a player can read to a CSV file
  --import-text F put the texts of such a file back into the game
```

`python main.py` still works, as in CLIo 1.

### On a phone (Termux)

```
pkg install python git
git clone https://github.com/eryxgames/CLIo && cd CLIo
python clio.py
```

For sound, install any one player: `pkg install play-audio` (recommended) or `pkg install mpv`.
Without one the game is simply silent; the in-game `sound` command tells you what it found.

The layout follows the screen: it is tested from 24 columns up, and re-measures the
terminal on every line, so rotating the phone or pinching to zoom just works. Art that
does not fit is swapped for a smaller version or left out. To check a particular phone
and font, run

```
python clio.py --test-display
```

and follow what it says. If a symbol shows as a box or a little picture, add
`--glyphs safe` (or `export CLIO_GLYPHS=safe` in `~/.bashrc`).

### Sound on other systems

CLIo renders its own audio and hands the result to a player that is already on the machine:

| System | Used automatically |
| --- | --- |
| Linux | `pw-play` (PipeWire), `paplay` (PulseAudio), `aplay` (ALSA), or `mpv` / `ffplay` / `sox` / `vlc` |
| macOS | `afplay` |
| Windows | the built-in multimedia API (no extra software) |
| Any | `pygame`, if it happens to be installed - never required |

Set `CLIO_AUDIO=off` for silence, `CLIO_AUDIO=mpv` to force one player, or
`CLIO_AUDIO="myplayer --flag {file}"` for anything else.

## Playing

```
look            examine locker       take wire        take all        inventory (i)
go north / n    go storage door      exit             back            map (m)
open crate      unlock locker        use relay on reactor             read log
talk to bolt    give apple to bugrat fight droid      trade
combine goo with suit   repair chip  equip cutter     journal (j)     stats
save / load     hint    help         style retro      music off       volume 40
speed fast      art off again (g)    records          quit
```

Saved games live outside the game folder: `%APPDATA%\clio\saves` on Windows,
`~/.local/share/clio/saves` elsewhere (set `CLIO_SAVES` to move them).

In a fight the enemy shows what it is about to do. **Guard** when a heavy blow is coming,
**strike** while it winds up, **focus** while it braces. Against a group, add a number to
aim: `strike 2`. Ctrl-C skips an animation.

A game can offer several modes. In The Hollow, **Story** is three floors with a save
at every stair; **Rogue** is one life in a dungeon without a bottom. A rogue run is saved
as you go and waits for you when you quit, but there is no loading back, and the save is
erased when you fall. `records` shows the best runs.

## Making a game

A game is a folder under `games/` with a `game.json` and a few data files. The shortest
useful game is about thirty lines of JSON: copy `templates/starter/` to `games/yourgame/`
and edit it - by hand, or with `python clio.py yourgame --edit`. See **[docs/AUTHORING.md](docs/AUTHORING.md)** for
the full reference: scenes, items, characters, dialogue trees, quests, conditions and
effects, art files, sprites, music notation, themes and the dungeon generator.

Games written for CLIo 1 (`config.json` + scenes / items / characters / story texts) load as
they are. See "Coming from CLIo 1" in the authoring guide for the handful of differences.

## Project layout

```
clio.py              launcher
engine/
  term.py            terminal detection, colour, markup, wrapping
  ui.py              frames, panels, menus, HUD, text effects
  theme.py           themes (files in engine/style/configs/)
  art.py             ASCII art files          sprite.py   pixel sprites
  banner.py          text in graphic styles   fx.py       art animation
  automap.py         auto-map                 maze.py     dungeon generator
  audio/             synth, composer, sound effects, playback backends
    ballistic/       Ballistic Foley Lab's sound engine (Node.js, or its C engine: --get-ballistic)
  picture/           CLIo Picture: the land, the sky, rooms' floors and the dots in C, when installed
  data.py            loading and normalising game files
  world.py           game state, save/load
  parser.py          command parser           actions.py  the verbs
  conditions.py      conditions and effects   quests.py   dialogue.py   combat.py
  game.py            the turn loop
  level.py           first-person levels      firstperson.py  the view
  model.py           3D models in levels      gltf.py     glTF from Blender
  frame.py  keys.py  the redrawn screen and single keys
games/               derelict/  depths/  rootless/
templates/starter/   a tiny complete game to copy (Apache-2.0)
game_files/          the original CLIo 1 sandbox
tests/               python -m unittest discover -s tests
utils/               Tkinter data editor (desktop, alpha)
index.html, .nojekyll   the editor as a web site (GitHub Pages serves the repository as it is)
legacy/prototypes/   early dialogue / crafting experiments from CLIo 1
```

## Changes

See [CHANGELOG.md](CHANGELOG.md).

## Tests

```
python -m unittest discover -s tests     # 600 tests, about a minute
python tests/bot.py 30                   # an automatic player runs the dungeon 30x per class
python tests/bot.py 30 rogue             # the same in rogue mode: how deep does it get
python tests/bot.py 30 cards             # the same with card battles (the Deck mode)
python tests/levelbot.py 10              # an automatic player walks Rootless's E1M1 ten times
python tests/levelbot.py 10 rootless e1m9  # ...and its secret level
python tests/levelbot.py 10 rootless e1m2  # ...and E1M2, the loader and all
python tests/levelbot.py 10 rootless e1m3  # ...and E1M3, out over the swamp
python tests/levelbot.py 10 rootless e1m4  # ...and E1M4, across the fens to the mast
python tests/levelbot.py 10 rootless sim1  # ...and the Simulatron's fens without end (also sim2, sim3)
python tests/levelbot.py 10 rootless sim4  # ...and the Kill House, a room for each kind of squad
```

The tests play the adventure and the dungeon to every ending from scripts, walk Rootless's
levels to their exits (key presses in a redrawn screen and typed commands), check that every screen fits
40 columns in both Unicode and ASCII (and down to 24), fight packs, run rogue mode until
the bot falls, round-trip saves, and render every sound effect. They write nothing into the repository: saves and audio go to temporary folders.

## Releasing

Raise `__version__` in `engine/__init__.py`, add a `## x.y.z - date` section to
`CHANGELOG.md`, then push a tag: `git tag -a vx.y.z -m "CLIo x.y.z" && git push origin vx.y.z`.
The release workflow (`.github/workflows/release.yml`) runs the tests, makes the GitHub release
with those notes (each paragraph joined onto one line, as GitHub keeps line breaks in release
notes), the engine as a zip and the editor's web pack, and pushes both to itch.io
(channels `win-linux-mac` and `html5`). It needs the repository secret `BUTLER_API_KEY`
(itch.io → Settings → API keys, the key whose source is wharf); without it the itch.io step is
skipped.

## Licence

CLIo is open source so that anyone can make games with it, including games they sell.

| Part | Licence |
| --- | --- |
| The engine: `engine/`, `clio.py`, `tests/`, `utils/`, `docs/` | [Apache-2.0](LICENSE) |
| Everything the engine ships for games to use: the themes, the built-in sound effects, the music composer, the sprite generator, the CLIo logo art | Apache-2.0 - reuse and edit freely |
| `templates/starter/` and the sandbox in `game_files/` | Apache-2.0 - copy them as a starting point |
| The demo games `games/derelict/`, `games/depths/` and `games/rootless/` (story, text, characters, art, sprites, levels, music) | Copyright Daniel Sandner, all rights reserved - see the `LICENSE.md` in each folder |

**What you make is yours.** A game you write for CLIo is your own work under whatever
terms you choose, and so are the music, sound effects and sprites the engine generates
for it. If you ship the engine with your game, keep the `LICENSE` and `NOTICE` files with
it and say if you changed the engine; that is all Apache-2.0 asks.

Copyright 2024-2026 Daniel Sandner.
