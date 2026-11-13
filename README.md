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
```

## The demo games

| Game | What it shows |
| --- | --- |
| **Derelict** (`games/derelict`) | A complete short adventure aboard an abandoned cargo hauler. Puzzles, dialogue trees, quests, a wandering NPC, one tactical fight that can also be talked around, and three endings. |
| **The Hollow Depths** (`games/depths`) | A dungeon crawler that is different on every run: three generated floors, three character classes, tactical combat, loot, shrines, a peddler, generated monster sprites and generated music. `--seed 7` replays the same dungeon. |
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
- [x] Character generator (name and class at the start of a game)
- [x] Sounds and music: synthesizer, generative composer, optional audio files
- [x] Styling: seven themes, frames, typewriter / fade / glitch effects, HUD
- [x] ASCII art with colour masks, half-block pixel sprites, procedural sprites
- [x] Auto-map
- [x] Generative maze
- [x] Save / load of the *whole* world, named slots
- [x] Two demo games, a starter template, 47 automated tests
- [ ] Entity data editor (`utils/entity_editor.py`, Tkinter, desktop only - still alpha and
      still edits the CLIo 1 file layout in `game_files/`; its Project Map needs
      `pip install graphviz pillow` plus the Graphviz program)

## Running it

```
python clio.py [game] [options]

  --list          list the games
  --style NAME    default, elegant, minimal, modern, retro, techno, console
  --no-sound      run silently
  --no-color      plain text
  --ascii         no box-drawing or block characters
  --no-art        hide ASCII art and sprites
  --fast          no text animation
  --width N       force the layout width
  --seed N        reproducible random numbers (same seed, same dungeon)
  --check         validate a game's data files and exit
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
speed fast      art off again (g)    quit
```

In a fight the enemy shows what it is about to do. **Guard** when a heavy blow is coming,
**strike** while it winds up, **focus** while it braces. Ctrl-C skips an animation.

## Making a game

A game is a folder under `games/` with a `game.json` and a few data files. The shortest
useful game is about thirty lines of JSON: copy `templates/starter/` to `games/yourgame/`
and edit it. See **[docs/AUTHORING.md](docs/AUTHORING.md)** for
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
  automap.py         auto-map                 maze.py     dungeon generator
  audio/             synth, composer, sound effects, playback backends
  data.py            loading and normalising game files
  world.py           game state, save/load
  parser.py          command parser           actions.py  the verbs
  conditions.py      conditions and effects   quests.py   dialogue.py   combat.py
  game.py            the turn loop
games/               derelict/  depths/
templates/starter/   a tiny complete game to copy (Apache-2.0)
game_files/          the original CLIo 1 sandbox
tests/               python -m unittest discover -s tests
utils/               Tkinter data editor (desktop, alpha)
legacy/prototypes/   early dialogue / crafting experiments from CLIo 1
```

## Tests

```
python -m unittest discover -s tests     # 47 tests, about ten seconds
python tests/bot.py 30                   # an automatic player runs the dungeon 30x per class
```

The tests play both demo games to every ending from scripts, check that every screen fits
40 columns in both Unicode and ASCII, round-trip saves, and render every sound effect.

## Licence

CLIo is open source so that anyone can make games with it, including games they sell.

| Part | Licence |
| --- | --- |
| The engine: `engine/`, `clio.py`, `tests/`, `utils/`, `docs/` | [Apache-2.0](LICENSE) |
| Everything the engine ships for games to use: the themes, the built-in sound effects, the music composer, the sprite generator, the CLIo logo art | Apache-2.0 - reuse and edit freely |
| `templates/starter/` and the sandbox in `game_files/` | Apache-2.0 - copy them as a starting point |
| The demo games `games/derelict/` and `games/depths/` (story, text, characters, art, sprites, music) | Copyright Daniel Sandner, all rights reserved - see the `LICENSE.md` in each folder |

**What you make is yours.** A game you write for CLIo is your own work under whatever
terms you choose, and so are the music, sound effects and sprites the engine generates
for it. If you ship the engine with your game, keep the `LICENSE` and `NOTICE` files with
it and say if you changed the engine; that is all Apache-2.0 asks.

Copyright 2024-2026 Daniel Sandner.
