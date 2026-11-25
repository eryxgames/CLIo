# CLIo

**Games in your terminal.** A first-person shooter drawn in pixel blocks, a dungeon crawler that
is new on every run, a sci-fi adventure - with chiptune music, all in a text window. CLIo runs on
Linux, macOS, Windows and Android phones (Termux), and needs nothing but Python.

Created by **Daniel Sandner** · [eryxian.com](https://eryxian.com)

## Play in a minute

1. **Get Python 3.8 or newer.** It is already on Linux and macOS (`python3 --version`). On
   Windows, get it from [python.org](https://www.python.org/downloads/) (tick "Add python.exe
   to PATH"). On an Android phone, see [On a phone](#on-a-phone-termux).
2. **Get CLIo.** Download the zip of the latest release from the
   [Releases page](https://github.com/eryxgames/CLIo/releases) and unpack it - or
   `git clone https://github.com/eryxgames/CLIo`.
3. **Play.** In a terminal, in the CLIo folder:

```
python clio.py            # choose a game from the list (python3 on some systems, py on Windows)
python clio.py rootless   # or go straight to one
```

There is nothing to install: no packages, no accounts. Saves stay on your machine.

**Or play in your browser**, with nothing at all to install:
[eryxgames.github.io/CLIo](https://eryxgames.github.io/CLIo/) (and on the game's itch.io page).
The same engine runs there in Python made for the web: the first visit fetches about 12 MB,
saves stay in that browser, and on a phone you tap and swipe the picture (keys are under it too).
It is slower than a terminal: Python made for the web runs at about half the speed, and the
browser cannot use CLIo Picture, so a lit level such as E1M8 takes about 130 ms a picture on a
desktop where a terminal with CLIo Picture takes about 8 - and a phone is slower still. It has no
downloads (CLIo Picture, Ballistic's sounds); every game and the tech demo play.

## The games

| Game | What it is |
| --- | --- |
| **RØØTLESS** (`rootless`) | A first-person shooter drawn in the terminal, a beat at a time: you step, the monsters step. A recruit's battle simulation: **E1M1** *Boot Sector*, **E1M2** *Dynamic Loader* (ride a cargo loader across the acid), **E1M3** *Drone Refit Assembly*, **E1M4** *Xantrium Fens* (open land to the horizon, a hopper to fly), **E1M5** *User Space* (lockers, supply crates, force fields, a race through a door that will not stay open), **E1M6** *Kernel Space* (a hall of many floors, drawn in the mesh view: a gallery a storey up, the scheduler's dais, the interrupt well), **E1M7** *The Stack* (magboots on the ceiling, upside down over the overflow), **E1M8** *Aspiration Central* (up a building's face and a broken lift shaft to the Metacron) and a secret level. Shotguns, chainsaws, rockets, grenades that bounce, drones in 3D, barrels, crates, oil that burns, keys, secrets to punch and shoot - and Cron, who rains fire on a schedule. |
| **The Hollow** (`depths`) | A dungeon crawler that is different every time: three classes, tactical fights where every enemy shows what it is about to do, loot, shrines, a peddler. **Rogue mode** (`--mode rogue`): one life, no bottom, a table of the best runs. **Deck mode** (`--mode cards`): every fight is a card battle. |
| **Derelict** (`derelict`) | A short sci-fi text adventure aboard an abandoned cargo hauler: puzzles, conversations, a fight that can be talked around, three endings. |
| **Erebus: Last Watch** (`erebus`) | The terminals demo: the last watch aboard a cargo hauler, on five consoles opened from a wheel of orders - wake the core, scan for a place to land and leave a beacon, open the bay, fly the lander through the drift and set it down. Panels, scopes, scans, models that move as values say; the autopilot can do each console (`python -m engine.sim games/erebus`). |
| **Tech demo** | `python clio.py --demo`: CLIo shows what it can do, by itself. Any key goes back. |

RØØTLESS also has a **simulatron** of training programs, each its own kind of game. Start one
with `python clio.py rootless --level ID`:

| ID | Program |
| --- | --- |
| `sim1` `sim2` `sim3` | Long Fens, Deep Swap, Swap Sprawl: open land, floors and rooms without end, new each run |
| `sim4` | Kill House: a room for each kind of squad |
| `sim5` | Bus Run: a platformer, side on, in real time |
| `sim6` | Purge: an arcade shooter from above |
| `sim7` | Xantrium Rush: real-time strategy |
| `sim8` | Fen Hopper: a flight simulator |
| `sim9` | Coolant Loop: keep a reactor's systems in bounds |
| `sim10` | Root Shell: hacking, as card duels |
| `sim11` | Deep Works: magboots, stairs, a jetpack, diving, a submarine |
| `sim12` | Stairwell: real stairs, a mezzanine and a pit, drawn as a mesh |

Each game has a demo that plays itself: `python clio.py rootless --demo`. Left alone on the
title screen or the launcher, the demos start by themselves.

## Controls

### RØØTLESS (first-person levels)

| Key | Does |
| --- | --- |
| ↑ ↓ | step forward, back |
| ← → | turn |
| Ctrl+← →, or `,` `.` | strafe (sidestep) |
| Space | fire |
| Enter | open, press, use - or just walk into a door, a locker or a switch |
| Tab | the map |
| 1 - 7, `]` | weapons; the next weapon |
| F2 | TTY goggles on/off |
| F3, F4, F6 | magboots, jetpack, dive / surface |
| F5, F9 | save (three times a level), load the last save |
| `?` | help |

Typed commands work too, joined as in a shell: `f z1 && w || h` fires at z1, then waits or
backs off. On a phone the picture answers taps (see below).

### The adventure and the dungeon

```
look            examine locker       take wire        take all        inventory (i)
go north / n    go storage door      exit             back            map (m)
open crate      unlock locker        use relay on reactor             read log
talk to bolt    give apple to bugrat fight droid      trade
combine goo with suit   repair chip  equip cutter     journal (j)     stats
save / load     hint    help         style retro      music off       volume 40
speed fast      art off again (g)    records          quit
```

In a fight the enemy shows what it is about to do. **Guard** when a heavy blow is coming,
**strike** while it winds up, **focus** while it braces. Against a group, add a number to aim:
`strike 2`. Ctrl-C skips an animation.

The Hollow's **Story** mode is three floors with a save at every stair; in **Rogue** mode a run
is saved as you go and waits for you when you quit, but there is no loading back, and the save is
erased when you fall. `records` shows the best runs.

## Sound, and faster pictures

CLIo makes its own music and sound effects and hands them to a player already on your machine:

| System | Used automatically |
| --- | --- |
| Linux | `pw-play` (PipeWire), `paplay` (PulseAudio), `aplay` (ALSA), or `mpv` / `ffplay` / `sox` / `vlc` |
| macOS | `afplay` |
| Windows | the built-in multimedia API (no extra software) |
| Android (Termux) | `pkg install play-audio` (or `mpv`) |

Without one, a game is simply silent; the in-game `sound` command says what it found.
`--no-sound` (or `CLIO_AUDIO=off`) turns it off.

Two **optional downloads** make RØØTLESS nicer. The launcher offers them under **Downloads**
(it says the size first and installs nothing without a yes):

- **CLIo Picture** (about 50 KB, `--get-picture`): draws the first-person picture several times
  faster - the same picture, to the last pixel - and, from its release 0.10, the consoles' line
  displays, scans and views ahead.
- **Ballistic's C engine** (about 1 MB, `--get-ballistic`): physically modelled shots, ricochets
  and blasts for RØØTLESS's Ballistic sound set (`--sounds ballistic`) - some of them; with
  [Node.js](https://nodejs.org) installed, all of them.

Both are checked against their published checksums and go into your user data folder, not into
CLIo's.

## Looks

- `--view dots` draws RØØTLESS in braille dots (finer, on a terminal font that has them).
- `--render mesh` draws RØØTLESS's rooms in a true perspective, as its open land is drawn
  (`--render classic`: the old way). There Shift+Up and Shift+Down look up and down (`look`
  looks ahead again), and a turn is drawn as one. E1M6 and SIM-12 are always drawn this way.
- `--style retro` (or elegant, minimal, modern, techno, console) changes the frames and colours.
- `--test-display` draws a test page: run it if something looks wrong. If a symbol shows as a
  box, add `--glyphs safe` (or set `CLIO_GLYPHS=safe`).
- On **Windows**, Windows Terminal (its Cascadia font) shows everything; in the old console
  window CLIo keeps to the symbols Consolas has.
- The layout follows the window: from 24 columns on a phone to a wide desktop terminal.
  Rotate, resize or zoom whenever you like.

## On a phone (Termux)

Install [Termux](https://termux.dev) (from F-Droid or GitHub), then:

```
pkg install python git play-audio
git clone https://github.com/eryxgames/CLIo && cd CLIo
python clio.py
```

In RØØTLESS the picture answers taps: its left and right thirds turn, their bottom corners
strafe, the top of the middle steps forward, the centre fires and the bottom opens. Swipe up or
down to step forward or back; tap the status line for the next weapon, or under the picture for
the map. For a row of game keys above the keyboard, run `python clio.py --termux-keys` and follow
what it prints. `--touch off` turns the taps off (so text can be selected again).

On a phone, the launcher's **Downloads** are worth it: CLIo Picture makes RØØTLESS much smoother.

## Saves

Saved games live outside the game folder: `%APPDATA%\clio\saves` on Windows,
`~/.local/share/clio/saves` elsewhere (set `CLIO_SAVES` to move them). In RØØTLESS, F5 saves
(three times a level) and each level saves itself as it starts; `Continue` on the title screen
picks up where you were.

## All the options

```
python clio.py [game] [options]

  --list          list the games
  --demo          play the game's demo (or, with no game named, CLIo's tech demo) and exit
  --attract       the same, over and over until a key
  --level ID      start a new game in a first-person level (or arcade stage, skirmish or sim)
                  (rootless: e1m1 ... e1m9, sim1 ... sim12)
  --mode NAME     game mode, for games that have several (depths: story, rogue, cards)
  --seed N        reproducible random numbers (same seed, same dungeon)
  --style NAME    default, elegant, minimal, modern, retro, techno, console
  --view STYLE    how first-person levels are drawn: pixel, dots, dots-fill
  --detail D      first-person levels: low draws the floor at half width (faster), auto (default), high
  --realtime [S]  levels in real time: a beat passes every S seconds (0.8) when no key acts
  --no-sound      run silently
  --sounds SET    another set of sound effects (rootless: ballistic)
  --get-picture   install CLIo Picture for this machine (faster first-person pictures)
  --shots DIR     draw the game's consoles, menus and models into DIR without playing it
  --add KIND NAME paste a working console, menu or model into the game (--add console list)
  --schema DIR    write JSON Schemas of the data files, for key completion in your editor
  --get-ballistic install Ballistic's C engine for this machine (sounds without Node.js)
  --touch on|off  taps and swipes in first-person levels (on in Termux)
  --termux-keys   print a row of extra keys for Termux that plays the levels
  --no-color      plain text
  --ascii         no box-drawing or block characters
  --glyphs MODE   full, console (the old Windows console fonts; the default in that window),
                  safe (frames stay, symbols become plain) or ascii
  --test-display  draw a test page: frames, symbols, colours, a sprite
  --no-art        hide ASCII art and sprites
  --fast          no text animation
  --width N       force the layout width
  --lines         in a level, every command is typed and ended with Enter (no single keys)
  --scroll        play levels in scrolling text instead of a redrawn picture
  --keys          show how your terminal reports keys to games in real time (held, let go)

For making games:
  --edit          open the game in the editor, a page in your browser
  --check         validate a game's data files and exit
  --dev           *ID in a level jumps to level ID, saves are not counted
  --import-model F  bring a glTF model (.glb/.gltf, e.g. from Blender) into a game's models.json
  --sheet WHAT    the game's pictures on one PNG with an atlas: monsters, sprites, tiles
                  (--scale N, --export FILE); --import-sheet FILE takes one back, edited
  --export-text F write every line a player can read to a CSV file
  --import-text F put the texts of such a file back into the game
  --bake-sounds SET  render a set's Ballistic sounds into the game as WAV files
  --looks         list the logos, banner styles, palettes and animations
  --logo NAME     the logo the launcher shows (or CLIO_LOGO=NAME); --effect NAME animates it
  --banner TEXT   draw TEXT in a style (--banner-style, --palette, --effect) or
                  write it as an .art file (--export FILE)
```

## Make your own game

A game is a folder of JSON files under `games/`. Copy `templates/starter/` (an adventure) or
`templates/realm/` (strategy by turns: a village through its seasons) or `templates/station/` (a
ship's bridge: three simulators, each with a screen of panels) to `games/yourgame/` and edit it - by hand, or in the editor in your browser: `python clio.py yourgame --edit` (also
[on the web](https://eryxgames.github.io/CLIo/), with nothing installed). The guide is
**[docs/AUTHORING.md](docs/AUTHORING.md)**: scenes, items, characters, conversations, quests,
first-person levels, monsters, realms, music, art. Working on the engine itself:
**[docs/DEVELOPING.md](docs/DEVELOPING.md)**. What changed: [CHANGELOG.md](CHANGELOG.md). For consoles and terminals there is also a cookbook, a task a page:
**[docs/COOKBOOK.md](docs/COOKBOOK.md)**.

## Licence

CLIo is open source so that anyone can make games with it, including games they sell.

| Part | Licence |
| --- | --- |
| The engine: `engine/`, `clio.py`, `tests/`, `utils/`, `docs/` | [Apache-2.0](LICENSE) |
| Everything the engine ships for games to use: the themes, the built-in sound effects, the music composer, the sprite generator, the CLIo logo art | Apache-2.0 - reuse and edit freely |
| `templates/starter/`, `templates/realm/`, `templates/station/`, the terminals demo `games/erebus/` and the sandbox in `game_files/` | Apache-2.0 - copy them as a starting point |
| The demo games `games/derelict/`, `games/depths/` and `games/rootless/` (story, text, characters, art, sprites, levels, music) | Copyright Daniel Sandner, all rights reserved - see the `LICENSE.md` in each folder |

**What you make is yours.** A game you write for CLIo is your own work under whatever
terms you choose, and so are the music, sound effects and sprites the engine generates
for it. If you ship the engine with your game, keep the `LICENSE` and `NOTICE` files with
it and say if you changed the engine; that is all Apache-2.0 asks.

Copyright 2024-2026 Daniel Sandner.
