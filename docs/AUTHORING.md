# Making games with CLIo

A game is a folder of JSON files. Nothing in it is code. Put the folder under
`games/` and it appears in the launcher; run `python clio.py yourgame --check`
to have the engine look for broken references.

- [A complete tiny game](#a-complete-tiny-game)
- [game.json](#gamejson)
- [Scenes and exits](#scenes-and-exits)
- [Items](#items)
- [Characters](#characters)
- [Conditions and effects](#conditions-and-effects)
- [Dialogue trees](#dialogue-trees)
- [Quests and triggers](#quests-and-triggers)
- [Combat](#combat)
- [Text, colour and themes](#text-colour-and-themes)
- [ASCII art](#ascii-art)
- [Pixel sprites](#pixel-sprites)
- [The map](#the-map)
- [Sound and music](#sound-and-music)
- [Generated dungeons](#generated-dungeons)
- [Coming from CLIo 1](#coming-from-clio-1)

## A complete tiny game

`games/cellar/game.json`

```json
{
  "title": "The Cellar",
  "initial_scene": "cellar",
  "player_stats": {"health": 30, "attack": 3, "defense": 1},
  "intro": "You came down for a bottle of wine. The door has swung shut."
}
```

`games/cellar/scenes.json`

```json
[
  {
    "id": "cellar", "name": "Wine Cellar",
    "description": "Racks of dusty bottles. Stone steps lead up to a heavy door.",
    "items": ["corkscrew"], "passive_items": ["barrel"],
    "exits": [{"door_name": "Cellar Door", "dir": "u", "scene_id": "kitchen",
               "locked": true, "required_item": "iron_key",
               "lock_text": "Locked. Of course it is."}]
  },
  {
    "id": "kitchen", "name": "Kitchen",
    "description": "Daylight, and the smell of bread.",
    "on_enter": [{"win": "You are out, and you still have the corkscrew."}]
  }
]
```

`games/cellar/items.json`

```json
{
  "corkscrew": {"name": "Corkscrew", "description": "Sturdy. Pointed."},
  "iron_key": {"name": "Iron Key", "description": "Cold and heavy."},
  "barrel": {
    "name": "Barrel", "description": "A barrel with a loose bung.", "takeable": false,
    "use_with": {"corkscrew": {"text": "You work the bung out. Something clinks inside.",
                               "do": [{"give": "iron_key"}]}}
  }
}
```

That is a finished game: `take corkscrew`, `use corkscrew on barrel`, `up`. It ships as
`templates/starter/` (run it with `python clio.py templates/starter`); copy that folder to
`games/yourgame/` to begin. It is Apache-2.0 like the engine, so it is yours to change.

## game.json

| Key | Meaning |
| --- | --- |
| `title`, `subtitle`, `author`, `version`, `description` | Shown on the title screen and in the launcher. |
| `initial_scene` | Where the player starts. |
| `player_stats` | `health`, `max_health`, `attack`, `defense`, `critical_hit_chance`, `evasion`, plus any stat of your own. |
| `style` | Theme name (see [themes](#text-colour-and-themes)). |
| `intro` | Key of a text in `texts.json` (or the text itself) shown at the start. |
| `music`, `title_music` | Default track and title-screen track. |
| `max_hints`, `default_hint` | Hint budget and fallback hint. |
| `rpg` | `true` to show levels, experience and gold. |
| `starting_items`, `starting_gold`, `currency` | Inventory and money at the start. |
| `character_creation` | Name prompt and classes; see `games/depths/game.json`. |
| `abilities`, `verbs`, `actions` | Extra combat skills, extra verb synonyms, verbs that work everywhere. |
| `generator` | Turns on the [dungeon generator](#generated-dungeons). |
| `modes` | Ways to play the same game, chosen at the start: see [game modes](#game-modes-scores-and-records). |
| `score` | What a run is worth; turns on the records table. |
| `group_fights`, `max_enemies` | `false` makes every fight one on one; the most enemies in one fight (default 4). |
| `files` | Override file names: `{"scenes": "world/rooms.json"}`. |

Files are looked up by these default names: `scenes.json`, `items.json`,
`characters.json`, `texts.json`, `dialogues.json`, `quests.json`, `triggers.json`,
`music.json`, `sounds.json`, `sprites.json`, `dungeon.json`, and the folder `art/`.
Only scenes and items are required.

## Scenes and exits

```json
{
  "id": "corridor", "name": "Main Corridor", "area": "Deck B",
  "description": "The spine of Deck B.",
  "first_visit": "A longer text shown the first time only.",
  "extra": [{"if": "reactor_online", "text": "The lights are back."}],
  "art": "corridor", "art_if": [{"if": "reactor_online", "art": "corridor_lit"}],
  "music": "lower_deck", "music_if": [{"if": "reactor_online", "music": "powered"}],
  "items": ["wrench"], "passive_items": ["panel"], "characters": ["robot"],
  "exits": [ ... ],
  "random_events": ["A panel rattles."],
  "hint": [{"if": "!has:key", "text": "Find the key."}, "Head south."],
  "on_first_enter": [ ...effects... ], "on_enter": [ ...effects... ],
  "actions": {"shout": "Your voice echoes."},
  "map": [1, 0, 0], "map_icon": "$"
}
```

`items` can be picked up; `passive_items` are fixtures (give them `"takeable": false`
or simply leave them as fixtures; add `"scenery": true` to keep one out of the "You
notice" line).

An **exit**:

| Key | Meaning |
| --- | --- |
| `door_name`, `scene_id` | What it is called and where it leads. |
| `dir` | `n s e w u d ne nw se sw` (or the words). Optional; the map invents one if missing. |
| `locked` + `required_item` | Needs that item (`"passcode"` + `passcode` asks for a code). `lock_text`, `unlock_text`. |
| `blocked` + `unblock_if` | Opens when a condition holds. `block_text`, `unblock_text`. (CLIo 1's `required_condition` / `required_stat` + `required_value` also work.) |
| `guard` | A character id; nobody passes while that character is alive and present. `guard_text`. |
| `leave_if`, `leave_text` | A condition checked every time. |
| `hidden`, `show_if` | Invisible until revealed by an effect or a condition. |
| `do`, `on_unlock` | Effects when passing / when first unlocked. |

## Items

```json
"plasma_cutter": {
  "name": "Plasma Cutter", "aliases": ["cutter"],
  "description": "A heavy cutting tool.",
  "equippable": true, "slot": "weapon", "effect": {"attack": 8},
  "abilities": ["overcharge"], "value": 60
}
```

| Key | Meaning |
| --- | --- |
| `usable` + `effect` | `use` applies the stat changes and consumes it (`"consumable": false` keeps it). |
| `equippable`, `slot`, `effect` | Worn or wielded; one item per slot. |
| `readable_item` | Text shown by `read`. `on_read` runs effects. |
| `components` | Two ids: `combine a with b` makes this item. One id: this is the repaired form. `"tool": true` on a component keeps it. |
| `repairable`, `repair_item`, `repaired_item` | `repair x` turns it into its fixed form if the tool is carried. |
| `lockpick` | Opens any lock that has no particular key. |
| `on_use` | `{"text", "do", "if", "else", "consume"}` for `use x`. |
| `use_on` / `use_with` | `use x on y`: keyed by the other item's id, same shape as `on_use` plus `next_state`. |
| `actions` | Game-defined verbs: `{"push": {"text": "...", "do": [...]}}`. A list of variants picks the first whose `if` holds. |
| `on_take`, `on_examine`, `take_if`, `takeable` | Hooks and restrictions. |
| `combat` | Usable in a fight: `{"damage", "heal", "status", "cure", "focus", "text"}`. |
| `art` | Art shown when examined. |

**State machines** (the CLIo 1 format, extended) make containers, switches and machines:

```json
"locker": {
  "name": "Locker", "current_state": "locked", "contents": ["screwdriver"],
  "unlock_required_item": "locker_key",
  "states": {
    "locked": {"description": "It is locked.", "action": "unlock", "next_state": "closed"},
    "closed": {"description": "It is closed.", "action": "open", "next_state": "open",
               "do": [{"set": "locker_opened"}]},
    "open":   {"description": "It stands open.", "action": "take", "next_state": "empty"},
    "empty":  {"description": "It is empty.", "action": null}
  }
}
```

`unlock_required_item` may be an item id, `"passcode"` (with `passcode`), or absent (any
lockpick works). A state's `action` can be any verb - `"push"`, `"pull"`, `"press"` - and
a state may also carry its own `actions` map.

## Characters

```json
"robot": {
  "name": "Bolt", "aliases": ["robot"], "type": "friendly",
  "description": "A boxy maintenance robot.", "greeting": "It beeps.",
  "portrait": "robot", "voice": {"pitch": 330, "wave": "square"},
  "dialogue_tree": "bolt",
  "gives": {"orange": {"text": "Citric acid!", "consume": true, "do": [{"set": "has_orange"}]}},
  "refuse_text": "It hands the thing back."
}
```

`type` is `friendly`, `neutral`, `hostile` or `aggressive`. Enemies add `stats`, `moves`,
`sprite`, `xp`, `gold`, `inventory` (dropped on defeat), `loot` (`[[item, chance], ...]`),
`tags`, `immune`, `ambush`, `no_flee`, `on_defeat`.

Wanderers: `"movable": true, "moves_after_commands": 4, "roam": ["a", "b"]`, or
`"follow_player": true`. Shops: `"shop": {"sells": [...], "buy_rate": 0.5}`.

`gives` (CLIo 1: `item_interactions`) says what happens when the player gives an item.
The CLIo 1 keys `response`, `consume_item`, `reward_item`, `story_flag` still work.

## Conditions and effects

Anywhere you see `"if"` it takes a **condition**; anywhere you see `"do"` it takes
**effects**.

Conditions:

| Form | True when |
| --- | --- |
| `"flag"` / `"!flag"` | the flag is set / not set |
| `"has:item"`, `"visited:scene"`, `"defeated:char"`, `"here:char"`, `"talked:char"`, `"quest:id:done"` | shorthand |
| `{"has": "x"}`, `{"lacks": "x"}`, `{"equipped": "x"}` | inventory |
| `{"stat": ["attack", ">=", 15]}`, `{"var": ["n", ">=", 3]}`, `{"gold": 20}`, `{"level": 3}`, `{"turns": [">=", 40]}` | numbers |
| `{"in_scene": "x"}`, `{"item_state": ["locker", "open"]}`, `{"class": "rogue"}`, `{"chance": 0.3}` | world |
| `{"all": [...]}`, `{"any": [...]}`, `{"not": ...}`; a list or several keys mean *all* | logic |

Effects (one dict may hold several; they run in order):

| Effect | Does |
| --- | --- |
| `{"say": "text", "style": "story"}` | prints (styles are theme roles; add `"effect": "glitch"`) |
| `{"set": "flag"}`, `{"clear": "flag"}`, `{"var": ["n", "+=", 1]}` | state |
| `{"give": "item"}`, `{"take": "item"}`, `{"add_item": ["item", "scene"]}`, `{"remove_item": "item"}` | things |
| `{"item_state": ["item", "state"]}`, `{"item_set": ["item", "key", value]}` | item state |
| `{"stat": {"attack": 1}}`, `{"heal": 20}` / `"full"`, `{"damage": 5}`, `{"gold": 10}`, `{"xp": 25}`, `{"learn": "cleave"}` | the player |
| `{"goto": "scene"}`, `{"unlock": "scene"}`, `{"lock": ...}`, `{"reveal": ["from", "to"]}`, `{"block": ...}` | movement |
| `{"spawn": ["char", "scene"]}` (add `"copy": true` for a fresh instance), `{"remove_char": "id"}`, `{"move_char": ["id", "scene"]}`, `{"char_set": ["id", "key", value]}` | characters |
| `{"quest": ["id", "start"]}` (`advance`, `complete`, `fail`) | quests |
| `{"fight": "char"}`, `{"dialogue": "char"}`, `{"shop": "char"}` | encounters |
| `{"sfx": "name"}`, `{"music": "track"}`, `{"art": "name"}`, `{"pause": 0.5}` | presentation |
| `{"save": true}` (the mode's own slot; a string names another), `{"win": "text or key"}`, `{"lose": "text or key"}` | the game |
| `{"deepen": true}` | builds the next floor of an [endless dungeon](#endless-dungeons) (the generator does this itself) |
| `{"if": cond, "then": [...], "else": [...]}`, `{"random": [[...], [...]]}` | control |

`$player` in any text is replaced by the player's name.

## Dialogue trees

```json
"bolt": {
  "start": [{"if": "remote_built", "node": "after"}, "hello"],
  "nodes": {
    "hello": {"text": "BEEP! A human!", "goto": "menu"},
    "after": {"text": "The remote suits you.", "goto": "menu"},
    "menu": {"choices": [
      {"text": "Where is everybody?", "say": "Evacuated.", "once": true},
      {"text": "About that droid...", "if": "!droid_calmed", "goto": "droid"},
      {"text": "Take this.", "if": "has:orange", "do": [{"take": "orange"}], "goto": "end"}
    ]},
    "droid": {"text": "It runs hot and angry.", "do": [{"quest": ["remote", "start"]}], "goto": "menu"}
  }
}
```

A choice answers inline with `say` (and stays put), or jumps with `goto` (a node, `"end"`
or `"back"`). `if` hides it, `once` removes it after use, `do` runs effects. A node may
offer `variants` (`[{"if", "text"}]`) for its line. After any conversation the condition
`"talked:<character id>"` holds.

The original flat format still works and is turned into a one-node tree:

```json
"dialogue": {"greet": "Hello."},
"dialogue_options": {"Ask about the ship": "It is old.", "Ask for help": "No."}
```

## Quests and triggers

```json
"main": {
  "title": "Abandon Ship", "description": "Time you left.",
  "auto_start": true,
  "stages": [
    {"text": "Restore main power", "done_when": "reactor_online"},
    {"text": "Reach the bridge", "done_when": "visited:bridge", "do": [{"xp": 20}]}
  ],
  "on_complete": [{"say": "Done."}], "complete_on_win": true
}
```

After every turn each active quest checks its current stage. `auto_start` may be `true`
or a condition; otherwise start a quest with the `quest` effect.

`triggers.json` is a list of `{"id", "when": condition, "do": effects}`; each fires once
(`"once": false` and `"every": 5` make a repeating one).

## Combat

Damage is `(6 + attack) x multiplier, +/-15%, minus half the target's defense`. Each round
the enemy picks a move and *shows it* before the player acts.

```json
"moves": [
  {"type": "attack", "name": "its shock baton", "weight": 3},
  {"type": "heavy",  "name": "The overload discharge", "mult": 2.3, "weight": 2,
   "tell": "Its capacitors whine."},
  {"type": "guard",  "name": "plates locked"},
  {"type": "status", "name": "a venomous bite", "status": "poison", "turns": 3, "power": 3},
  {"type": "heal",   "name": "self-repair", "amount": 15, "below": 0.5},
  {"type": "drain",  "name": "latch on"}
]
```

A `heavy` move takes two rounds: a wind-up (a free round for the player) and the blow.
Statuses: `poison`, `burn`, `bleed` (damage per round), `stun`, `blind`, `weak`, `exposed`.

Skills live in `engine/combat.py` (`ABILITIES`) and can be added in `game.json`:

```json
"abilities": {"headbutt": {"name": "Headbutt", "cost": 1, "kind": "attack", "mult": 1.2,
                           "status": {"name": "stun", "turns": 1}, "text": "You lower your head."}}
```

The player gets a skill from a class, from an item's `abilities`, or from the `learn` effect.
Naming a built-in skill in `abilities` changes only the fields you give
(`"nova": {"name": "Ember Nova"}`).

### Fighting a group

Every hostile character in the room joins a fight (at most `max_enemies`, 4 unless
`game.json` says otherwise); two of a kind are told apart as *Bone Rat A* and *Bone Rat B*.
Each enemy shows its own intent, and the player aims with a number - `strike 2`, `heavy 1`,
`backstab 3` - or is asked. Guarding covers the whole round. Rewards are paid for every
enemy that falls, also when the player then runs away.

- `"solo": true` on a character keeps it out of other fights, and others out of its own.
- `"group_fights": false` in `game.json` turns the whole thing off.
- A skill with `"area": true` reaches every enemy; `"splash": 0.6` gives the others that
  share of a blow aimed at one of them. The built-in `cleave` splashes, `smoke` and `nova`
  are area skills.
- The `combat` block of an item takes `"area": true` as well (a bomb, a flash powder).

## Text, colour and themes

Inline markup works in every text:

```
You take the {item}Bent Wire{/}.   {b red}Danger!{/}   {#ff8800}orange{/}   {on_blue}boxed{/}
```

A tag is a theme role (`item`, `character`, `exit`, `key`, `hint`, `quest`, `error` ...), a
colour name, `#rrggbb`, a 256-colour number, or an attribute (`b`, `dim`, `i`, `u`, `inv`).
`{{` prints a brace.

Themes live in `engine/style/configs/` (a game may add its own in `themes/`). The CLIo 1
schema is unchanged - `colors` per role, `styles` per role - with a few additions:

```json
"styles": {
  "description": {"frame": "ROUNDED", "padding": 2, "character_delay": 0.012, "fade_in": true},
  "list_title":  {"frame": "DOUBLE", "alignment": "center", "gradient": true}
},
"ui": {"prompt": "> ", "max_width": 78, "transition": "wipe", "frame_color": "38;5;61",
       "title_gradient": [39, 45, 51, 87, 123]}
```

Frames: `NONE SINGLE DOUBLE ROUNDED HEAVY ASCII DOTS`. Effects: `character_delay`
(typewriter), `fade_in`, `glitch`, `flash`, `gradient`. Effects only play on a real
terminal and never when output is piped.

## ASCII art

`art/corridor.art`:

```
# comment
@color steel
@palette
y = amber
@art
 |   |   _______   |   |
 | ' |  |   |   |  | ' |
@mask

   y                 y
@small
 [corridor]
```

The mask has the same shape as the art; each letter picks a palette colour, blanks use
`@color`. `@small` is used when the main drawing is too wide; if nothing fits, the art is
left out. Keep art within about 34 columns so it fits beside the text on a desktop and
above it on a phone. Reference art from scenes (`"art"`), items (`"art"`) and characters
(`"portrait"`); `title`, `win` and `lose` are picked up automatically.

## Pixel sprites

`sprites.json`:

```json
"bugrat": {
  "palette": {"b": "#3a2a22", "B": "#8b5a3c", "r": "#ff3030"},
  "pixels": ["..bBBb..", ".BrBBrB.", "..BBBB.."]
}
```

Two pixel rows share one text row (`▀` with a foreground and a background colour), so
pixels are square. `.` is transparent. Give a character `"sprite": "bugrat"` - or
`"sprite": "auto"` to have one grown from its name (`"sprite_size": 14` to change the size).

## The map

`map` draws explored rooms from the exits. Give exits a `dir` and the layout follows it;
give scenes `"map": [x, y, level]` for full control. `"map_icon": "$"` marks a room once
visited. Set `"map": false` in `game.json` to disable it.

## Sound and music

Reference a track from a scene (`"music"`), from `game.json`, or with the `music` effect.
A track is:

- a name from `music.json`,
- an audio file relative to the game folder (`"music/theme.ogg"`) - played if the machine
  has a player for that format, otherwise the default track is used,
- or generated: `{"generate": {"mood": "dark", "seed": 7}}`.
  Moods: `calm mystery dark tense battle heroic shop space victory defeat`.

A written song (`music.json`):

```json
"theme": {
  "tempo": 84, "steps_per_beat": 4,
  "instruments": {
    "lead": {"wave": "square", "duty": 0.25, "attack": 0.02, "decay": 0.15, "sustain": 0.5,
             "release": 0.3, "vibrato": [5, 0.006], "volume": 0.3, "echo": [0.36, 0.35]},
    "arp":  {"wave": "triangle", "volume": 0.22, "arp": 2},
    "bass": {"wave": "triangle", "volume": 0.5},
    "kit":  {"wave": "drums"}
  },
  "patterns": {
    "A": {"lead": "e5:4 .:2 c5:2 d5:2 e5:4 .:2 | f5:4 .:2 e5:2 d5:2 c5:4 .:2",
          "arp":  "[a3 c4 e4 c4]:16 | [f3 a3 c4 a3]:16",
          "bass": "a1:8 a1:4 e2:4 | f1:8 f1:4 c2:4",
          "kit":  "k . h . s . h . k k h . s . h h | k . h . s . h . k k h . s . s s"}
  },
  "sequence": ["A", "A"]
}
```

Notes: `c4`, `d#4`, `eb3`; `:4` lasts four steps; `.` rests; `-` holds; `[c4 e4 g4]:8` is a
chord (arpeggiated if the instrument has `arp`); `|` is ignored. Waves: `square` (with
`duty`), `triangle`, `saw`, `sine`, `soft`, `organ`, `noise`, `drums` (`k s h o t c`).

A note can also move (since 2.1). `c3>c5:16` slides from one pitch to the other over its
length; `c4@5` plays at a level between `@0` (silent) and `@9` (full, the default);
`c4@2>9:16` swells from level 2 to level 9; `c3>c5@2>9:16` does both and is a riser. Levels
work on chords (`[c4 e4 g4]@6:8`) and drum hits (`k@4`) too. On the `noise` wave a slide
sweeps the hiss. Songs that use none of this sound exactly as they did.

Sound effects are played by name (`{"sfx": "unlock"}`). Built in: `select back error save
step door airlock locked unlock pickup drop open use craft read computer power teleport
secret coin quest quest_done levelup heal trap alarm encounter hit crit miss hurt guard
focus special flee enemy_down win lose explosion`. Add or replace them in `sounds.json`:

```json
"zap": {"wave": "saw", "freq": [900, 120], "dur": 0.2, "vol": 0.4},
"fanfare": {"notes": "c5 e5 g5 c6:3", "tempo": 480, "wave": "square"},
"door": "sounds/my_door.wav"
```

Rendered audio is cached in `~/.cache/clio/audio` (override with `CLIO_CACHE`).

## Generated dungeons

```json
"generator": {"type": "maze", "entry": "camp", "loops": 0.22}
```

`entry` is a hand-written scene with an exit whose `scene_id` starts with `@`; the
generator connects it to the first floor. Floors are described in `dungeon.json`: size
(`w`, `h`), `monsters` (weighted), `elite` (guards the stair down), `boss` (last floor),
`merchant`, `treasure`, `shrine`, `wanderer`, loot tables, room texts per kind and
`trap_damage`. `games/depths/dungeon.json` is a complete example. The world seed decides
everything, so `--seed` replays a dungeon exactly.

A monster room can hold a pack instead of a single creature. `packs` lists the groups
with their weights, `pack_chance` says how often a monster room gets one. A pack always
guards an item from the floor's loot table (`pack_loot` changes that chance).

```json
"pack_chance": 0.25,
"packs": [[["bone_rat", "bone_rat"], 3], [["bone_rat", "gloom_bat"], 2]]
```

### Endless dungeons

In a [game mode](#game-modes-scores-and-records) with `"endless": true` the dungeon does
not stop at the last floor you wrote. Each time the player arrives on the deepest floor,
one more is built below it and the keeper of the stair (the elite, or the boss) stands in
the way. Deeper floors reuse the written floors in turn. Their monsters are scaled
automatically so that every floor is `growth` stronger than the one above, whichever
description it uses, and experience and gold grow with them. The `endless` block of
`dungeon.json` tunes the rest; all of it is optional:

```json
"endless": {
  "growth": 0.22,
  "prefixes": ["Elder", "Dread", "Abyssal"],
  "names": ["The Lower Crypt", "The Drowned Deep", "The Ashen Halls"],
  "arrival": ["The stair keeps going. Nobody ever drew a map of this far down."],
  "floor": {"merchant": "merchant", "chest_loot": [["heart_root", 3], ["whetstone", 3]]},
  "boss": {"name": "Echo of the Hollow King", "on_defeat": [{"add_item": "heart_root"}]}
}
```

| Key | Meaning |
| --- | --- |
| `growth` | How much stronger each floor is than the last (0.22 = 22%). |
| `prefixes` | Name prefix for monsters, one per pass through the written floors. Characters marked `"unique": true` keep their name. |
| `names`, `arrival` | Names and arrival texts for the deeper floors, used in turn. |
| `cycle` | Which written floors to reuse, by index (default: all, in order). |
| `floor` | Settings laid over every deeper floor: loot tables, a merchant, chances. |
| `boss` | Changes to the boss when it returns: name, texts, `on_defeat`. |

The variable `depth` holds the deepest floor reached, and every floor sets a flag
`floor_N` on arrival, so quests and conditions can use both.

## Game modes, scores and records

`modes` in `game.json` offers several ways to play one game. The player picks one at the
start (or passes `--mode rogue` on the command line); the first one listed is the default.

```json
"mode_prompt": "How will you go down?",
"modes": {
  "story": {"name": "Story", "description": "Three floors and a crown."},
  "rogue": {"name": "Rogue", "description": "One life. How deep can you go?",
            "permadeath": true, "endless": true}
}
```

| Key | Meaning |
| --- | --- |
| `name`, `description` | Shown in the menu. |
| `permadeath` | One life. `load` is refused, the run is saved as it goes (at every fight, on quitting), and the save is erased when the run ends. Leaving in the middle of a fight puts the player back at the start of that fight. |
| `endless` | Sets the flag `endless`, which keeps a [generated dungeon](#endless-dungeons) going. |
| `flags`, `on_start` | Extra flags to set and effects to run when the mode starts. |
| `text`, `intro`, `help` | A line shown on choosing the mode; an intro and a help text that replace the game's. |
| `slot` | Save slot of the mode. The first mode uses `save`, the others their own name, so a story save and a rogue run do not overwrite each other. |

The chosen mode sets the flag `mode_<id>` and the variable `mode`, so any condition can
ask for it: `{"if": "mode_rogue", "then": [...], "else": [...]}`.

`score` says what a run is worth. Each name is a counter in the game's variables, one of
`level`, `gold`, `xp`, `turns`, `places`, `quests`, `health`, `win`, or a flag (worth 1
when set); the number is its weight.

```json
"score": {"depth": 100, "kills": 5, "level": 20, "gold": 1, "crown_taken": 250, "win": 500}
```

`kills` counts defeated spawned creatures, `depth` the deepest dungeon floor. With a
`score`, the game shows the points in `stats` and at the end of a run, and keeps the ten
best runs of every mode. `records` shows the table. It lives next to the saved games, in
`records.dat`.

## The editor

```
python clio.py mygame --edit
```

opens the game in your browser. Nothing is installed and nothing leaves your machine: the
page is served by CLIo itself, on this computer only, and it writes only the data files of
that one game. Ctrl+C in the terminal ends it.

- On the left, what the game is made of - scenes, items, characters, dialogues and so on -
  then the things of that kind, then a form for the one you chose.
- Fields the editor knows have a control of their own: text, a number, a tick box, a list
  of items picked from the game's items. Parts with fields of their own - a scene's
  exits, a character's stats and moves, a quest's stages, a dialogue's nodes and their
  choices, an item's states - open as small forms: add, remove, reorder. Whatever the
  editor has no form for is shown as JSON, under *Everything else* or *Other fields*, and
  kept exactly as written. Nothing is hidden and nothing is dropped.
- What only some things have - what happens on entering a room, what a character does
  when given something - waits under *Add…* at the end of a form until it is wanted.
- The engine checks the game as you type, with the same rules as `--check`, on the files
  as they would be after saving. Problems are listed at the top; choosing one takes you
  to the thing it is about.
- *Save* writes the changed files. A file keeps its layout, so a version-control diff
  shows only the lines you changed. The first save of a day keeps the previous version of
  each file in `.editor-backup` inside the game folder.
- Under each thing is the list of places that refer to it. Change an id and the editor
  offers to change those places too.

- *Check-up* lists what is not wrong but may not be meant: a room that cannot be reached
  from the first scene, a thing nothing else in the game refers to.
- *Theme* switches between light, dark and whatever your system uses; the choice is
  remembered. *Download game* gives you the whole game folder as one zip file.

The forms are built from `engine/schema.py`, which describes the data files. To give a
field a control, add a line there.

### What happens, and when

Effects and conditions are forms too. Wherever something happens - a choice's *And then*,
a trigger's *Then*, a room's *On entering*, a quest's *When it is completed*, what an
item answers when it is used - each effect is a line: what happens, chosen from a list
of everything the engine can do, and what it happens to, chosen from the game's own
scenes, items, characters, quests and texts. Lines can be moved up and down.

A condition - *Offered when*, *When*, *Done when*, *Unblocked when* - is one question,
chosen from a list of everything the engine can ask, with a tick for *not*. The editor
writes the short form where there is one (`"has:key"`, `"!met_robot"`,
`"quest:main:done"`) and the long form where it is needed (`{"turns": [">=", 50]}`).

Not everything fits on a line. An effect with a branch (`if` / `then` / `else`), several
questions at once (`all`, `any`), or more settings than the line shows (a line's
`style`, an effect's own `if`) appear as they are written in the file, and can be edited
there. Nothing is rewritten by being shown: a file changes only where you change it.

The two lists are `EFFECTS` and `CONDITIONS` in `engine/schema.py`; a test keeps them
equal to what `engine/conditions.py` understands, so the editor cannot offer a word the
engine does not know, or miss one that it does.

### The map and the conversations

Choosing *Scenes* on the left shows the **map**: the rooms where the player's own map puts
them, one level at a time. A dashed way is locked, blocked or guarded; an arrow is a way
with no way back; ▲ and ▼ lead to another level. Click a room to open it. Drag a room to
pin it to another place (that writes its `"map": [x, y, level]`). Rooms that no exit leads
to have a dashed edge and are listed under the picture. Rooms a game makes as it is played - a generated
dungeon - are not on it.

A **dialogue** opens with a picture of how it runs: its nodes from left to right in the
order they can be reached, the jumps between them as arrows - solid for a choice, dotted
for a node that goes on by itself - and a count of the answers that stay on a node. A
node that is never reached has a dashed edge; a jump to a node that does not exist is
named. Click a node to open it in the form below.

### Can it be finished?

No program can tell in general whether an adventure can be won - a case with its code on a
note three rooms away defeats any blind search. What can be checked, exactly and after
every change, is that a known way through still works. A game keeps that way in
`walkthrough.txt`, in its folder:

```
# one command per line, as a player would type them; answers to questions too
== the quiet way out
take wire
unlock locker
...
== the loud way out
seed 11
fight bugrat
strike
```

`== name` starts another walkthrough, played from a fresh start - one for each ending,
say. `seed 7`, as the first line of a walkthrough, sets the dice where fights could go
either way. `#` starts a comment.

*Can it be finished?* in the editor plays them on the real engine, on the game as it is
in the page - unsaved changes included - and says for each how it ended, at which line it
stopped, and which lines the game refused. It also names the rooms no walkthrough enters
and the quests none completes. From the command line, for a test or a release script:

```
python clio.py mygame --walkthrough        # exit code 0 when every walkthrough is won
```

A game whose rooms are made in play (a generated dungeon) has no fixed way through; this
check is for games that are written.

### All the text at once

Everything a player can read - names, descriptions, dialogue, quest steps, the lines of
effects - can be handled as one table, without touching ids, conditions or anything else.

- **Find and replace.** Type in *Find in everything the player reads*: the places are
  listed, and choosing one takes you there. *Replace all* changes them in the page; as
  always, nothing is written until you save, and the engine checks the result first.
- **Export and import.** *Export text* downloads a CSV file with two columns, the place
  and the text:

  ```
  where,text
  scenes/utility_room/description,"A cramped maintenance closet: two dented lockers, ..."
  scenes/utility_room/exits/0/guard_text,The bugrat has nested in the hatch mechanism. ...
  dialogues/bolt/nodes/hello/text,...
  ```

  Open it in a spreadsheet or send it to a proofreader or translator; change the second
  column and leave the first alone. *Import text* puts it back. A row whose place no
  longer exists - the game changed in the meantime - is listed and left out; nothing is
  guessed. Markup such as `{item}...{/}` and `$player` is ordinary text here: keep it.

  The same from the command line, for scripts:

  ```
  python clio.py mygame --export-text texts.csv
  python clio.py mygame --import-text texts.csv      # refuses if the game would then fail --check
  ```

### Making an enemy, and trying it

Under the list of characters, *Make an enemy…* builds a new one of a strength you choose.

- **Strength** is health times hitting power, `max_health * (6 + attack)` - the measure the
  dungeon generator itself uses to keep floors in step. You pick a floor to measure
  against (for a game with a dungeon: its floors and a few below the last; otherwise the
  average of the game's enemies) and a rank: a minion is 0.6 of that floor's average
  monster, a regular one equal to it, an elite 2.2, a boss 4.
- **Start from** an existing character and the new one keeps its moves, tags and looks,
  scaled by the generator's own rule; or from a plain enemy with a blow and a heavy blow.
- **Build** turns the same strength into more health and softer hits, or the reverse.
- **Try it** runs real fights - the engine's battle code, forty times for each class the
  game has - and shows how often the player wins, how much health is left, how long it
  takes. The player in these fights is at the level you set, carries what a new character
  starts with, and fights sensibly without flair: guards a wound-up blow, heals when low,
  uses a skill when there is focus for it. Use the figures to compare enemies with each
  other; a person will do better or worse than they say.
- **Add to the characters** puts it in the game (unsaved, like every change). From there
  it is an ordinary character: put it in a scene, in a floor's monster table, or edit it.

Every character with stats also has *Try in a fight* at the top of its form, alone or two
or three at once.

### Pictures

A character's *Sprite* field shows what the game will draw in a fight. With `auto` that is
a creature grown from the character's name - the same words always grow the same one.

- *Another one* grows a different creature (it sets `sprite_seed`, the words to grow from).
- *Draw over it* keeps the creature as a drawing in `sprites.json`, points the character
  at it, and opens it in the pixel editor.
- The pixel editor - also for any sprite under *Sprites* - paints with the mouse (right
  button rubs out) or the keyboard (arrow keys, Space, Delete), mirrors left and right
  unless you switch that off, changes the colours and the size, and can grow a fresh
  creature from any words. A small picture shows it as the game will, on a dark screen.

What counts as text is a rule of thumb (`engine/editor/texts.py`): names, titles and
anything called `..._text` always; otherwise a string with a space in it, unless its key
is known to hold something else. Songs, sounds and sprites are left out. A choice written
as a key - `{"Ask about the ship": "..."}` - has its answer in the table but not the
question, since a key cannot be changed without changing what refers to it.

## Coming from CLIo 1

CLIo 1 game folders load unchanged. What behaves differently:

- **Conversations** from `dialogue_options` continue until the player leaves, instead of
  ending after one reply. `dialogue_rewards` options now appear in the menu.
- **Unlocking** a container also opens it.
- **Lock picking** used to be hard-wired to the item `bent_wire`. It is now the item flag
  `"lockpick": true` (set automatically on `bent_wire` when no item declares it).
- **Repairing** keeps the tool unless the tool is `"consumable": true`. A broken item
  named `broken_x` finds `fixed_x` / `repaired_x` on its own.
- **Combat** is the new tactical system; typing `attack` and `defend` still works.
- **`push`, `pull`** and friends are no longer built in: define them with `actions`.
- **Saves** hold the entire world (opened containers, moved characters, unlocked doors),
  live in the user data folder (`CLIO_SAVES` to override) and are not compatible with
  CLIo 1's `savegame.json`.
- **Framing**: not every message gets its own frame; the theme decides per role.
- **`story_texts.json` conditions** match item and enemy names or ids, and
  `enemy_defeated` is actually checked.
- **Missing audio files** no longer print "The sound of silence!"; a generated track
  plays instead.
