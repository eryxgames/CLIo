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
- **Floors and fire**: slick floor (`;`, `"slick"`) - the player, a pushed crate or a
  rolled barrel slides on until something stops it, picking up what it passes; oil (`:`,
  `"oil"`), slick and burning - fire runs along it a cell a beat and leaves it scorched;
  fire that stays a few beats on a cell and hurts what stands in it (`fire_damage`), set
  off by blasts, flamethrowers and monsters whose tanks burst; belts (`"conveyor": "e"`)
  that move the player, crates, barrels, monsters and items a cell a beat. Barrels roll
  when walked into. Monsters take teleporters, and count a pad as a step on their way.
- **New kinds of attack**: `flame` (levels its nozzle, then sprays fire three cells along
  a row or a column), `spinup` (a minigun that spins up for beats, then fires every beat
  while it sees you), `move_every` (heavy monsters that move every other beat), `dodge`
  (a chance to sidestep a shot seen coming) and `burst_fire` (a death that burns).
- **A secret exit**: `{"exit": "secret"}` runs the scene's `on_secret_exit` instead of
  `on_level_exit`.
- **Monsters that walk and aim**: while a monster moves it shows its steps - made by the
  engine from its standing picture, or drawn (`"walk"`); while it takes aim and fires,
  its `"attack"` picture; its shots flash at its `"muzzle"`.
- **Melee weapons**: one key can hold several weapons (`"key"`; pressed again, the next
  on it; a weapon can also be typed by its id). Melee options `accuracy`, `shove` (throws
  the target back) and `stagger` (a bitten monster loses its turn); `ready_sound`.
- **An end screen** (`"end_screen"` in game.json): a won game of levels ends on a screen
  of its own - banner, pictures (side by side, or taking turns: `picture_every`; as big as
  `picture_lines`), the totals counting up, the ending, what comes next, credits and a
  crontab line still ticking. In the editor it is part of the Game form, drawn as the
  game draws it.
- **Sheets of pictures**: the monsters with their steps and attack, every sprite, or the
  tiles, on one PNG with an atlas (JSON, the form many engines read) - from the editor
  (*A sheet of pictures…*) or `--sheet monsters|sprites|tiles` (`--scale`, `--export`).
  The PNG is written with the standard library.
- **The way back**: an edited sheet is taken back in (the sheet panel, or
  `--import-sheet FILE.png`): only the pictures painted over, checked against the atlas,
  with new colours added to the palettes - a monster's steps and attack too, an engine
  tile becoming the game's own. **From a picture** in the sprite and tile editors makes a
  drawing of any picture file: a pixel picture drawn bigger back to its own pixels, made
  smaller, its colours fewer, its background cleared (the commonest edge colour, or a
  click), dust swept away, an outline if wanted. PNG files are read with the standard
  library (every colour type and depth; not interlaced).
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
  of the whole game (the flag `cron_escaped`); the exit is a lift down. A secret exit in
  the goggles' closet leads to E1M9 *Swap Partition*: a belt hall running into acid, an
  oil depot guarded by flamethrowers, a coolant room of slick floor with a crate puzzle,
  and a minigun holding the exit. Five new enemies - shred (flamethrower), kworker
  (dodging gunner), kswapd (heavy gunner), crawler (fast, three red eyes), spinlock
  (minigun) - drawn in the game's own style; the recruit, the game's hero; and two helmet
  portraits (his, and a hazmat mask) taking turns on the end screen. A shovel (E1M1) and a chainsaw (E1M9's closet) share key 1 with the fist. The
  story is framed: a recruit of the Terran Ascendancy Mandate in a simulator pod, his
  first battle simulation. Two riffs, sounds (chip and Ballistic), 41 sprites, a tile.
- `--view STYLE`, `--lines` (every command typed, no single keys), `--scroll`.
  `--check` also counts levels and monsters, and checks their maps and references.
- `engine/levelbot.py`: a simple player that walks a level by its `"bot"` goals - if it can
  finish, a person can (`python tests/levelbot.py`, and in the editor). It plans slides,
  keeps off fire, steps out of a flamethrower's line and ducks a spun-up minigun. 94 more
  tests.
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

- **TTY goggles on and off**: F2, or `goggles [on|off]` typed (`nv` for short), puts them
  on or takes them off, free as turning is. Their battery runs down only while they are on;
  the line under the picture says `goggles: 12` or `goggles off: 12`, and warns at 5.
- **`detail`** (`--detail auto|high|low`, or `"detail"` in game.json's `first_person`):
  `low` draws a level's floor and ceiling at half width - half their work, which is most of a
  frame - and `auto`, the default, does so only for a very big picture (the goggles' dots in
  a wide window).
- **Rockets and grenades** (weapon kinds `rocket` and `grenade`): a rocket flies the line to
  its target and bursts on what it meets; a grenade is thrown a few cells ahead, bounces back
  off walls, slides on slick floor, rides belts and goes off a beat later. Their **blast** is
  a barrel's - everything within a cell, the player too, thrown back, oil set alight - and
  leaves the floor scorched; grenades next to a blast go off with it. Running out of bullets
  never puts an explosive in the player's hands.
- **Bullet holes**: a shot into a wall, and a shot that misses and goes on into the wall
  behind, leaves a hole in that wall's face, kept in place as the player walks round (the
  last 60 of a level).
- **Vehicles**: a monster with a `"vehicle"` block can be ridden - walk into it to climb in,
  Enter or `out` to climb down. It takes the hits instead of the player, treads on monsters,
  has a claw for a weapon, shoves heavy **containers** (`{"crate": "heavy"}`) that the
  player alone cannot move, wades through acid, fits through no door, and bursts when it is
  wrecked. The picture shows its cage and claws. The level bot can `board` and get `out`.
- **3D models in levels** (`models.json`, `engine/model.py`): a monster, vehicle or item with
  `"model"` is drawn as a low-poly model instead of a sprite - made of parts (box, wedge,
  cylinder, cone, sphere, ring: placed, sized, turned) or a mesh, with glTF's physically
  based materials (colour, metal, rough, glow) lit by a Cook-Torrance light, flat or smooth,
  in the level's fog, with a depth buffer; it faces where it went or whom it aims at, bobs,
  turns, spins groups of parts, plays imported frames (`idle`, `walk`, `attack`), and when
  destroyed breaks into shards that fly, fall and fade. About 1 ms for 200 triangles.
- **The sky over open cells** (`"sky": true` on a cell, the level's `"sky"`): a gradient,
  a sun or a banded planet, drifting clouds, stars and ridges along the horizon - the near
  ones move as the player steps sideways. Drawn once per facing and beat, behind everything.
- **Switches** (`{"switch": event, "label": "GATE"}`): a panel in a wall; Enter throws it
  and sets off the event. Thrown, its lever is up and its lamps green.
- **Balls** (monsters of `"kind": "ball"`): shoved, they roll `speed` cells a beat for
  `roll` cells, crushing what they meet (`crush`), knocking other balls on, setting barrels
  off, breaking hollow walls and rolling through, sinking in acid to make a step, holding
  plates down; shots ping off them and blasts set them rolling. Held by an event, one
  rumbles for a beat and then rolls on its cell's `"roll"` way - a cell a beat behind a
  player who must not stop. Their models turn as they roll. The level bot gets out of
  their way.
- **Machines that fly on fuel**: a vehicle with `"fly"` crosses acid and water; with
  `"fuel"` it needs fuel cells (`"pickup": {"fuel": 12}`), burns a beat of it every beat
  once it lifts, and when it runs dry comes down - `"on_empty": "exit"` ends the level. Its
  `"gun"` fires with Space and never runs dry; `"canopy"` draws a canopy frame and a
  dashboard with a fuel gauge. The status line shows the fuel.
- **`--check`** also checks balls, vehicles' fuel, guns and `on_empty`, fuel items, switches
  (something must listen to their event), `roll` on map cells and a level's `sky`; a ride
  that ends the level counts as its exit. The editor lists **3D models** (models.json),
  draws monsters and items that have a model as a small picture of it, and its map painter
  knows switches, the sky and a ball's roll.
- **A model builder in the editor** (3D models): the model in a small room as a level draws
  it, turned, broken and playing its frames, with its triangles and size; its materials
  and parts as rows to edit (shape, material, group, size, place, turn; copy, mirror, add,
  remove), and *From Blender* to take a `.glb` in. The picture follows every change.
- **Models break into their parts** (`"break": "parts"`, or `"groups"`): a drone's gun and
  plates fly off whole. An imported mesh comes apart where it is not joined.
- **A flying machine's eye is higher** (`"eye"`, 0.74 of a wall's height): more of the
  ground below, a little sway; it rises as the machine lifts off and sinks as it lands.
- **RØØTLESS's Ballistic set** has the sounds E1M3 brought: drones, the hornet swarm, the
  warden, the hopper's cannon, fans, start and stop, fuel, the rolling core, balls and
  the switch.
- **`--import-model FILE`**: glTF 2.0 (`.glb`, `.gltf`) from Blender into `models.json` -
  meshes with their placing, PBR materials, PNG textures and vertex colours as colours per
  triangle, object and skinned animations as frames (`--model-name`, `--model-scale`).
  `--check` checks models and what names them.
- **`python clio.py --get-ballistic`**: installs Ballistic's C engine for this machine - the release CLIo
  follows (0.5.0: Linux x64/arm64, macOS, Windows x64/arm64, Android), checked against the SHA-256 CLIo keeps,
  only the library with its LICENSE and NOTICE, in the user's data folder (`~/.local/share/clio/ballistic/`,
  `%APPDATA%\clio\ballistic\`, or `CLIO_DATA`) rather than CLIo's or a game's. CLIo looks for it after
  `CLIO_BALLISTIC_LIB` and `engine/audio/ballistic/lib/`; `sound` suggests it when no engine is found.
- **Saving in levels**: `save [name]` (F5), `load [name]` (F9) and `saves` in a first-person
  level. A save is the world as the level began and every line played since; loading
  builds the level again and plays them back unseen (a whole level in about a tenth of a
  second), so everything in it comes back as it was. A save notes what the level was made
  of and says when it has changed; one that no longer plays through starts the level
  again. `first_person` `"saves"` limits saves per level and `"autosave"` saves as each
  level begins (what the death menu's "Load your last save" goes back to); a cell with
  `{"savepoint": true}` is a checkpoint. The title screen names a level's save by its level
  and beat. The key reader knows F9.
- **Trying levels out**: `--level ID` starts a new game in the scene that plays a level;
  with `--dev` (or `CLIO_DEV=1`) `*ID` typed in a level goes on to that level as you are,
  `*` lists the levels, and saves are not counted.
- **RØØTLESS E1M2 *Dynamic Loader***: the cargo dock where everything the facility runs is
  loaded first - containers, a belt of crates feeding an acid channel, the w key across it,
  and a cargo loader in its bay; three secrets; the rocket launcher and grenades; its own
  music. E1M1's exit leads there, and so does the secret level's.
- **RØØTLESS E1M3 *Drone Refit Assembly***: where the facility's drones are pressed again
  out of recycled Xantrium. Balls of it to roll into the acid trough (or on to a plate that
  holds a store open), the x key at the top of an ore chute whose hatch lets a Xantrium core
  roll after you, drones in three sizes (scout, hornet swarm, warden) drawn as 3D models,
  three fuel cells, the launch controls - and the X-47B Swamp Hopper, flown out of the
  launch gate over a swamp under an alien dusk until its fuel runs out. Its own music, and
  sounds for drones, balls and the hopper. E1M2's exit leads there.
- **Open land** (`engine/land.py`, a level's `"land"`): hills, lakes and coasts made from a
  seed, drawn in true perspective to the horizon, with the level's map (a camp, a compound)
  set down on flattened ground. The ground is worked out from the coordinates, so it goes on
  past the level as far as the picture reaches. Biomes by height colour it and grow props
  (sprites or models; solid ones are in the way), landmarks stand far off and show on the
  map, `things` and `scatter` put monsters and items about it the same way every time, and
  far things fade into the haze. Deep water and cliffs stop a walker but not a drone that
  floats or a machine that flies; hills hide what is behind them; a flying machine that runs
  dry glides down to firm ground. `--check` checks a land, and the level bot crosses it.
- **RØØTLESS E1M4 *Xantrium Fens***: open country past the refit plant. Fens and lakes of
  toxic water, Xantrium crystals on the hills, a survey camp with a spare hopper and fuel
  cells, a secret on the rocks, and a relay mast to the north-east whose compound holds the
  switch that ends the simulation. Its own music. E1M3's ending leads there; it ends the demo.
- **Levels without end** (`engine/chunks.py`, a level's `"world"`): made a chunk at a time
  round the player. Monsters and items wake near him and sleep where they stand when he goes;
  what changed in a chunk is kept for when he comes back, untouched chunks are forgotten and
  made again the same, and far cells are let go, so a long way keeps little. Two kinds: open
  land without end, with sites (small maps) at fixed places and by chance, and spawns per
  chunk by biome and distance; and dungeons without end, a room to a chunk, deeper the
  further one goes. The same seed makes the same world, `"seed": "run"` a new one each game,
  and saves play back the same.
- **Dungeon floors from a seed** (`engine/levelgen.py`, a level's `"generate"`): rooms,
  corridors, doors, the exit in the room furthest from the start, behind a locked door with
  its key where one can reach it, a secret closet, acid pools, rooms in their own walls, and
  monsters and items by depth - from a game variable, so a scene can go down a floor at a time.
- RØØTLESS: three free programs of the simulatron, made new each run - **SIM-1 Long Fens**
  (the fens without end: camps, ruins, hopper pads and shrines by chance, the relay mast 230
  cells off), **SIM-2 Deep Swap** (floor after floor, each worse) and **SIM-3 Swap Sprawl**
  (rooms without end). `--level sim1`, `sim2`, `sim3`; the demo's last page says so.
- The level bot plans its way in a window round itself in a world without end, keeps out of
  acid unless booted, and picks up what helps on a long way.
- **Saves hold the level's state** (`engine/snapshot.py`). Loading puts it back on the level
  built afresh instead of playing every line again: 0.05 s rather than seconds for a long
  game. The snapshot's digest is checked on loading, and the level plays on exactly as
  before. Nothing is listed as "to save": every part of a level is kept unless it is made
  again when the level is built. Tests snapshot every kind of level half way through,
  play the rest on both copies and compare, and compare the digest across processes, so
  two machines can check they agree (the ground for multiplayer).
- Lines are kept with the beat they were played on. A save asked for during a line is made
  when the line is done (whole beats). Saves keep the last 20000 lines, and old saves
  still load.
- Saves are written whole (flushed to the disk, then put in place) and the one before is
  kept as `.bak`, which loading falls back on if a save is damaged. A rogue run's death
  removes both.
- **Brains** (`engine/ai/brain.py`, a monster's `"brain"`): a monster that weighs, each beat,
  coming at the player, keeping its distance, taking cover and leaning out to shoot, working
  round to his side, falling back when hurt, holding, or searching where he was last seen -
  by how hurt it is, whether he sees it, how far he is and how many friends are near. It only
  knows where he is while it sees or hears him, and only shoots what it sees. Five presets
  (`brute`, `skirmisher`, `soldier`, `heavy`, `coward`) and weights of one's own; `ps` shows
  what each is doing and the manual page how it fights. Monsters without a brain play as before.
- **Squads** (`engine/ai/squad.py`, a level's `"squads"`, `"squad"` in the legend): monsters
  that share what they see, wake each other, follow the strongest, and take parts by the
  squad's tactic - `pincer`, `fire_team`, `hold` (guards by their posts until he comes near)
  and `rush`. `"auto"` squads the brainy monsters that stand near each other; in a world
  without end squads are made a chunk at a time, and spawns can come in packs.
- **A search for games of moves** (`engine/ai/search.py`): minimax with alpha-beta and Monte
  Carlo tree search, stopped by a budget of positions, not by time, and rounding the same on
  every machine - for duels and cards to come.
- RØØTLESS's monsters have brains (kworkers take cover, scouts and orphans flank, wardens and
  minigunners hold their lines, crawlers come at you); its levels make squads of those that
  stand together, E1M4's two relay wardens guard their compound, and SIM-1's scouts and
  kworkers come in pairs.
- The level bot steps out of the line of a gun that takes aim when it is hurt or the gun is
  far, keeps further from acid the more hurt it is, and looks further round when a lake is
  in its way.
- **Tactics that pay.** Cover: a shot at someone beside a wall, crate or closed door that the
  line of fire grazes hits the cover half the time - the player's shots and the monsters' alike;
  walls along a corridor are no cover, the corner one leans out from is. Crossfire: a squad's
  gun is surer for each other gun of the squad on him from another side. Monsters can carry
  `"grenades"` (thrown at one in cover or out of sight, never on their own, three beats to get
  out) and `"mines"` (laid unseen in doorways and by the cover they hold; a mine is an item with
  `"pickup": {"mine": ...}`, seen only within 3 cells, never counted as an item found, set off
  by blasts).
- **Squads that fight as squads**: `assault` (the short guns and claws go in together while the
  long guns pin him down), `sweep` (bounding overwatch: half move, half cover, by turns),
  `ambush` (awake, still and silent until he comes close, then all fire at once) and `swarm` (a
  pack circles until enough of it is near, comes in from every side, bites harder together, and
  scatters when halved). Two more brains, `assault` and `swarm`. A monster's `"squad_tactic"`
  says how it fights in a squad, and `"auto"` squads chain only monsters that fight alike.
  Rooms of dungeons without end and of floors from a seed can hold packs.
- RØØTLESS: **bugrats** (swarm bots: weak alone, a pack is another matter), **gc sweepers**
  (sweep squad soldiers who mine what they hold) and **sigkill commandos** (assault, shotguns
  and grenades); a training program, **SIM-4 Kill House** (`--level sim4`): a room for each kind
  of squad. Bugrat packs roam SIM-1's fens; packs of all three come with depth in SIM-2 and SIM-3.
- The level bot steps out of a grenade's blast, never steps on a mine it has seen, and leaves
  alone items dropped where it cannot stand or under a parked machine.
- **Card battles** (`engine/cards.py`, `cards.json`): a fight played with a deck - energy and
  a hand each turn, a draw and a discard pile, block, strength, weak, exposed, poison, burn,
  bleed, stun, cards that exhaust. Enemies keep their moves and show them with numbers (a
  heavy blow a turn ahead). `"battle": "cards"` in game.json, a mode or a character; decks
  per class; a card to take after each win (the enemy's `card_rewards`, else by rarity and
  class); effects `add_card` and `remove_card`; the `deck` command; `--check` checks cards,
  decks and battles; the editor has a Cards page and its odds play card battles.
- **Duellists**: a character with a `"deck"` plays cards as the player does, choosing each
  one by Monte Carlo tree search over guesses of the hand it cannot see (the visits of a few
  guesses added up). MCTS now asks a state whose move it is (`to_play`), so one side may make
  several moves in a row, and gives its visit counts (`search.mcts_visits`).
- The Hollow: a **Deck** mode - every fight a card battle, a starting deck for each class,
  18 cards of its own, and the Bone Warden and the Hollow King fight with decks of their own.
  `python tests/bot.py 30 cards` plays it.
- **Real time** (`engine/realtime.py`): a fixed-rate clock that runs the ticks it owes (a few at
  most, so a slow machine slows the game rather than making it jump), `Controls` for each tick
  (keys held, pressed, let go), a journal of the keys by tick that plays back the same, and a
  loop for games stepped tick by tick.
- **Key events** (`engine/keys.py`): presses, repeats and releases, from the kitty keyboard
  protocol (asked for, and turned on only when the terminal speaks it; Ctrl-C still stops),
  from the Windows console, or - anywhere else - held keys guessed from their repeats, in
  ticks, so even the guess plays back the same. `--keys` shows what a terminal reports.
- **First-person levels in real time**: `"realtime"` (seconds a beat lasts) on a level or in
  `first_person`, `--realtime [SECONDS]`, and the `realtime [off|SECONDS]` command. A beat
  passes when no key acts in time; typing a line holds the clock; the beats that pass are
  journaled (`.`), so saves play back the same. The footer says REAL TIME.
- **Arcade stages** (`stages.json`, a scene's `"stage"`, `engine/arcade.py`): platformers and
  top-down stages in real time, built from a map of characters - walls, platforms that are
  jumped through from below and dropped through, ladders, spikes, pits, doors and keys,
  checkpoints, chips, hearts, the exit - with runs that speed up and slow down, jumps that are
  lower when let go early, a moment after an edge to still jump and a jump pressed just before
  landing kept. Enemies walk, hop, fly, chase and shoot; jumped on, they are beaten. Goals:
  the exit (with chips), all the chips, every enemy, or lasting out the time; lives, health
  and a time limit. Drawn in half-block pixels with a camera that follows, or a character a
  tile in plain text; piped, a stage is played a typed line at a time. Whole numbers only, so
  a stage's keys play it back the same. `"arcade"` in game.json for a game's own enemies,
  colours, physics and sounds; `on_stage_clear`, `on_stage_fail`, `on_stage_quit` in the scene.
- **The stage bot** (`engine/stagebot.py`, `python -m engine.stagebot GAME`): finds a way
  through a stage without losing a life, and the keys that play its run back.
- RØØTLESS: two arcade sims - **SIM-5: Bus Run**, side on (`--level sim5`), and **SIM-6:
  Purge**, from above with a gun (`--level sim6`).
- **Skirmishes: real-time strategy** (`skirmishes.json`, a scene's `"skirmish"`,
  `engine/rts.py`). A map of ground, rock, water, trees and crystal with up to four sides; workers
  gather crystal and build, buildings train units (queues, paid back when cancelled, rally
  points), units move on flow fields shared by everyone sent to one place, fight what comes
  near, attack on the way, hold, and splash; towers shoot; fog of war. The computer player keeps
  its workers busy, builds barracks, towers and a factory, trains an army in its mix, defends,
  and attacks in growing waves. Kinds and factions as data (game.json `"rts"`). On the screen:
  a cursor, choosing by box, a build menu, a panel with a map of the whole field; the mouse where
  the terminal reports it. Piped, typed commands (`select workers; gather; wait 20`). Ten ticks
  a second in whole numbers: the orders kept by tick play a game back the same.
  `python -m engine.rts GAME` lets the computer play every side.
- **Skirmishes, the rest**: gas, a second resource (`&`, a second cost); **upgrades** made at
  buildings (`"upgrades"`: what they add to which kinds or roles; hit points to those there
  already) and **tech** (`needs`: a building or an upgrade first); **fliers** (`air`: straight
  over anything; `hits` ground, air or both) and **transports** (`carries`: board, ride, set
  down, lost with it); **repair** (workers, for crystal) and **patrol**; **control groups**
  (`G` and a digit; the digit again; twice to go there); groups that keep their shape and the
  slowest one's pace. The computer player puts workers on gas, researches, builds an airfield
  for an air mix, mends its buildings and attacks with what it has when its crystal is gone.
- **Card duels in first-person levels**: a terminal (a switch with `"duel"`) is hacked by a card
  duel before it opens; a monster with `"duel"` is a challenger that waits to be faced. The
  player duels with his health in the level; a lost duel hurts (`feedback`). The duel is
  fought off the level's screen and its outcome is kept in the level's journal, so loads play
  it back without fighting again.
- **Better cards**: `id+` in the deck - a card's own `"upgrade"`, else more of its first
  effect, else cheaper; the effect `upgrade_card` (choose, random, or a card).
- **Card shops**: a shop's card counter - `"cards"` for sale (priced by rarity or `"price"`),
  `"upgrade"` and `"remove"` services. The Hollow's merchant has one.
- **Simulators** (`sims.json`, a scene's `"sim"`, `engine/sim.py`): a vehicle over a map in real
  time - a car (grip, drift, terrain that slows, walls that hurt), a boat, a hover craft (thrust,
  lift, gentle sinking, soft or hard landings, falling when dry) and a plane (throttle, stalls,
  runways) - with fuel and fuel pads, checkpoints in order, landing pads, time limits, and
  instruments as data (bars, centred bars, numbers, a compass strip). **Systems** as data:
  stocks that change by formulas each tick (a small, safe formula language), harming the vehicle
  above a limit, and `win_if` / `fail_if`. **Systems sims** without a vehicle: controls on keys,
  gauges, charts - an economy, an ecology, a reactor. Sines and cosines from a table made with
  whole numbers. Piped, typed keys for seconds. `python -m engine.sim GAME`: the autopilot does
  each one, and its keys play the run back.
- **Mouse reports** (`engine/keys.py`): an SGR mouse report is read as `mouse:B:X:Y` (and
  `mouseup:...`), and the real-time `Controls` carry each tick's events as they came.
- RØØTLESS: **SIM-7: Xantrium Rush** (`--level sim7`), the TAM against the root process - mining
  rigs, troopers, drum gunners and cargo loaders against kworkers, daemons, drones and spinlocks,
  across a toxic channel with three crossings; Xantrium and plasma, hoppers and landers from the
  TAM's hangar, hornets from the root's hive, four upgrades a side.
- RØØTLESS: **SIM-8: Fen Hopper** (`--level sim8`), the hopper flown over the fens through five
  checkpoints to a landing, minding fuel and engine heat; **SIM-9: Coolant Loop** (`--level
  sim9`), a reactor through a shift - rods and pumps against a changing demand.
- RØØTLESS: a hacking deck (ping, firewall, traceroute, fork bomb, kill -9, sudo, grep,
  nohup, chmod 000, fsck, rm -rf, overclock), Black ICE and the Kernel Sentinel, and
  **SIM-10: Root Shell** (`--level sim10`): hack a terminal, then out-deal a sentinel.
- **CLIo Picture** (`engine/picture/`, `--get-picture`): a C library, found and installed as
  Ballistic's is, for the inner loops of the pictures; `--get-picture` installs release 0.3.0
  for Linux, macOS, Windows or Android (Termux), checked by its SHA-256. It draws the open
  land's ground (the caster, `Land.cast`) and the sky over open cells (all but the sun's disc
  and glow, which stay in Python), from release 0.3 the rooms' floor and ceiling (all but
  the teleporters' rings), and from 0.4 it keeps the whole picture from the floor to the
  cells (`engine/picture/frame.py`: walls, pictures, shadows, models' triangles, colour
  changes, hurt, shaking, the cockpit; what has no call there - a glow, a blast - is drawn
  through rows that read and write the frame), and from 0.5 it projects and shades the models
  (with the `pow` and `exp` of the Python running CLIo, handed over by ctypes and checked
  against `model.pbr` before models are drawn there); it works out the land's heights a chunk
  at a time and makes the braille of the dots and dots-fill views. Along the bot's games at
  150 x 34, a room frame takes 4-5 ms instead of 10-12 (dots: 6-7 instead of 40), E1M3, E1M4
  and SIM-1 7-8 ms instead of 35-80 (dots: 10-15 instead of 95-140). It gives exactly the Python's
  results, to the last bit, and is checked against the Python before it is used; an older
  release does what it can and leaves the rest to the Python; without it everything is drawn
  in Python as before.

### Changed

- The banner font has `Ø`, `ø`, `Æ`, `æ`; in plain ASCII they become `0`, `o`, `AE`, `ae`.
- **The far end of a room**: walls are drawn 10 cells ahead (monsters and items are still
  seen, aimed at and shot at within 7), and wide rooms are drawn to the edges of the
  picture, so a far wall no longer shows the floor through it. The walls beside and behind
  the player are drawn from the cells they are, each with its own tile, so a panel beside
  him (the shooting target, the exit switch) is no longer drawn three times. Beyond the
  walls is a dark haze.
- **Faster frames**: the floor and ceiling work out what depends on a cell once per cell
  and each colour's fog once per row; walls, the dots of the braille view and whole-picture
  tints (the goggles' green, root's inverse) work each colour out once - the dots view
  draws in about half the time. The screen writes only what changed since the last frame
  (in an animation, often a small part), with colour codes that set only the colour that
  changed: a whole frame is about a quarter smaller. An animation keeps its time: a slow
  frame shortens the wait after it, and one that comes too late is left out (never the last).

### Fixed

- A first-person view no longer shows the floor and ceiling of the level before when the
  next one starts at the same place, facing the same way.
- E1M3's title page showed its intro a letter to a line (a level's `intro` may now be one
  line or a list), and dying there named a text that is not one; `--check` now says when
  a level's `death_text` is not in texts.json.

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
