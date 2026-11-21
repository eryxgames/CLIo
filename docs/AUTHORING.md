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
- [Title screens, banners and animation](#title-screens-banners-and-animation)
- [Pixel sprites](#pixel-sprites) (and [pictures in the styles](#pictures-in-the-styles))
- [The map](#the-map)
- [Sound and music](#sound-and-music)
- [Generated dungeons](#generated-dungeons)
- [First-person levels](#first-person-levels)
- [Arcade stages](#arcade-stages)
- [Skirmishes (real-time strategy)](#skirmishes-real-time-strategy)
- [Simulators](#simulators)
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
| `title_banner` | The title drawn in a graphic style: `{"style": "reflect", "palette": "ice"}` - see [banners](#title-screens-banners-and-animation). |
| `title_effect` | How the title picture animates: `"glitch"`, `"shine"`, `"none"`... |
| `logo` | Which CLIo logo the title screen shows when the game has no title art or banner (`python clio.py --looks`). |
| `win_banner`, `lose_banner` | A banner at the end, when there is no `win` / `lose` art. |
| `palettes` | The game's own named colours, for every banner: `{"dusk": ["#ffd27a", "#ff6f91", "#5a2a8f"]}`. |
| `banner_defaults` | The game's house style: what every banner uses unless it says otherwise. |
| `show_title` | `false` hides the title text under the title art (it is hidden under a banner unless `true`). |
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
| `{"sfx": "name"}`, `{"music": "track"}`, `{"art": "name"}` (add `"effect": "glitch"`), `{"pause": 0.5}` | presentation |
| `{"banner": "Chapter II", "style": "led", "palette": "amber", "effect": "flicker"}` | big text in a [graphic style](#title-screens-banners-and-animation) |
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

### Card battles

A fight can be played with a deck of cards instead: `"battle": "cards"` in `game.json`,
in one of its [modes](#game-modes-scores-and-records), or on one character
(`"battle": "classic"` on a character keeps the old fight for it). The Hollow's *Deck*
mode plays every fight this way.

Each turn the player gets `energy` (3) and draws `hand` (5) cards; he plays what he can
pay for, by number (`2`, or `2 1` to aim at enemy 1), and ends the turn with `end`. What
is left in his hand goes to the discard pile, which is shuffled into a new draw pile when
that runs out. `piles` shows them, `use` takes an item from the pack (1 energy), `flee`
tries to run (ending the turn if it fails). Block soaks damage until his next turn.

```json
"cards": {"energy": 3, "hand": 5, "rewards": 3,
          "deck": ["strike", "strike", "strike", "strike", "strike", "defend", "defend", "defend", "defend", "bash"],
          "decks": {"warrior": ["strike", "...", "shield_bash"]},
          "enemy_health": 1.0, "enemy_damage": 1.1}
```

The player's deck starts as his class's (`decks`), else `deck`, else the engine's
starter, and is kept with the game (`deck` shows it). A won fight offers `rewards` cards:
the enemy's `"card_rewards"` if it has any, else the game's cards by rarity (common six
times as often as rare; `"reward": false` keeps a card out, `"classes"` keeps it to some
classes). Effects `{"add_card": "id"}` and `{"remove_card": "id"}` change the deck from
anywhere: a shrine, a shop, a quest.

Cards live in `cards.json` (over the engine's own `strike`, `defend`, `bash`, `cleave`,
`twin_strike`, `heavy_blow`, `second_wind`, `quick_step`, `hamstring`, `envenom`, `rally`,
`bandage`, `adrenaline`, `iron_wall`):

```json
"backstab": {"name": "Backstab", "cost": 1, "type": "attack", "rarity": "starter",
             "effects": [{"damage": 7}, {"status": "bleed", "turns": 3, "power": 3}]}
```

| Field | Meaning |
| --- | --- |
| `cost` | energy, 0 to 9 |
| `type` | `attack`, `skill` or `power` |
| `target` | `enemy` (one, aimed), `all`, `self` - by default `enemy` when it hurts or hexes |
| `effects` | in order: `damage` (`times` over), `block`, `draw`, `energy`, `heal`, `strength` (more damage on every hit, for the fight), `status` with `turns` and `power` |
| `exhaust` | gone for the rest of the fight once played |
| `rarity`, `reward`, `classes` | how and to whom it is offered after a win |
| `text`, `say`, `sfx` | what it says it does (else made from its effects), a line when played, a sound |

Statuses: `weak` (hits a quarter softer), `exposed` (takes half again), `blind` (hits half
as hard), `poison`, `burn`, `bleed` (`power` at the end of each of its turns), `stun`
(loses its next turn). The player's `attack` adds one to every hit for each two points
over 5; his `defense` takes half of itself off every hit he takes.

Enemies fight by their `moves`, and show what they will do with numbers: an attack's
damage is (4 + attack) times its `mult`, times `enemy_damage`; a guard gives it block (4 +
twice its defence); a heavy move winds up a turn ahead and says how hard it will land.
`enemy_health` scales their health in card battles.

**Duellists.** A character with a `"deck"` (and `"energy"`, `"hand"`) plays cards as the
player does, from a hand he cannot see (only how many cards it holds). It chooses each
card by Monte Carlo tree search (engine/ai/search.py) over a few guesses of what it cannot
know - his hand and the order of both draw piles - and adds the guesses' visits up: an
information-set search, the simple way. It takes a kill when it has one, guards when a
blow is coming, and plays its big cards when they count. The search stops at a number of
games played, not at a time, so it chooses the same on any machine. In a classic fight
the deck is ignored and the `moves` are used.

The editor's *odds* for an enemy (and `python tests/bot.py 30 cards` for The Hollow) play
card battles too, the plain greedy way: block what is coming when it would hurt, hit the
weakest.

**Better cards.** Any card can be made better: in the deck it becomes `id+` (shown with a
+). What changes is the card's own `"upgrade"` (`{"cost": 1}`, or new `effects`, or a
`name`), else three more damage, block or healing (one more draw, strength, energy or turn)
on its first effect that has them, else one cheaper; `"upgrade": false` keeps a card as it
is. The effect `{"upgrade_card": "choose"}` asks which (`"random"`, or a card's id, does not).

**Card shops.** A shopkeeper's `shop` can keep a card counter beside its goods (shown when
the game has a deck): `"cards"` (ids for sale, each once unless `"unlimited_cards"`; priced
by `"price"` on the card, else by rarity - starter 25, common 45, uncommon 70, rare 110 -
times `"card_rate"`), `"upgrade"` (the price of making a card better) and `"remove"` (of
taking one out; never below `"least"` cards in game.json `cards`, 5):

```json
"shop": {"sells": ["healing_draught"], "cards": ["backstab", "riposte", "ember"],
         "upgrade": 60, "remove": 50}
```

**Card duels in first-person levels.** A terminal - a switch with `"duel"` - is hacked with a
card duel before it is thrown; a monster with `"duel"` is a challenger that waits to be
faced (Enter) and dealt with (`"fights": true` and it fights as well):

```json
"t": {"switch": "ice_down", "label": "TERMINAL", "duel": "black_ice", "feedback": 20,
      "duel_won": "The ICE melts."}
```

`duel` names a character (with `stats`, and a `deck` for a duellist). The player duels with
his health in the level, and keeps what is left of it; a lost duel hurts him `feedback` (20),
and the terminal stays shut; fled, nothing happens. A won challenger dies. The game needs a
`"cards"` deck for it (game.json); won duels offer the opponent's `card_rewards`. The duel is
fought off the level's screen and the level comes back after it; its outcome is written into
the level's journal (`use =won:57`), so a load plays the level back without the duel being
fought again. The level bot, with no game round it, takes duels as won.

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

A palette colour is anything markup takes: `y = amber`, `w = #ffffff b`, `s = #3a2a14 on_#101010`.
A comment after a colour starts with ` # ` (a space, a hash, a space).

More sections, all optional:

```
@effect shine          how the art animates when it is shown (see below)
@fps 8                 the speed of the @frame drawings
@ascii                 a hand-made version for terminals without Unicode (--ascii), with its own @mask
 (oo)
@frame                 a drawing to play, in turn, after the art (each may have its own @mask)
 /--\
```

Without `@ascii` the engine turns box-drawing and block characters into `+ - | # " _`
itself, and braille dots into `. ' : #`; a hand-made version usually reads better.

## Title screens, banners and animation

The title screen shows, in this order of preference: the game's own `art/title.art`; its
`title_banner`; the CLIo logo named in `logo` (the engine's own by default). Every picture
fades in over a star field and then plays its animation, if it has one.

### Banners

A banner is any text drawn in one of the engine's graphic styles. The game's title is the
usual one, so a game can have a title screen of its own without drawing anything:

```json
"title_banner": {"style": "reflect", "palette": "ice", "effect": "shine"}
```

| Field | Meaning |
| --- | --- |
| `text` | What to draw; the game's `title` when left out. |
| `style` | `pixel`, `shadow`, `chrome`, `glitch`, `reflect`, `synthwave`, `led`, `dots`, `plain` |
| `palette` | `clio`, `sunset`, `ice`, `fire`, `toxic`, `gold`, `steel`, `amber`, `phosphor`, `blood`, `royal`, `forest`, `mono` |
| `colors`, `accent` | Your own colours instead: `["#fff07a", "#ff6f91", "#9b5cff"]` top to bottom; `accent` for lower-case letters. |
| `effect` | Its animation (each style has a default: `glitch` for glitch, `shine` for chrome...; `"none"` for none). |
| `scale` | `2` draws every pixel twice as big, for short titles on wide screens. |

A game can name colours of its own and use them like the built-in palettes, and set a
house style that every banner follows unless it says otherwise:

```json
"palettes": {
  "dusk":  ["#ffd27a", "#ff6f91", "#5a2a8f"],
  "brand": {"colors": ["#e8f6ff", "#5fd7ff", "#2f6bff"], "accent": ["#ffd23f", "#d9700a"]}
},
"banner_defaults": {"style": "shadow", "palette": "brand"},
"title_banner": {"scale": 2}
```

The house colours stay when a banner picks another style (`{"banner": "Act II", "style": "led"}`
is a brand-coloured LED board). In the editor, every banner field is drawn as you type, as
the game will draw it, on a desktop, a phone or a 24-column screen, with its animation.

Capitals and digits are 5x7 pixels; lower-case letters are drawn as small capitals, so
`CLIo` keeps its small o. Accented letters lose their accent. A banner too wide for the
screen is wrapped at spaces, then drawn smaller, and in the end written as spaced capitals,
so it shows on any phone. Without a `style`, the theme chooses: `retro` draws green LEDs,
`techno` glitches, `elegant` casts a shadow, `minimal` keeps to plain letters.

The same banners work in the story - `{"banner": "Chapter II", "style": "led"}` - and at
the end: `"win_banner": {"text": "Victory", "style": "chrome"}`.

To see them, or to turn one into a file you can draw over:

```
python clio.py --looks                                     # every style, palette, logo, animation
python clio.py --banner "The Hollow" --banner-style synthwave
python clio.py --banner "The Hollow" --banner-style shadow --export games/mygame/art/title.art
```

### Animation

| Effect | What happens |
| --- | --- |
| `glitch` | rows slip sideways, colours split into red and cyan, noise flickers, then it settles |
| `flicker` | it lights up part by part like a neon sign switched on |
| `shine` | a bright glint sweeps across |
| `twinkle` | stars and dots twinkle (in other art, a few cells sparkle) |
| `pulse` | the colours swell towards white and back |
| `cycle` | the colours run once round the colour wheel |
| `type` | it is typed in from the left behind a block cursor |
| `frames` | the `@frame` drawings of the `.art` file play at `@fps`; with `reveal=1` they build the picture up, so it is not shown before them |

An effect is named in the art itself (`@effect glitch`), for the title (`"title_effect"`),
for a banner (`"effect"`), or where art is shown (`{"art": "door", "effect": "flicker"}`).
It may carry options: `"glitch loops=2 speed=0.5"` (`speed` 2 is twice as fast). An `.art`
file with `@frame` drawings and no `@effect` plays its frames.

Animation plays once, only on a real terminal, never with `--fast`, and Ctrl-C skips it.
`shine`, `pulse` and `cycle` are made of colour and do not play without it; the others
work everywhere.

### The CLIo logos

The CLIo logo is a little terminal window that types its own name (`engine/art/clio_logo.art`).
Fourteen more are in `engine/art/logos/`, most with an animation of their own: `classic` (the
logo before 2.2), `glitch`, `neon` (flickers on), `led` (a scrolling LED board), `chrome`,
`synthwave`, `pixel`, `shadow`, `slant`, `reflect`, `sword`, `braille`, `constellation`,
`badge`. A game shows one with `"logo": "neon"`; the launcher with `--logo neon` or
`CLIO_LOGO=neon`, and `--effect` gives it another animation.

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

### Pictures in the styles

A sprite is also a picture: any name that has no `.art` file is looked up in `sprites.json`,
so `"art": "torch"` in a scene, `"portrait": "torch"` on a character, `{"art": "torch"}` in
the story and a sprite called `title` (the title screen) all work. A sprite can choose how
it is drawn, animate, and hold more drawings that play in turn:

```json
"torch": {
  "palette": {"y": "#ffd23f", "r": "#ff5533", "s": "#8a5a2b"},
  "pixels": ["..yy..", ".yrry.", "..ss.."],
  "frames": [[".yy...", ".yrry.", "..ss.."], ["...yy.", ".yrry.", "..ss.."]],
  "fps": 6, "loops": 3, "style": "dots", "effect": "twinkle"
}
```

| `style` | A pixel is drawn as | Size of a 16x16 picture |
| --- | --- | --- |
| `pixel` | half a character (the default; two colours a character) | 16 x 8 |
| `blocks` | two full blocks: big, crisp and square | 32 x 16 |
| `dots` | braille dots, eight to a character: the finest detail, one colour a character | 8 x 4 |
| `led` | a round dot and a space, like an LED panel | 31 x 16 |
| `ascii` | two letters by brightness, like classic ASCII art | 32 x 16 |

`frames` are drawings of the same size, played after the first `loops` times at `fps`
drawings a second; `effect` is any [animation](#animation) instead. Where the picture is too
wide for the screen it is drawn in dots; without Unicode, in letters by brightness. Enemies
fight in their sprite's style too.

In the editor every sprite has a drawing board of up to 64 x 64 pixels, drawings to add,
copy and remove (the one before shows faintly while you draw the next), and the picture as
the game draws it, in its style, with its animation.

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

Generated music can be shaped in two ways without changing its notes (since 2.2.2), so
that a game, a level or a scene keeps one sound:

- **`sound`**: `"chip"` (the default - CLIo as it has always sounded) or `"rich"`, the same
  tune on other instruments: strings, a horn or a trumpet, a clarinet, plucked strings, an
  overdriven guitar, a synthesizer in a large room, as the mood has them.
- **`form`**: how the tune's two halves, `A` and `B`, are laid out; without it `A A B A`. A
  mark says how a half is played: `(A)` without the tune, `A-` quietly (no bass, no drums),
  `A+` a tone higher. `"long"` is `(A) A A B A B- A A+` - an introduction, the tune, a quiet
  stretch, the tune again and once more a tone higher: more than twice as long before it
  comes round.

Say it in the track - `{"generate": {"mood": "dark", "seed": 7, "sound": "rich", "form":
"long"}}` - or once for the whole game with `"music_sound"` and `"music_form"` in
`game.json`; a scene, or a floor of a generated dungeon, can have its own with the same two
keys. A track's own word comes first, then the scene's, then the game's. Music heard while
in a scene - a fight there, too - takes that scene's choice.

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

Besides its wave and its envelope (`attack`, `decay`, `sustain`, `release`) an instrument
can have `gate` (how much of a note's length it sounds, 0.9 by default), `lowpass` (0 to
1, darker), `echo` (`[seconds, gain]`) and, since 2.2.2, `drive` (0 to 1): overdrive, as of
a guitar amplifier. The whole track goes through it, so a root and its fifth on a `saw`
wave - `[e2 b2]:8` - growl as a power chord does; a `lowpass` after it takes the fizz off:

```json
"guitar": {"wave": "saw", "drive": 0.7, "lowpass": 0.45, "sustain": 0.8, "volume": 0.3}
```

Three more, also since 2.2.2:

- `detune` (cents, try 6 to 12): two more oscillators a little above and below. They beat
  slowly against the first - a string section, a fat synthesizer.
- `filter` (`[from Hz, to Hz, resonance, seconds]`): every note goes through a resonant
  low-pass whose cutoff travels from the first frequency to the second in about that many
  seconds. Closing and resonant, it is the squelch of an acid bass; opening slowly, it is
  brass, or strings that swell.
- `room` (0 to 1, or `[amount, size]`): the track is heard in a room - a cluster of early
  echoes. With `echo` after it, a hall.

```json
"strings": {"wave": "saw", "detune": 9, "attack": 0.3, "release": 0.6, "filter": [500, 2400, 0.1, 0.6],
            "room": [0.5, 1.5], "volume": 0.2},
"acid":    {"wave": "saw", "filter": [2400, 280, 0.85, 0.12], "drive": 0.3, "gate": 0.6, "volume": 0.4}
```

A note can also move (since 2.1). `c3>c5:16` slides from one pitch to the other over its
length; `c4@5` plays at a level between `@0` (silent) and `@9` (full, the default);
`c4@2>9:16` swells from level 2 to level 9; `c3>c5@2>9:16` does both and is a riser. Levels
work on chords (`[c4 e4 g4]@6:8`) and drum hits (`k@4`) too. On the `noise` wave a slide
sweeps the hiss. Songs that use none of this sound exactly as they did.

Sound effects are played by name (`{"sfx": "unlock"}`). Built in: `select back error save
step door airlock locked unlock pickup drop open use craft read computer power teleport
secret coin quest quest_done levelup heal trap alarm encounter hit crit miss hurt guard
focus special flee enemy_down win lose explosion`. A level also plays `footstep` at every step, which is
silent unless the game or its sound set defines it; a step into toxic floor plays `wade` (or the footstep, if
there is no `wade`), and `acid_burn` when the floor burns the player; `push` when a crate is pushed, `plate` when a
pressure plate goes down or comes up, `lift` when a lift rides. Add or replace them in `sounds.json`:

```json
"zap": {"wave": "saw", "freq": [900, 120], "dur": 0.2, "vol": 0.4},
"fanfare": {"notes": "c5 e5 g5 c6:3", "tempo": 480, "wave": "square"},
"door": "sounds/my_door.wav"
```

Rendered audio is cached in `~/.cache/clio/audio` (override with `CLIO_CACHE`).

### Sound sets

A game can have more than one set of sound effects. Every `sounds.NAME.json` in the game's folder is a set
(or list them in `game.json`: `"sound_sets": {"loud": "audio/loud.json"}`). A set holds sounds by name, written
as in `sounds.json`; a name it does not have plays the game's own sound. A sound in a set may also be just the
name of another sound.

Which set plays: `--sounds NAME` on the command line, else `CLIO_SOUNDS=NAME`, else `"sound_set"` in
`game.json`, else the game's own. In the game, `sound set` lists the sets and `sound set NAME` changes to one
(`sound set default` goes back); it works inside first-person levels too, so the same fight can be heard both ways.

### Sounds from Ballistic

A sound can come from the engine of [Ballistic Foley Lab](https://github.com/eigensoundlab/ballistic),
which models shots, ricochets, blasts, impacts, electric arcs and energy fields from physics: the muzzle blast
and the bullet's crack, the room it is fired in, the plate it hits. Name one of Ballistic's presets (they are
listed in its page, and in `engine/audio/ballistic/engine.js` under `PRESETS`) and change what you need:

```json
"pistol":   {"ballistic": "pistol", "p": {"D": 0, "target": "none", "env": "indoor"}, "action": "game",
             "vol": 1.0, "variations": 6, "length": 1.2},
"hit_wall": {"ballistic": "ricochet", "p": {"D": 2, "env": "indoor"}, "action": "game", "vol": 0.7},
"zap":      {"ballistic": {"kind": "discharge", "dcEnergy": 2, "dcDist": 3}, "fallback": "error"}
```

- `ballistic`: a preset, or an object of parameters (Ballistic's names; `--check` knows them all).
- `p`: parameters to change in the preset: `D` is the distance to the listener in metres (0: the one who
  fires), `env` the place (`indoor`, `urban`, `forest`, `field`, `valley`...), `target` or `tgMat` what the shot hits.
- `action`: Ballistic's finishing for games - `"game"` adds punch, weight and loudness; also `"block"`,
  `"slow"`, `"far"`, or an object of its action parameters (`punch`, `weight`, `drive`, `bite`, `tail`, `swell`,
  `width`, `loud`, `slowmo`). Without it the sound is the physics alone, quieter beside chip sounds.
- `vol`: the loudest point, 0 to 1 (default 0.7). `length`: seconds, cut with a short fade (default 2.5).
  `channels`: 1 for mono (default 2).
- `variations`: how many takes, 1 to 12 (default 4). Each is the same event with other chance; shots in a row
  play different takes and never the same one twice running.
- `fallback`: the sound to play when Ballistic cannot (see below). Without it, the game's own sound of the same
  name plays.

Ballistic's engine is JavaScript, so the takes are rendered by [Node.js](https://nodejs.org) when one is
installed (`CLIO_NODE` points at another; `CLIO_NODE=none` turns it off). Faster, and without Node: its C port,
[Ballistic Engine](https://github.com/eigensoundlab/ballistic-engine). `python clio.py --get-ballistic` installs
it: it downloads the release CLIo follows for your machine (Linux x64 and arm64, macOS, Windows x64 and arm64,
Android/Termux), checks it against the checksum CLIo keeps, and puts only the library (with the engine's LICENSE
and NOTICE) in your data folder - `~/.local/share/clio/ballistic/` (`%APPDATA%\clio\ballistic\` on Windows,
`CLIO_DATA` to put it elsewhere), never in CLIo's folder or a game's. A library of your own build still comes
first: `CLIO_BALLISTIC_LIB` pointing at it, or put in `engine/audio/ballistic/lib/` (which git ignores).
CLIo then renders with it every kind it has ported (all but rockets and rotors since 0.3.0) and uses Node for the
rest; the takes are the same either way. `sound` says which renders what. A game starts rendering every take
of the set in the background as soon as it begins, the first take of each sound first; the takes are kept in
the audio cache, so a second run renders nothing. A typical shot takes 10 to 50 ms to render.

To ship a game whose players may not have Node, bake the takes into it:

```bash
python clio.py rootless --bake-sounds ballistic     # into games/rootless/sounds/ballistic/
```

They play without Node, at the effects volume. Bake again after changing a sound: with Node, a changed sound
is rendered fresh rather than played from an old bake. With neither Node nor baked takes, the fallback plays,
so a game never goes silent for want of Node. `sound` in the game says what was found.

First-person levels play three more sounds a game may give, all silent unless it does: `hit_body` when the
player's shot or blow lands (a monster's `"sounds": {"hit": ...}` replaces it), `hit_wall` when a shot meets a
wall or misses, and `fly_by` when a monster's shot goes wide of the player. RØØTLESS's `sounds.ballistic.json`
gives Ballistic's sounds to its weapons, hits, fire, souls, explosions and Cron:

```bash
python clio.py rootless --sounds ballistic
```

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
  "boss": {"name": "Remains of the Hollow King", "on_defeat": [{"add_item": "heart_root"}]}
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
| `battle` | `"cards"`: every fight in this mode is a [card battle](#card-battles). |

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

### On the web

The same editor runs without CLIo installed, from a web address: the repository itself
is the site (<https://eryxgames.github.io/CLIo/>). There the page has no program to talk
to, so it runs the engine itself - Python in the browser - and everything above works
the same: the check as you type, the map, the fights, the walkthroughs.

- *Open a game folder* reads the game from your computer. In Chrome and Edge the editor
  then saves straight back into that folder, backups included, after the browser has
  asked you to allow it. In Firefox and Safari a page cannot write into a folder: *Save*
  keeps the game in the browser and *Download game* gives the folder back as a zip.
- *Open a zip file* takes a game as *Download game* makes it.
- *A new game* starts from the starter template; the two demo games can be opened too.

A game opened without a folder to save into - a zip, a new game, a demo, or any game in
Firefox or Safari - is **kept by the browser** each time you save, and waits under
*Carry on with* on your next visit, on that computer and in that browser. *Forget it*
deletes that copy. It is a convenience, not a backup: clearing the browser's data removes
it, so download the game when a session's work matters.

The game never leaves your computer: the site is only files, and has nowhere to send
anything. The one thing fetched from elsewhere is Python itself (Pyodide, from the
jsDelivr CDN), the first time.

To have the site for your own copy of CLIo: on GitHub, *Settings - Pages - Deploy from a
branch*, branch `main`, folder `/ (root)`. Nothing is built. The page fetches the
engine's files by name from `engine/editor/web/manifest.json`; after adding or removing
a module run `python -m engine.editor.hosted` to renew that list (a test says so when it
is out of date).

**On itch.io, or any host that takes an upload.**

```
python -m engine.editor.hosted --pack clio-editor.zip
```

writes the site as one zip - the page, the engine, the starter and the demo games, about
a hundred files - with `index.html` at the top, which is what an itch.io HTML project
wants (*Kind of project: HTML*, upload the zip, *This file will be played in the
browser*). There the editor is shown inside itch.io's page, and a page inside another
site's page may not ask for a folder to write into; so games are kept in the browser as
above, and the start screen offers to open the editor in a tab of its own, where saving
into a folder works again. itch.io serves every project from one shared address, so the
games the browser keeps there are not walled off from other projects' scripts: fine for
game data, and one more reason to download what matters.

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
  unless you switch that off, changes the colours and the size (up to 64 x 64), and can
  grow a fresh creature from any words.
- *Drawings* adds more drawings to play in turn - *Copy this drawing* starts the next one
  from the current, and the one before shows faintly while you draw. *Drawn as* picks the
  [style](#pictures-in-the-styles), *Animation* an effect, and the speed and the number of
  times the drawings play are just above the board.
- *As the game draws it* is the picture drawn by the engine, in its style, on a dark
  screen; *Play the animation* plays it.
- *Grow a monster* grows an enemy for a [first-person level](#first-person-levels) on a
  body plan - biped, beast, floater, crawler or brute - as tall as you say, from the words
  above it; it replaces the drawing and makes its far versions.
- *From a picture* (for sprites and tiles) makes a drawing from any picture file - a PNG,
  a JPEG, a screenshot. A pixel picture drawn bigger (each pixel a square) comes back to
  its own pixels; anything higher than *Height* is made smaller; it gets at most *Colours*
  colours, the sprite's own letters kept for the colours it already has. *Clear the
  background* takes away the commonest colour round the picture's edges, as far as it
  reaches; a click on the picture clears the colour there too (a checkerboard needs a
  click on each of its colours), and dust left apart is swept away. *A dark outline* draws
  a line round it, as the game's own monsters have. *Use it* puts it in place of the
  drawing shown (the next drawings keep the sprite's size). Nothing is written until you
  save; drawn pictures are best brought in at their own size, painted ones need the most
  touching up.
- *Far away, in a first-person level* shows the sprite one to six cells away as a level
  draws it. *Letters to keep far away* (`keep`) are the colours that must survive the
  shrinking - eyes, a mouth. *Keep them, to draw over* stores the far versions in the
  sprite (`lod`) so they can be painted pixel by pixel like the drawing; *Make them again
  from the drawing* replaces them; *Let the game make them* removes them, and the engine
  makes them when the level starts.

Banners in game.json (*The title drawn in a graphic style* and the others) are drawn the
same way, as you type, on a desktop, a phone or a 24-column screen.

What counts as text is a rule of thumb (`engine/editor/texts.py`): names, titles and
anything called `..._text` always; otherwise a string with a space in it, unless its key
is known to hold something else. Songs, sounds and sprites are left out. A choice written
as a key - `{"Ask about the ship": "..."}` - has its answer in the table but not the
question, since a key cannot be changed without changing what refers to it.

## First-person levels

A scene can hold a level: a grid the player walks through, seen through his eyes and
redrawn in place (frame mode), with monsters that move and shoot a beat at a time.
`games/rootless` is a complete example.

```json
{"id": "boot_sector", "name": "Boot Sector", "level": "e1m1",
 "on_level_exit": [{"story": "e1_end"}, {"win": "outro_demo"}]}
```

Entering the scene hands the screen to the level. When the player throws the exit switch,
`on_level_exit` runs (any effects: `goto` the next level's scene, a story text, `win`);
when he dies the game is lost (`death_text` names the text); quitting leaves the game as
quitting always does. Health, armour, weapons and ammunition go on to the next level; keys
do not. Each level's numbers (kills, items, secrets, beats) are kept in the variable
`levels`.

**Time** moves in beats: a step, a shot, opening a door or `w` (wait) is one beat, and
then every monster moves. Turning to look round is free. On a real terminal the level is
drawn as a picture and keys act at once; piped, with `--scroll`, or on a screen smaller
than 40 x 18 it is played in scrolling text with a small map that turns with the player,
so it can be tested and played anywhere.

### levels.json

```json
"e1m1": {
  "name": "Boot Sector", "title": "E1M1   BOOT SECTOR",
  "intro": ["Episode 1: Roasted in the Shell."],
  "par": 140, "music": "boot_sector", "facing": "n",
  "map": ["#####E#####",
          "#...C.....#",
          "##X#####1##",
          "#..k..@..D#",
          "###########"],
  "legend": {"X": {"door": true, "key": "x", "closes_on": "arena", "opens_on": "boss_escaped"},
             "1": {"wall": "steel", "opens_on": "keyroom"},
             "k": {"item": "key_x", "on_pickup": "keyroom"},
             "D": {"monster": "daemon", "wake_on": "keyroom"},
             "C": {"monster": "cron", "wake_on": "arena"}, "m": "medkit"},
  "events": {"keyroom": "The walls grind open."}
}
```

The map is rows of characters, north at the top. Without a legend entry a character means:

| Character | Meaning |
| --- | --- |
| `#` `%` `=` | wall: steel panels, terminal screens, hazard stripes (a space is a wall too) |
| `.` | floor; `~` toxic floor (hurts every beat spent on it, `toxic_damage` in `first_person`, unless the player wears boots) |
| `@` | where the player starts (`facing`: n, e, s or w) |
| `+` | a door: walk into it (or press Enter, `use`) to open it |
| `R` `W` `X` | a door that needs the r, w or x key (drawn red, yellow or blue, marked `r--` `-w-` `--x`) |
| `S` | a hollow wall: a secret that opens to a punch (the fist, weapon 1) |
| `P` | a dented vent: a secret that opens to a gunshot with nothing else to aim at |
| `E` | the exit switch, on a wall |
| `&` | a crate: walk into it to push it (see [Things that move](#things-that-move)) |
| `^` | a pressure plate, named `plate` |
| `:` | oil on the floor: slippery, and it burns (see [Floors and fire](#floors-and-fire)) |
| `;` | slick floor (spilled coolant): what moves on to it slides on |

A legend entry is either the id of a monster or an item (`"m": "medkit"`), or an object:
`{"monster": id}` or `{"item": id}` on a floor cell; `{"wall": tile}`; `{"door": true,
"key": "x"}`; `{"toxic": true}`; `{"panel": "fist"}` or `{"panel": "shoot"}`;
`{"exit": true}` (or `{"exit": "secret"}`, see [The end of a game of levels](#the-end-of-a-game-of-levels));
`{"switch": event, "label": "GATE"}` - a switch in a wall: Enter throws it (once) and sets
off the event, and its label is shown on it.
A floor cell can also have `"floor"` and `"ceiling"` tiles, a surface: `"oil": true`,
`"slick": true` or `"conveyor": "e"` (a belt), and `"sky": true` (open to the sky, see
[Under the sky](#under-the-sky)). The engine's
tiles are `steel`, `screens`, `screens2`, `hazard`; a game can draw its own (see
[Tiles](#tiles)). `"floor"` and `"ceiling"` on the level itself lay a tile everywhere
(toxic floor keeps its own look unless its cell names a tile).

**Events** tie a level together. They have names you choose; a cell with
`"on_enter": name` sets one off when the player steps on it, an item with
`"on_pickup": name` when he takes it. Then every cell with `"opens_on": name` opens (a
wall becomes floor; a door opens), every open door with `"closes_on": name` slams shut and
stays sealed, and every monster with `"wake_on": name` wakes. A door with `opens_on` and no
key is sealed until then. `events` gives the line shown when one happens. A boss's escape
sets off its own event (see below). Monster closets, traps and doors that open when a
fight is won are all made this way.

Monsters are named on the map in the order a player meets them: the nearest zombie is `z1`.

### Under the sky

Cells with `"sky": true` have no ceiling: the level's sky is over them - courtyards, a
landing pad, a swamp. The sky is drawn behind everything: a gradient from the horizon up,
a sun or a planet, clouds that drift a little every beat, stars, and ridges along the
horizon - the far ones stay put, the near ones move a little as the player steps sideways.
A quarter turn is a quarter of the sky. Walls stand under it as they are (rock, reeds - a
tile with clear pixels shows the sky through it), and the level's fog still darkens what is
far, so a sky at dusk or at night sits best with it.

```json
"sky": {"top": "#0b1022", "horizon": "#c46a44", "stars": 0.012,
        "sun": {"at": 0.18, "height": 0.42, "size": 0.32, "color": "#d9b07a", "bands": "#a8744a", "glow": 0.35},
        "clouds": {"color": "#3a2c44", "amount": 0.35},
        "ridges": [{"color": "#2a2236", "height": 0.42, "seed": 3, "rough": 0.7},
                   {"color": "#14121a", "height": 0.2, "seed": 11, "near": 1.0}]}
```

`sun`: `at` is where it stands round the horizon (0 north, 0.25 east, 0.5 south, 0.75 west),
`height` above the horizon (0..1 of the sky), `size`, `color`, `bands` (a planet's stripes)
and `glow` round it. `ridges`, far to near: `height` (0..1 of the sky), `seed` (another
seed, another skyline), `rough`, `near` (0..1: how much it moves as the player does).
`stars`: how many (0.01 is a clear night). Everything has a default: `"sky": {}` is a dusk.

### Open land

A level can stand on open land: hills, lakes, a coast, as far as one can see. Give it a
`"land"` object. The map is then optional. It is a camp or a compound set down on the land
at `at`; the ground under it is flattened, and every space and every cell outside the map is
land. The level's size becomes the land's `size`.

```json
"land": {"size": [112, 112], "seed": 4207, "scale": 30, "height": 5, "sea": 0.42, "ridges": 0.25,
         "at": [90, 10], "start": [16, 80], "haze": 60,
         "water": {"color": "#2a4a3c", "deep": "#14261f", "toxic": true, "shallow": 0.05},
         "biomes": [{"name": "fen", "below": 0.3, "color": "#3f4c2c", "color2": "#4c5a30", "char": ".",
                     "props": [{"sprite": "prop_reeds", "density": 0.1, "size": 0.75}]},
                    {"name": "rock", "below": 2, "color": "#5c5850", "char": "^",
                     "props": [{"sprite": "prop_crystal", "density": 0.05, "solid": true}]}],
         "landmarks": [{"at": [95, 8], "model": "relay_mast", "solid": true}],
         "things": [{"at": [80, 60], "monster": "hopper_fens"}, {"at": [52, 80], "item": "armor", "secret": true}],
         "scatter": [{"monster": "hornet", "count": 16, "on": ["water", "deep water"], "away": 14},
                     {"item": "medkit", "count": 5, "on": ["fen"]}]}
```

**The ground** is worked out from the numbers, not stored: the same `seed` makes the same
land every time.

- `scale` is how many cells a hill spans.
- `height` is the highest ground, in walls' heights.
- `sea` (0..1 of the heights) is where the water starts.
- `ridges` (0..1) is how much of the land is mountain ridges.
- `rough` is how broken the ground is.
- `warp` (0..1) is how far the shapes are twisted.

Because the ground is a sum of the coordinates, it goes on past the level's `size`: the
picture draws it to the horizon (`view` cells off). The level itself, the part one can walk
and that the rules keep track of, is `size` cells across. At its edge, hills rise (`"edge":
"rim"`) or the land goes on flat as it is (`"open"`), with no way out. An endless world would
load the land in pieces as one walks; the land is ready for that, and the rules may follow.

**Water** lies flat at the sea line. It mirrors the sky, and it is `toxic` if you say so.
`shallow` (0..1 of the heights) is how far under the line one can still wade. Deeper water
stops a walker.

**Slopes.** A slope steeper than `climb` (walls' heights per cell, 0.55) is a cliff: it stops
a walker too, and is drawn in the `cliff` colour. Drones that float go over water and cliffs.
A flying machine flies at `altitude` (2.6) over the ground.

**Sight.** Hills hide: a monster behind a ridge does not see you, and you do not see it.

**Biomes** colour the land by height above the water, from low to high: `below` (0..1) is
where each one ends. Each has a `color` and a `color2` (mixed in patches) and a `char` for
the text view. It can be `toxic`. Its `props` stand about on it: a `sprite` or a `model`, a
`density` (0..1: how many cells have one) and a `size`. A `solid` prop (a tree, a rock) is in
the way like a cliff is. The default biomes are shore, grass, forest, rock and snow.

**Landmarks** are models (or sprites) that stand far off and are seen from far: a mast, a
wreck, a tower. Each has `at`, `size`, `turn` (degrees) and `lift` (walls' heights up or down).
A `solid` landmark blocks its cell. Landmarks show on the map from the start.

**Things** put a monster or an item at a place; `"secret": true` makes the place a secret.
**Scatter** puts `count` of a monster or an item about the land: `on` the biomes named
(`"water"` and `"deep water"` are names too), `near` a place within a `radius`, and at least
`away` cells from the start. The same seed puts them in the same places every time.

The land's `start` is where the player starts, unless the map has an `@`. Also: `see` (how
far things are drawn, 24), `props_view` (18), `haze` (how far off half a colour is haze, 70),
`haze_color`, `pad` and `blend` (the height of the ground under the map and how far it blends
into the land), and `sky_ridges` (draw the sky's ridges as well, which the land's own hills
otherwise replace).

The picture of open land is in true perspective: the ground is drawn first, near to far,
then what stands on it, and far things fade into the haze. The first look round builds the
ground near by (about half a second). After that a frame takes about as long as a room's.
The level bot finds its way over open land by working the way out from its goal once and
then following it.

### Levels without end

A level with a `"world"` block is never built whole: it is made a chunk (16 x 16 cells) at a
time, round the player, as he goes. Its monsters and items wake with the chunks near him
(`"awake"`: 2 chunks each way) and go to sleep where they stand when he has gone on. What
changed in a chunk - a door opened, a monster hurt or moved, an item taken - is kept for when
he comes back. A chunk nobody touched is forgotten and made again, the same, if he does.
Cells further off than `"keep"` chunks (6) are forgotten too, keeping only what changed, so a
long journey keeps little. The same seed makes the same world; `"seed": "run"` makes a new
one every game (a save keeps the seed). The map's characters, the level's `"legend"` and its
`"floor"` and `"ceiling"` work as in any level; a world has no `"map"`.

**Open land without end** (`"kind": "land"`): the level's `"land"` (see Open land) going on
for ever, with sites - small maps - set down on it.

```json
"world": {"kind": "land", "seed": "run", "awake": 2,
          "sites": [{"name": "start", "at": [0, 0], "map": ["##...##", "#.....#", "...@...", "##...##"]},
                    {"name": "relay", "at": [180, -150], "map": ["#####", "#.E.#", "##.##"],
                     "landmarks": [{"at": [2, -2], "model": "relay_mast", "solid": true}]},
                    {"name": "camp", "chance": 0.07, "away": 30, "spacing": 2,
                     "map": ["#####", "#f.m#", "##.##"], "legend": {"#": {"wall": "fence"}, "f": "fuel", "m": "medkit"}}],
          "spawns": [{"monster": "scout", "per_chunk": 0.12, "on": ["fen", "heath"], "away": 30, "more": 0.003},
                     {"item": "stimpack", "per_chunk": 0.3}]}
```

- **Sites** with `"at"` stand there, measured from the start (the middle of the site's map);
  the start itself is the `@` in one of them, or the world's middle. Such places are known
  from the start: the level bot can head for their exit, and their landmarks stand on the
  horizon. A world of land needs an exit (`E`) in one of them.
- **Sites by chance** have a `"chance"` (0..1) of standing in a chunk at least `"away"` cells
  from the start, never within `"spacing"` chunks of another, and only where the ground is
  dry and near the start's height. They are at most 14 x 14; `"weight"` makes one kind more
  common than another. The ground under every site is flattened, at the start's height.
- A site's `"legend"` (over the level's) puts monsters and items in it; its `"landmarks"` are
  measured from its map's corner.
- **Spawns** put monsters and items about each chunk as it is first woken: `"per_chunk"` of
  them on average, `"on"` the biomes named (`"water"` and `"deep water"` are names too), at
  least `"away"` cells from the start. With `"more"`, there are more the further from the start
  (so many more a cell of distance), up to `"most"` times as many (3).
- `"things"` put a monster or item at a place (`"at"`, from the start).

**A dungeon without end** (`"kind": "dungeon"`): a room to a chunk (or a crossing of
corridors), joined to the chunks round it through gaps in their edges.

```json
"world": {"kind": "dungeon", "seed": "run", "rooms": 0.8, "room_size": [4, 11], "links": 0.7,
          "doors": 0.35, "pools": 0.2, "walls": ["#", "#", "%", "|"], "depth_every": 2,
          "exit": {"away": 6},
          "monsters": [{"monster": "zombie", "weight": 3}, {"monster": "daemon", "from": 3}],
          "per_room": [0, 2], "more": 0.5, "most": 6,
          "items": [{"item": "medkit", "weight": 2}], "items_per_room": [0, 1]}
```

`"rooms"` is the chance a chunk has a room, `"room_size"` how big (cells), `"links"` the chance
two chunks are joined, `"doors"` the chance of a door at a room's mouth, `"pools"` of acid in a
room, `"walls"` the map characters a room's walls are drawn with (one a room). It gets deeper
every `"depth_every"` chunks from the start: monsters and items with a `"from"` depth come in
then, and each room has `"more"` monsters a depth more (at most `"most"` more). The exit is in a
room `"away"` chunks off, in a direction the seed chooses.

### Dungeon floors from a seed

A level with a `"generate"` block makes its map each time it is built: rooms set about the
floor, joined by corridors (all of them, and a few more ways round), doors at some of their
mouths. The player starts in one room; the exit is in the room furthest from it.

```json
"generate": {"type": "dungeon", "seed": "run", "depth": "swap_depth", "size": [44, 32],
             "rooms": [7, 10], "room_size": [4, 8], "loops": 0.2, "doors": 0.45,
             "key": {"door": "W", "item": "key_w"}, "secret": "armor", "pools": 0.25,
             "walls": ["#", "%"], "guard": "kswapd",
             "monsters": [{"monster": "zombie", "weight": 3}, {"monster": "daemon", "from": 3}],
             "per_room": [0, 2], "more": 0.4, "most": 6,
             "items": [{"item": "medkit", "weight": 2}], "items_per_room": [0, 1]}
```

- `"key"`: the exit's room is shut behind locked doors (`R`, `W` or `X`), and the key lies in
  a room one can reach without it.
- `"secret"`: an item in a closet behind a fist panel, off one of the rooms.
- `"guard"`: a monster in the exit's room.
- `"loops"` (0..1): how many more ways round there are than the fewest that join the rooms.
- `"seed"`: `"run"` for a new floor every game (a save keeps it), or a number; otherwise the
  game's seed.
- `"depth"` names a game variable: how deep this floor is. A scene can go down a floor by
  adding to it and going to itself again:
  `"on_level_exit": [{"var": ["swap_depth", "+", 1]}, {"goto": "deep_swap"}]`. The level's
  title page says which floor it is; monsters and items with a `"from"` depth come in, and
  rooms hold `"more"` monsters a floor (at most `"most"` more).

### Things that move

The rules move a cell at a time, a beat at a time:

- **Crates** (`{"crate": true}`, `&`): walking into one pushes it a cell on, if nothing
  is behind it (a wall, a monster, an item, a pad or a lift). A crate blocks the way, sight
  and shots - it is cover. Pushed into toxic floor it sinks and makes a step to stand on.
  A **container** (`{"crate": "heavy"}`) is a crate only a vehicle can shove; blasts do
  not throw it, and it does not slide. The game's sprite `container` draws it.
- **Pressure plates** (`{"plate": name}`, `^`): down while something heavy stands on it -
  a crate, the player, a monster that does not float. A door or a wall with
  `"open_while": name` is open only while a plate of that name is down, and shuts again
  when nothing holds it (not on top of someone). The level's `events` text for the name is
  shown the first time. A crate on the plate keeps a door open: the old puzzle.
- **Teleporter pads** (`{"teleport": name}`): stepping on one takes the player to the next
  pad of that name in the map's order; `"arrive": true` only receives, `"facing"` turns the
  player on arrival. The picture dissolves into braille dots and back. A monster standing
  on the pad the player arrives at dies of it.
- **Lifts** (`{"lift": name, "deck": n}`): Enter while standing on one rides to the other
  lift of that name, down if its deck is lower; the picture slides away in dots and the
  shaft goes by. `"exit_ride": "down"` (or `"up"`) on a level ends it in a lift ride when
  the exit switch is thrown.
- **Blasts and the shotgun**: a barrel's blast throws crates and monsters next to it a cell
  further away; the shotgun at point blank throws its target a cell back. Monsters that do
  not float burn on toxic floor like the player.
- **A secret area**: a floor cell or a door with `"secret": true` counts as a secret when
  the player stands in it.
- **Barrels** roll: walking into one pushes it a cell on, like a crate - into a crowd of
  monsters, or into the acid.
- **Monsters use teleporters**: a pad that leads closer to the player is a step on their
  way, and one that walks on to a pad is taken to the next, like the player.
- **Vehicles**: a monster with a `"vehicle"` block (and the `barrel` attack, so it stands
  still and goes up when it is wrecked) is a machine to ride. Walking into it climbs in;
  Enter, or `out`, climbs down behind or beside it, and it stays where it stands. While
  riding, the picture shows its cage and its `cockpit` sprite instead of a gun; Space is its
  `claw` (damage to what is right ahead, which is thrown a cell back and loses a beat; a
  hollow wall breaks); walking into a monster treads on it (`stomp` damage - crushed, if
  that kills it, else thrown back); it shoves containers, and with `"wades": true` (the
  default) acid does not hurt it. It goes through no doors and onto no pads or lifts. What
  would hurt the player hurts it, armour or not; at 0 it throws him clear and bursts for
  its attack's `damage`. Its texts are `board`, `leave` and `wreck`; its `sounds` are `step`,
  `board` and `claw`.
- **Machines that fly on fuel**: `"fly": true` flies over acid, water and what is on the
  floor, treads on nothing, and climbs down only beside dry floor. `"fuel"` (its tanks, in
  beats, usually 0) makes it need fuel: an item with `"pickup": {"fuel": 12}` is carried
  and poured in on boarding (or at once, if picked up while flying); a dry machine will
  not lift. From its first move it burns a beat of fuel every beat - the status line and
  the gauge on its dashboard show what is left - and when the last of it is gone it comes
  down: `"on_empty": "exit"` ends the level there (the ride is the level's end), else it
  just stops. `"gun"` is a weapon (`damage`, `burst`, `pellets`, `sound`, `text`) that Space
  fires with no ammunition; `"canopy": "#4b5047"` draws a canopy's frame and a dashboard
  instead of a cage. Once it lifts, the player sees from higher up - `"eye"`, of a wall's
  height (0.74; standing is 0.52) - swaying a little, rising as it lifts off and sinking
  as it comes down. Its texts add `start` and `empty`, its `sounds` `start` and `empty`.
- **Balls** (a monster of `"kind": "ball"`): heavy, and they roll. Walking into one shoves
  it: it rolls `speed` cells a beat (2) for `roll` cells (8), and on until something stops
  it. What it rolls into takes `crush` damage - and if that kills it, the ball rolls on;
  another ball is knocked on and this one stops; a barrel goes off; a hollow wall breaks
  and the ball rolls through; in acid it sinks and makes a step. It holds a plate down,
  rides belts, takes no harm (shots ping off it), and a blast beside it sets it rolling
  away. On the map, `{"monster": "xantrium_core", "wake_on": "chute", "roll": "s"}` waits
  for the event, rumbles for a beat, and then rolls that way - with `"roll": 99` and
  `"speed": 1` it rolls a cell a beat until a wall stops it, one step behind a player who
  does not stop.

```json
"xantrium": {"name": "Xantrium ball", "tag": "x", "model": "xantrium_ball", "kind": "ball",
             "size": 0.85, "roll": 8, "speed": 2, "crush": [26, 40]},
"hopper": {"name": "Swamp Hopper", "tag": "H", "model": "hopper", "hp": 220, "kind": "barrel",
           "attack": {"kind": "barrel", "damage": 30},
           "vehicle": {"fly": true, "fuel": 0, "on_empty": "exit", "canopy": "#4b5047",
                       "gun": {"damage": [9, 15], "burst": 2, "sound": "hopper_gun", "text": "DAKKA."}}}
```

```json
"loader": {"name": "cargo loader", "tag": "v", "sprite": "loader", "hp": 150, "size": 1.35, "kind": "barrel",
           "attack": {"kind": "barrel", "damage": 30},
           "vehicle": {"claw": [30, 50], "stomp": 40, "cockpit": "w_loader", "wades": true,
                       "board": "You strap into the loader's cage. Space: claw. ...",
                       "sounds": {"step": "loader_step", "board": "loader_board", "claw": "claw"}}}
```

### Floors and fire

- **Slick floor** (`{"slick": true}`, `;`): the player, a pushed crate or a rolled barrel
  that moves on to it goes on in the same direction until something stops it - a wall, a
  crate, a monster, or dry floor, where it stops. What lies on the way is picked up as the
  player goes over it. A puzzle of slick floor is a puzzle of where you can stop.
- **Oil** (`{"oil": true}`, `:`): slick, and it burns. Fire on oil burns two beats longer
  and runs to the oil next to it every beat; burned-out oil leaves a scorched floor that
  is dry.
- **Fire** stays on a cell a few beats and hurts what stands in it every beat:
  `fire_damage` (6) in game.json's `first_person` for the player, the same for monsters
  that do not float; a barrel in fire goes off. A barrel's blast sets its cell and the oil
  next to it alight; a flamethrower's spray and its tanks bursting do too. Walls, acid and
  closed doors do not burn.
- **Belts** (`{"conveyor": "e"}` - n, e, s or w): at the end of every beat a belt moves
  what is on it a cell on, if there is room: the player, crates, barrels and monsters
  that do not float, and items. A belt into acid sinks the crates it carries (each makes
  a step); a belt can carry a barrel to where it is wanted. Belts are drawn as chevrons
  that move.

What only flies in the picture - debris and fire from a barrel, a monster torn apart by a
blast or by overkill, sparks where a shot hits a wall, acid splashing, a spent case thrown
from the gun, an item bouncing out of a dying monster - changes nothing in the game: it
is drawn from its own dice, so a level plays the same with it.

### monsters.json

```json
"zombie": {"name": "zombie process", "role": "hitscan grunt", "tag": "z", "sprite": "zombie",
           "hp": 20, "size": 1.0, "sight": 8, "drops": "clip",
           "attack": {"kind": "hitscan", "damage": [4, 9], "range": 8, "keep": [2, 6], "eager": 0.5},
           "sounds": {"sight": "zombie_sight", "attack": "pistol", "death": "zombie_death"},
           "death": "%s is reaped.", "man": ["What man zombie shows, line by line."]}
```

A monster sleeps until it sees the player (`sight` cells, default 8, with nothing in
between), hears a shot (gunfire carries 12 cells through open space), is hurt, or its
`wake_on` event comes. `size` is 1 for a person; `float` lifts it off the floor (0..1).
`awake: true` starts it awake.

| `attack.kind` | What it does |
| --- | --- |
| `hitscan` | takes aim for a beat (a red `!`), then fires: `damage`, `pellets`, `accuracy` by distance; it keeps to `keep` = [nearest, farthest] cells |
| `projectile` | raises a burning hand (an orange `!`), then throws fire at where the player stood; it flies `speed` cells a beat, so a step aside dodges it; `claw` when close |
| `melee` | comes `speed` cells a beat and bites when next to the player |
| `spawner` | every `every` beats makes a `spawn` (a monster id), up to `max` at a time |
| `barrel` | does nothing until hit; then bursts for `damage` on everything next to it (a vehicle has this attack too) |
| `flame` | levels its nozzle (an orange `!`) when the player is in its row or column within `range`, then sprays fire along the line: `damage` to everything in it, and the floor burns for `burn` beats |
| `cron` | a boss that works to a schedule (see below) |

More for the attacks:

- `"spinup": 2` on a `hitscan` attack: a minigun. While it sees the player its barrels
  spin up for that many beats (a red `!!`), then it fires every beat until it loses sight,
  and winds down. Break its line of sight - a wall, a crate - and it has to start again.
- `"move_every": 2`: a heavy one moves only every other beat (it still shoots).
- `"dodge": 0.35` on the monster: the chance it sidesteps a shot it sees coming, from two
  cells away or more (never at arm's length).
- `"burst_fire": 3` on the monster: when it dies, its cell and the four next to it burn for
  that many beats.

Fire that hits a monster turns it on the thrower: monsters fight each other.

**A boss** has `"boss": true` and ignores the player's shots until its fight starts (its
`wake_on` event). The `cron` kind follows a crontab:

```json
"attack": {"kind": "cron", "arena": 7, "rain_damage": [14, 20],
           "crontab": [{"every": 3, "do": "rain"},
                       {"every": 5, "do": "fork", "spawn": "soul", "count": 2, "max": 3}],
           "enraged": {"below": 0.5, "text": "...", "crontab": [{"every": 2, "do": "rain"}]},
           "escape": {"below": 0.15, "event": "boss_escaped", "text": ["...", "..."]}}
```

`rain` marks part of the floor of the arena (the cells within `arena` steps of the boss) a
beat ahead and burns it the next: rows, columns, diagonals, rings or a checkerboard,
always laid so that one step gets the player off it. `fork` makes monsters. The next jobs
and their countdowns are shown under the picture. Below `enraged.below` of its health the
boss switches to the faster crontab; below `escape.below` it does not die but escapes:
it says its lines, leaves, and sets off `event`. Its own `music` plays while it fights.
When the level is left after a boss escaped, the flag `<monster id>_escaped` is set
(`cron_escaped`), so a later level or ending can bring it back.

### Brains and squads

A monster with a `"brain"` chooses what to do each beat, instead of always coming at the
player. Without one it hunts as monsters always have.

```json
"kworker": {"...": "...", "brain": "soldier"}
"warden":  {"...": "...", "brain": {"kind": "heavy", "flank": 0.4, "flee": 0.1, "range": [3, 6]}}
```

It weighs its **tactics** and does the one that scores best:

| Tactic | What it does | `ps` |
| --- | --- | --- |
| close | goes at the player | R |
| keep | stays at its distance (`range`), where it can shoot | K |
| cover | gets out of his sight, then leans out to shoot (a gun) or waits for him (a claw) | D |
| flank | works round to his side or back, out of where he looks | F |
| retreat | hurt and frightened: back to its squad's leader, or away from him | B |
| hold | stays where it is (a guard by its post, a gunner with a good line) | H |
| search | it has lost him: goes where he was last seen, then back to its post | ? |

What weighs in: how hurt it is (below `flee`, a share of its health, it grows afraid), how far
he is, whether it can see him, whether he is looking at it, how many friends are near, the part
its squad gives it, and a little for keeping to what it was doing, so it does not dither. A
brainy monster only knows where the player is while it (or its squad) sees or hears him; it
goes on hunting where he was for `memory` beats, then searches, then gives up. It only shoots
what it can see.

The presets, by their weights (`close`, `keep`, `cover`, `flank`, `retreat`, `hold`):

| Brain | Fights like |
| --- | --- |
| `brute` | comes at you, works round your side; flees late |
| `skirmisher` | works round your side, keeps its distance, falls back when hurt |
| `soldier` | takes cover, keeps its distance, works round your side |
| `heavy` | keeps its distance, holds its ground, takes cover; flees late |
| `coward` | falls back when hurt, takes cover, keeps its distance |
| `assault` | comes at you, works round your side, takes cover now and then |
| `swarm` | comes at you and round you; it fights to the end, unless its pack breaks |

An object brain names a `"kind"` (a preset) and changes any of its weights, `"flee"` (0..1),
`"memory"` (beats) and `"range"` ([near, far] cells; a gun's is its `keep`, a claw's is 1). Its
manual page (`man kworker`) says how it fights. Barrels, vehicles, bosses and spawners have no
brain.

**What pays.** The choices are worth making because the rules reward them - for the player too:

- **Cover.** A shot at someone standing beside a wall, a crate or a closed door that the line of
  fire grazes hits the cover instead, half the time ("Your shot hits the cover in front of k2",
  "k1's shot hits your cover"). Walls along a corridor are no cover, nor is anything at arm's
  length; the corner a gunner leans out from is. Coming from another side takes it away.
- **Crossfire.** A squad's gun is a tenth surer for each other gun of its squad that has him in
  sight from another side (60 degrees off or more), two tenths at most.
- **Grenades.** `"grenades": {"count": 2, "range": 5, "fuse": 3, "blast": 30, "every": 6}` on a
  monster: it throws one at him (or next to him) when he is in cover from it, or out of its sight
  where it knows he is - never where one of its own would be caught, never when it has a clear
  shot. A fuse of 3 gives him two moves to get out of it.
- **Mines.** `"mines": {"count": 1, "item": "mine"}`: it lays one where it stands - a doorway, a
  corridor, or by the cover it holds - when he does not see it, and moves off. A mine is an item
  with `"pickup": {"mine": {"blast": 40}}`: it goes off under the player, is seen only within 3
  cells (6 in night goggles, a blinking red light), is never counted among the items found, and a
  blast next to it sets it off. A level can lay mines in its map too.

**Squads.** Monsters in a squad know what any of them knows: when one sees the player, all of
them know where he is, and when one is woken it calls the others (`k1 calls the others`). The
strongest still standing leads. Put monsters in one with `"squad"` in the legend (or in a
land's `"things"`), and give it a tactic in the level's `"squads"`:

```json
"legend": {"V": {"monster": "warden", "squad": "relay"}},
"squads": {"relay": {"tactic": "hold", "guard": 8},
           "auto": {"radius": 4}}
```

| Tactic | The parts it gives out |
| --- | --- |
| `pincer` (the default) | the leader holds the front; the rest work round both sides of him, by turns left and right |
| `fire_team` | half of those with guns pin him down from where they are; the rest flank |
| `hold` | every member keeps by its post until he comes within `guard` cells of the squad (6), or hurts one of them; then a pincer |
| `rush` | all of them at him |
| `assault` | those that fight close (claws, short guns: a `keep` ending at 4 or less) go in together; the long guns pin him down; grenades flush him out |
| `sweep` | bounding overwatch: two halves take turns every `bound` beats (3), one moving up while the other holds and covers it; they mine the doorways and cover they hold |
| `ambush` | every member is awake but still and silent where it was put, even when it sees him, until he comes within `guard` cells of one (3, heard if not seen), hurts one, or looks one in the face within 4; then all that can see him fire at once ("Ambush!") and fight on as a pincer |
| `swarm` | a pack keeps off and circles out of his eyes until `gather` of it (3) are near him, then all come in at once, each to its own side of him. Each one at him bites a quarter harder for every other one of the pack at him (up to three). When fewer than half are left the rest scatter |

`"memory"` is how long the squad hunts where he was last seen (12 beats). The parts only weigh
in each member's own choice: a hurt flanker still falls back. `"auto"` puts brainy monsters
that stand near each other into squads by themselves: a chain of them, each within `"radius"`
cells of the next (4); a lone one stays alone. A monster's `"squad_tactic"` in monsters.json
says how it fights in a squad (bugrats `swarm`, sweepers `sweep`): only monsters that fight
alike chain together, and the squad fights that way (else by the `"auto"`'s own `"tactic"`).

In a world without end, a site's legend squads and the `"auto"` squads are made a chunk at a
time (a squad never reaches over a chunk's edge), and a spawn can come as a **pack**: so many
together, one squad, with the pack's own tactic (or its monster's `"squad_tactic"`).

```json
"spawns": [{"monster": "scout", "per_chunk": 0.07, "pack": [2, 3], "tactic": "fire_team"}]
```

A room's monsters in a dungeon without end or a floor from a seed can come as packs too
(`{"monster": "bugrat", "from": 1, "pack": [3, 5]}`): the rest of the pack stand next to the
first, and the level's `"auto"` squads make them one.

A squad that was never woken is forgotten with its chunk and made again, the same, when he comes
back; a squad that fought is kept, asleep, with its chunk.

Everything a brain or a squad does comes from the level's state, never from a clock, so a game
played back (or on another machine) goes the same way. For games of moves and answers - a duel,
cards - the engine has a search too (engine/ai/search.py): minimax with alpha-beta, and Monte
Carlo tree search, both stopped by a budget of positions looked at, not by time.

### Pick-ups, weapons and the player

Anything lying in a level is an ordinary item (items.json) with a `pickup` block, taken by
walking onto it:

```json
"medkit":  {"name": "medkit", "pickup": {"health": 25, "sprite": "medkit", "text": "..."}},
"shells":  {"name": "shells", "pickup": {"ammo": {"shells": 4}, "sprite": "shells", "size": 0.45}},
"key_x":   {"name": "x key", "pickup": {"key": "x", "sprite": "key_x", "sound": "unlock"}},
"shotgun": {"name": "shotgun", "pickup": {"weapon": 3, "ammo": {"shells": 8}, "sprite": "shotgun"}},
"sudo_orb": {"name": "sudo", "pickup": {"power": "sudo", "beats": 15, "sprite": "sudo_orb"}},
"boots":   {"name": "hazmat boots", "pickup": {"power": "boots", "beats": 20, "sprite": "boots"}}
```

`health` (up to `max`, default the player's maximum; not taken at full health), `armor`
(armour soaks a third of every hurt), `ammo`, `key`, `weapon`, `power: "sudo"` (nothing
hurts the player for `beats`; the picture inverts), `power: "boots"` (toxic floor does not
hurt for `beats` spent on it - they wear down only there, show under the picture, and go
on to the next level), `power: "goggles"` (the level is drawn in braille dots, in green,
and secret walls show, for `beats` - F2 or `goggles` takes them off and puts them on again,
and the battery runs down only while they are on), `power: "magboots"` (kept; F3 or `mag`
switches them) and `power: "jetpack"` with `beats` of fuel (and `"jet": n`, a can of jet fuel):
see Getting about, below. `size` is the picture's size on the floor (0.55 if not said).

The weapons are in weapons.json, by the key that picks them (`"weapons"` in game.json's
`first_person` works too; weapons.json comes over it):

```json
{"1": {"name": "fist", "kind": "melee", "damage": [6, 14], "sprite": "w_fist", "sound": "punch", "text": "THUD."},
 "2": {"name": "pistol", "ammo": "bullets", "damage": [8, 14], "sprite": "w_pistol", "sound": "pistol"},
 "3": {"name": "shotgun", "ammo": "shells", "damage": [5, 9], "pellets": 7, "spread": 0.35, ...},
 "4": {"name": "chaingun", "ammo": "bullets", "damage": [7, 12], "burst": 2, ...}}
```

The player's start is in game.json:

```json
"first_person": {
  "view": "pixel",
  "start": {"health": 100, "weapons": ["1", "2"], "weapon": "2",
            "ammo": {"bullets": 50, "shells": 0}, "max_ammo": {"bullets": 200, "shells": 50}},
  "keymap": {"q": "turn left"}
}
```

A weapon is picked by its key: its id when that is a digit, or `"key"`. One key can hold
several weapons - Rootless puts the fist, the shovel and the chainsaw on 1: pressed, it takes
the best of them in hand (the last in weapons.json), pressed again the next. Typing a
weapon's id (`shovel`) takes it too. A melee weapon can have `"accuracy"` (the chance a
blow lands, 0.85 if not said), `"shove": true` (a blow throws the target a cell back, as
the shotgun does at point blank) and `"stagger": 1` (a monster it bites loses that many
beats: no aim, no step - not a boss); `"ready_sound"` plays when it is taken in hand.

```json
"shovel":   {"name": "shovel", "key": "1", "kind": "melee", "damage": [10, 20], "accuracy": 0.9, "shove": true, ...},
"chainsaw": {"name": "chainsaw", "key": "1", "kind": "melee", "damage": [9, 16], "accuracy": 1.0, "stagger": 1, ...}
```

A shot goes for what is in sight, nearest and most central first; a barrel only when it is
straight ahead and not at arm's length. `pellets` spread to monsters next to the target
(`spread`); `burst` fires (and spends) that many rounds a beat. What misses goes on into
the wall behind and leaves a bullet hole there, as does a shot into a wall (the last 60
holes of a level are kept).

Two more kinds throw something that bursts - a **blast**: everything within a cell takes
its damage (the player three quarters of it), crates and monsters are thrown a cell away,
oil next to it catches fire, grenades next to it go off, and the floor keeps a black mark.

```json
"5": {"name": "rocket launcher", "ammo": "rockets", "kind": "rocket", "damage": [30, 50], "blast": 40, ...},
"6": {"name": "grenades", "ammo": "grenades", "kind": "grenade", "blast": 50, "fuse": 2, "range": 3, ...}
```

A `rocket` flies the line to the target (or straight ahead) until it meets a monster, a
barrel or a wall: the one it hits takes `damage`, and then the blast. A `grenade` is
thrown `range` cells ahead, or to the row of the one aimed at; it bounces back off a wall
(a cell lost), drops before a monster, slides on slick floor, rides a belt, and bursts when
its `fuse` (beats) is out - thrown now, it goes off at the end of the next beat. Run out of
ammunition and the next gun is taken up, never one of these. The sprites `rocket` and
`grenade` draw them flying (the engine has its own). `view` is how the level is
drawn: `pixel` (half blocks), `dots` or `dots-fill` (braille); `--view` overrides it.
`"detail"` is how fine the floor and ceiling are: `"high"`, `"low"` (half width, half the
work - for a slow machine or a very wide window) or `"auto"` (the default: low only for a
very big picture); `--detail` overrides it. Walls are drawn 10 cells ahead; monsters, items
and shots count within 7.

**Faster pictures.** `python clio.py --get-picture` installs CLIo Picture, a small C library
([eryxgames/clio-picture](https://github.com/eryxgames/clio-picture)) that draws the open
land's ground and the sky over open cells, the rooms' floor and ceiling, and from release 0.4
keeps the whole picture in C from the floor to the cells - walls, pictures, shadows, the
triangles of models, colour changes, the cockpit - while CLIo still decides what is drawn
where; from 0.5 the models are projected and shaded there too, with the very `pow` and `exp`
your Python uses (CLIo hands them over and checks the shading against its own before it lets
the library draw models); from 0.6 it keeps each model's faces and is handed only the posed
corners and where the model stands, so a crowd costs about half as much (100 drones in sight:
15 ms a frame instead of 32). Along the bot's own games at 150 x 34: a room frame takes 4-5 ms
instead of 10-12 (in the dots view 6-7 instead of 40), open land and the hall of drones 7-8 ms
instead of 35-80 (in dots 10-15 instead of 95-140). It gives exactly what the Python gives - every pixel, height and dot the
same, to the last bit; CLIo checks some before it uses the library and keeps to the Python if
any differs - so a game plays and looks the same, only faster, and never needs it. It is found as Ballistic's library is: `CLIO_PICTURE_LIB` (`none` turns it
off), then `engine/picture/lib/` (a build of your own: `make` in its folder), then your data
folder (`~/.local/share/clio/picture/`, `%APPDATA%\clio\picture\` on Windows). Where no
release is listed for your machine, `--get-picture` says how to build it.

### Getting about: stairs, magnetic plating, the jetpack, the water

The levels are flat: a floor above another is another part of the map, and these take the
player from one to the other.

```json
"U": {"stairs": "deck", "deck": 0, "label": "UP"},  "D": {"stairs": "deck", "deck": 1, "facing": "w"},
"M": {"mag": "shaft", "deck": 1},                    "N": {"mag": "shaft", "deck": 2},
"o": {"pit": true, "floor": "pit"},  "w": {"deep": true, "floor": "water"},  "|": {"bulkhead": true}
```

- **Stairs** (`"stairs": name`) are a wall with steps in it (tile `stairs`): walked into, they
  take the player to the other end of the same name, up or down by their `deck`s, and he steps
  off on its open side (or the side its `"facing"` names). The view climbs past.
- **Magnetic plating** (`"mag": name`, tile `magwall`) is the same, walked up (or down) in
  **magboots**: the world tips on its side as the boots clamp, goes by, and tips back. Magboots
  also grip a slick floor (no sliding) and hold the player on a belt; F3 or `mag on|off`
  switches them, for a slide that is wanted.
- **A drop** (`"pit": true`) stops whoever walks: only fliers cross it, and monsters that float.
- **The jetpack** (F4 or `jet on|off`): up in the air with the gun in hand, over drops, acid,
  deep water and fire, a beat of fuel a beat. Down again only where there is something to stand
  on; when the fuel runs out it glides to the nearest edge within 4 cells - or he falls.
  `first_person` `"jet_eye"` (0.86) is how high the eye goes in rooms, `"jet_altitude"` on land.
- **Deep water** (`"deep": true`, tile `water`) is swum where the level (or `first_person`) says
  `"swim": true`; elsewhere it is too deep to wade. F6 or `dive` goes under, `surface` comes up:
  under water the picture takes the water's colour, the bottom (tile `seabed`) is below and the
  surface (tile `surface`) above, and the breath runs down - `"breath"` (20) beats, then it hurts
  (`"drown_damage"`, 8 a beat). **A bulkhead** (`"bulkhead": true`, tile `bulkhead`) is a wall
  down into the water: only a diver passes under it, to the water on its other side.
- **A submarine** is a vehicle with `"swim": true` (and `"dive": true`): boarded from the dock
  (walk into it), it goes where the water goes, dives and surfaces with F6, passes under
  bulkheads dived, has its own air, and is left by a dock (Enter or `out`, surfaced). Give it a
  `"gun"` of kind `rocket` for torpedoes, a `"canopy"` for the porthole frame, and `"float": true`
  so it sits on the water.

The level bot takes `jet`, `land`, `dive`, `surface`, `mag` and `unmag` among its goals, and
stairs and plating as map characters (it walks into them). RØØTLESS's **SIM-11: Deep Works**
(`--level sim11`) has all of these.

### Doors and gates: lockers, supply crates, bars, force fields, timed and one-way doors

```json
"L": {"locker": ["shells", "medkit"]},            "K": {"locker": ["chaingun"], "key": "w", "on_open": "alarm"},
"$": {"supply": ["clip", "clip", "stimpack"]},    "G": {"gate": true, "opens_on": "cells_open"},
"F": {"field": true, "opens_on": "emitter_down", "zap": 12},
"e": {"monster": "emitter", "on_death": "emitter_down"},
"T": {"door": true, "open_for": 6, "opens_on": "blast_run"},  "s": {"switch": "blast_run"},
"O": {"door": true, "from": "s"}
```

- **A locker** (`"locker": [item ids]`, or `true` for an empty one) is a wall with a door in it
  (tiles `locker`, `locker_open`; `locker_r` `_w` `_x` with a key). Walked into or used
  (Enter), it opens: what is in it falls at the player's feet and he takes what he can use -
  the rest stays on the floor where he stands. `"key"` locks it; `"on_open"` sets off an event
  (an alarm that wakes the barracks: `"wake_on"`). A mine among the items is a booby trap.
- **A supply crate** (`"supply": [item ids]`) is a crate (pushed, thrown by blasts, carried by
  belts - its contents go with it) that Enter pries open; it stays standing, open and empty
  (sprites `supply`, `supply_open`). `"key"` and `"on_open"` as for lockers.
- **Bars** (`"gate": true`, a door) are seen and shot through - by both sides - but never walked
  through until they open: by hand, with a key, on an event (`"opens_on"`), or while a plate is
  down (tile `bars`, `bars_r` `_w` `_x` with a key).
- **A force field** (`"field": true`, tile `field`) is seen and shot through too, and throws
  back whoever walks into it (`"zap"`, 10 by default; 0 only stops him). It turns off on
  `"opens_on"` and on again on `"closes_on"` (unless someone stands in it). A monster's map cell
  can say `"on_death": event`: kill the emitter, and the field drops. (An emitter is a monster
  with `"attack": {"kind": "none"}`: it neither moves nor strikes.)
- **A timed door** (`"open_for": beats`) shuts again that many beats after it opens - not on
  whoever stands in it (tile `door_timed`). Opened by a switch (`"opens_on"`), it is sealed
  again when it shuts and the switch can be thrown again: a run against the clock.
- **A one-way door** (`"from": "n"`, `e`, `s` or `w`) opens only from that side (tile
  `door_oneway`); once open it stays open.

Line of sight, shots and the automap go through bars and fields; monsters do not. The level bot
opens lockers and supply crates when they are among its goals (their map characters), and
plans a one-way door only from its side. RØØTLESS's **E1M5: User Space** has all of these.

### 3D models

Beside sprites, a level can draw low-poly 3D models: a monster, a vehicle or an item with
`"model": "NAME"` (an item in its `"pickup"`) is drawn from `models.json` instead of its
sprite, lit, turned the way it faces (where it went, or at the player when it aims), and
labelled as a sprite is. Model space: x to the right, y forward, z up; one unit is a cell
(and the room's height); the origin is on the floor under its middle.

```json
"drone_scout": {
  "materials": {"hull": {"color": "#6b717c", "metal": 0.8, "rough": 0.35},
                "paint": {"color": "#e07a1f", "metal": 0, "rough": 0.5},
                "eye": {"color": "#ff3020", "glow": 3}},
  "bob": [0.04, 2],
  "parts": [
    {"shape": "sphere", "size": [0.5, 0.5, 0.34], "at": [0, 0, 0.55], "material": "hull", "detail": 1},
    {"shape": "cylinder", "axis": "y", "size": [0.15, 0.42, 0.15], "at": [-0.36, 0, 0.52], "material": "paint",
     "group": "pods"},
    {"shape": "box", "size": [0.1, 0.07, 0.07], "at": [0, 0.25, 0.56], "material": "eye"}],
  "spin": {"pods": {"axis": "y", "speed": 90}}
}
```

- **Parts**: `shape` is `box`, `wedge` (a box whose top slopes down to its front: a nose,
  a ramp, a canopy), `cylinder`, `cone`, `sphere` (`detail` 0-3) or `ring` (a torus;
  `thick` is the tube against the ring, `tube` its sides); `sides` for round ones, `axis`
  (`x`, `y` or `z`) for the way a round one lies. `size` is the part's box, `at` its middle,
  `turn` `[yaw, pitch, roll]` in degrees; `color` paints one part over its material.
- **Materials** are glTF's physically based kind: `color` (as picked on a screen), `metal`
  (0 paint and plastic, 1 bare metal), `rough` (0 a mirror, 1 chalk), `glow` (light of its
  own, 0-4). A triangle is lit as a whole - the low-poly look - or, with `"smooth": true`,
  at its corners and blended across (round things). The light comes with the player, from
  his left and above, so the side he sees is lit and its far side falls into shadow; metal
  shows that light's side of the room, and the level's fog dims it as it does sprites.
- **Moving**: `"bob": [height, beats]` floats it up and down; `"turning"` turns the whole
  model so many degrees a beat (a pickup); `"spin"` turns a `group` of parts about its own
  middle (rotors, turbines, a radar dish). Imported animations play as **frames**: `idle`,
  `walk` (while it moves), `attack` (while it aims and fires); `fps` is frames a beat.
- **Destroyed**, a model breaks apart: its pieces fly out from its middle, turn, fall to
  the floor and are gone; it leaves no gore unless its monster names `remains`. The pieces
  are its triangles (`"break": "shards"`, the default), its parts (`"parts"`: a pod, a
  gun, a canopy fly off whole; an imported mesh comes apart where it is not joined), or its
  groups (`"groups"`).
- **From Blender**: export glTF 2.0 (`.glb`, or `.gltf` with its `.bin`), then
  `python clio.py GAME --import-model drone.glb` (`--model-name`, `--model-scale`: cells
  per metre, 0.4 by default - a 2.5 m room is a cell high). It brings in the meshes of
  the scene with their objects' placing; the materials' base colour, metallic, roughness
  and emission; a base colour texture (PNG) or vertex colours as a colour per triangle;
  and every action - object and armature (skinned) animation alike - as frames, named as
  the actions are. Shape keys (morph targets) and JPEG textures are not taken; it says so.
  Keys you added by hand to a model of that name (`bob`, `turning`, `smooth`, `spin`)
  stay. Keep models low: a few hundred triangles each - every one is lit and filled in
  Python, about 1 ms for a 200-triangle model.

`--check` checks the shapes, sizes, materials and mesh of every model, and that what names
a model has one.

In the editor, **3D models** shows each model in a small room as a level draws it - turn it
(◀ ▶, *Turn round*), *Break it*, play its frames - with its triangles, size and anything
wrong with it. Its **materials** are a row each (name, colour, metal, rough, glow) and its
**parts** too: shape, material, group, size, place and turn, and what a round shape takes
besides; *Copy*, *Mirror* (the same part on the other side, left for right), up the list,
*Remove*, *Add a part*. *From Blender* takes a `.glb` in, as `--import-model` does, keeping
how the model bobs, turns, spins and breaks. The picture follows every change.

### Saving in a level

`save [name]` (F5) saves in a level and `load [name]` (F9) loads; `saves` lists them. A save
holds the game as it was when the level began, a **snapshot** of the level now, and the
lines played since it began. Loading builds the level again from its seed and puts the
snapshot back on it - in a moment, however long the game has gone on. Everything in the
level comes back as it was: fire, grenades, a ridden vehicle, a boss's timetable, the chunks
of a level without end. The level then plays on exactly as it would have (engine/snapshot.py).

A save asked for during a line (`w; save`, or a checkpoint reached on the way) is made when
the line is done, so it always holds whole beats. Each line is kept with the beat it was
played on; a save keeps the last 20000 of them.

A save notes what the level was made of. If the level has changed since, loading plays
the lines back instead of the snapshot, and says so. If even they no longer play through,
the level starts again from the beginning. A save is written whole or not at all, and the
one it replaces is kept beside it (`.bak`); if a save is ever damaged, loading takes that
one and says so. The title screen offers a level's save by the level's name and beat.

```json
"first_person": {"saves": 3, "autosave": true, ...}
```

`saves` limits the saves a player may make in each level (left out: as many as he likes;
`whoami` says how many are left); `autosave` saves as each level begins, so the death menu's
"Load your last save" goes back to it. A cell with `{"savepoint": true}` is a **checkpoint**:
the game is saved, free, the first time it is reached.

For making a game, `--dev` (or `CLIO_DEV=1`) lets saves be made without counting, and
`*ID` typed in a level goes on to the scene that plays level `ID`, as the player is (`*`
alone lists the levels). `--level ID` starts a new game straight in that level.

### The end of a game of levels

`"end_screen"` in game.json ends a won game on a screen of its own, on a terminal big
enough for a level:

```json
"end_screen": {"heading": "EPISODE 1: ROASTED IN THE SHELL",
               "picture": ["helmet_recruit", "helmet_hazmat"], "picture_every": 4,
               "next": "Next: User Space", "credits": ["RØØTLESS - a game by ..."],
               "tick": "*/3 * * * *  cron  rain --on rootless"}
```

The title banner, the `picture` (a sprite, or a list of them: standing side by side, or
taking turns for `picture_every` seconds each), the `heading`, every level's kills, items,
secrets, beats against par and accuracy added up and counted up, the ending's text, what
comes `next`, the `credits`, and the `tick` line at the bottom, which keeps counting down
to its next run. A key goes on to the usual "THE END". Piped or on a small screen the usual
ending is all there is. A picture is at most `picture_lines` lines high (14 - 28 pixels);
a small one is drawn two, three or four times as big where that fits, a big one smaller.
A portrait about 28 pixels high, with few colours and a bold outline, reads best. In the
editor the end screen is in the **Game** form, drawn beside it as the game draws it.

**A secret exit**: an exit switch with `{"exit": "secret"}` (Rootless puts one behind the
goggles' closet in E1M1) ends the level too, but then the scene's `"on_secret_exit"`
effects run instead of `"on_level_exit"` - usually a story text and a `goto` to a scene
with a secret level of its own, whose exit leads back to the next level:

```json
{"id": "boot_sector", "level": "e1m1",
 "on_level_exit": [{"story": "e1_end"}, {"goto": "dynamic_loader"}],
 "on_secret_exit": [{"story": "e1m9_intro"}, {"goto": "swap_partition"}]},
{"id": "swap_partition", "level": "e1m9",
 "on_level_exit": [{"story": "e1m9_end"}, {"goto": "dynamic_loader"}]},
{"id": "dynamic_loader", "level": "e1m2",
 "on_level_exit": [{"story": "e1m2_end"}, {"goto": "drone_refit"}]},
{"id": "drone_refit", "level": "e1m3",
 "on_level_exit": [{"story": "e1m3_end"}, {"win": "outro_demo"}]}
```

### Sprites for a level

Monsters, pick-ups and the gun in the player's hands (`w_...`) are pixel sprites
(sprites.json). A level also uses `fireball`, `muzzle` (the flash) and `gore` (what is left
where a monster died) if the game has them. Far away a sprite is drawn small; the engine
makes smaller drawings for that when the level starts, keeping the pixels that matter -
the letters in `"keep"` (say `"eE"` for the eyes), then the rarest colours - instead of
losing them as plain scaling would. To draw them yourself, put them in the sprite as
`"lod": [{"pixels": [...]}, ...]`: the level uses the smallest that is not much smaller
than what it needs.

A monster that walks shows its steps while it moves: the engine makes two from its
standing picture, the feet on one side lifted a pixel, then the other side's (when the
bottom row has two feet apart; floaters, barrels and spawners do not walk). To draw
them yourself, give the sprite `"walk": [[...rows...], [...rows...]]`; `"walk": []` keeps
it still. `"attack": [...rows...]` is shown while it takes aim, levels its nozzle, spins up
or fires - a flash at the barrel, a raised arm. `"muzzle": [x, y]` is the pixel its shots
leave from, where the flash is drawn (the right edge if not said). Steps and the attack
picture are as big as the sprite, and get far versions of their own.

### Tiles

The walls, floors and ceilings of levels are drawn with tiles: small pictures in the
sprites' format, in tiles.json.

```json
{"grate": {"pixels": ["bbbaaa...", "..."], "palette": {"a": "#2b2e35", "b": "#5c616c"}},
 "steel": {"pixels": [...], "palette": {...}},
 "screens": {"pixels": [...], "frames": [[...], [...]], "palette": {...}}}
```

A tile may be any size (the engine's are 32 x 32); it is stretched over a wall's face or a
cell of floor. A tile named like one of the engine's - `steel`, `screens`, `screens2`,
`hazard`, `door`, `door_r`, `door_w`, `door_x`, `sealed`, `exit`, `exit_on`, `fist`,
`shoot` - takes its place everywhere. `frames` are more drawings, shown in turn, one a beat.
A clear pixel (`.`) shows what is behind a wall - bars, a window - though the wall still
stops the player, shots and sight. In the editor a tile is painted like a sprite, with the
engine's tiles to start from and a small room to see it in.

### Playing it

Keys act at once while nothing is typed; anything else starts a typed command, finished
with Enter.

| Keys | Command | |
| --- | --- | --- |
| ↑ ↓ | `k` `j` | step forward, back |
| ← → (and `<` `>`) | `turn left`, `turn right`, `turn around` | turn (free) |
| Ctrl+← →, Alt+← →, `,` `.` | `h` `l` | strafe left, right |
| Space | `f`, `f z1`, `kill z1` | fire (at z1); `kill -9 x` punches |
| Enter | `use` | open, press what is ahead |
| Tab | `map` | the map of what has been seen |
| 1-7 | `1`-`7`, `shovel` | weapons (a key pressed again: the next weapon on it) |
| `]` | `next` | the next weapon (round to the first) |
| F3, F4, F6 | `mag`, `jet`, `dive` / `surface` | magboots, the jetpack, under the water and up |
| numpad 5 or Delete | `w`, `w 3` | wait a beat (or three) |
| | `t z1` | keep aiming at z1 |
| | `ps`, `man orphan`, `history`, `keys`, `whoami`, `help` | |

The numpad works with NumLock off: 8 2 step, 4 6 turn, 7 9 strafe, 0 fires, 1 turns round.
**Taps** (on by default in Termux, `--touch on` elsewhere): the picture's left and right thirds
turn, their bottom corners strafe, the top of the middle steps forward, the centre fires, the
bottom uses; a swipe up or down steps forward or back; the status line readies the next weapon
and the lines under the picture show the map. `--termux-keys` prints a row of extra keys for
Termux's keyboard.
Lines are joined as in a shell: `a; b`, `a && b` (b only if a hit or moved), `a || b`
(b only if a missed or was blocked); `!!` repeats the last line, `!3` the third, `!f` the
last that began with f; `alias dodge='h || l'` names a line. Anything new - a hit, a
monster waking, fire coming - stops the rest of a line, as Ctrl-C would. `--lines` turns
the single keys off; `"keymap"` in `first_person` (key name -> command line) changes them.
The window can be resized at any time; the picture is drawn again at once.

**Real time.** A level can go on without the player: `"realtime": 0.8` (seconds) on the level,
or in `first_person` for all of them, lets a beat pass every 0.8 seconds in which no key
acts - the monsters move, aim and fire, fuses burn. A key still acts at once, and is a beat
as before; a line being typed holds the clock until Enter, and pages (the map, `ps`, help)
stop it. `"realtime": false` keeps a level waiting whatever the game says. The player can
switch it with `realtime`, `realtime 0.5` and `realtime off`, or start with `--realtime
[SECONDS]` (`--realtime 0` turns it off). The beats that pass are kept in the journal like
any other (as `.`), so a save plays back the same. It needs single keys in a redrawn
screen; scrolling text (`--scroll`, `--lines`) always waits.

`python clio.py --keys` shows what the terminal tells a game in real time: whether it says
when a key is let go (the kitty keyboard protocol, the Windows console), or only repeats
it, and which keys it thinks are held. Games stepped tick by tick - arcade, platformers -
are built on `engine/realtime.py`: a fixed-rate `Clock`, `Controls` for each tick (keys
held, pressed, let go), and a journal of the keys by tick that plays back the same.

A simple player (`engine/levelbot.py`) can walk a level: it follows the level's `"bot"`
list of goals - item ids or map characters, the exit `E` last; `board` climbs into the
nearest vehicle and `out` climbs down - fights what it sees and steps out of fire. If it can finish, a person can. `python tests/levelbot.py 10 rootless
e1m1` lets it play ten times; the editor does the same.

### Levels in the editor

**Levels** opens a map painter: the map drawn with its tiles and the pictures of its
monsters and items, and a palette of its characters - the level's own legend first, then
the engine's. Click or drag to paint with a character, the right button paints floor;
pointing at a cell says what it is. Choosing a character opens what it means: floor,
toxic floor, wall (and its tile), door (its key, the events that open and shut it, the
plate that holds it open), secret wall, monster (and the event that wakes it), item (and
the event taking it sets off, and the way a ball rolls when it wakes), start, exit, a switch (the
event it sets off, its label), crate, pressure plate, teleporter pad or lift (and their names), a
secret area, the tiles above and below it, and whether it is open to the sky. Monsters and items
drawn by 3D models are shown by a small picture of the model. *Add a character* gives the legend a
new one; *Change its meaning here* gives one of the engine's another meaning in this level.
Below the map: the tiles of the whole level, the text of each event, and *Seen from a
cell* - choose *Look from a cell*, click the map, and the engine draws what the player sees
from there; the arrow keys (or the buttons) walk and turn. *Let the level bot play it*
plays it five times and says how far it got.

**Tiles** are painted like sprites; **Weapons** have a form and show the weapon in the
player's hands, with *Fire* to see a shot. **3D models** (models.json) have a form for how a
model moves and the JSON for its parts and materials. **Monsters** are listed like everything else;
sprites can be grown on a body plan, and their far versions seen, made again and painted
(see [Pictures](#pictures)).

**A sheet of pictures…** (below the list of sprites, tiles or monsters) lays the game's
pictures out on one PNG image, each drawn 1 to 8 times as big with its name under it: the
monsters with their steps and their attack, every sprite, or the tiles (the game's and the
engine's). *Download the PNG* saves the image; *Download the atlas* saves where each
picture is on it, in the JSON form many engines and tools read (TexturePacker's "hash",
with each monster's walk as an animation). The same from the command line:

```
python clio.py rootless --sheet monsters --scale 4      # rootless-monsters.png and .json
python clio.py rootless --sheet tiles --export walls.png
```

**Take an edited sheet back in**: draw over the sheet in any paint program - keep each
picture where it is and as big as it is, and paint in squares of the sheet's size (at
`--scale 4`, a square of 4 x 4 is one pixel) - then choose the PNG and its atlas together
in the sheet panel. Only the pictures that were painted over come back (the atlas keeps a
check of each one as it was written, so an old sheet does not undo newer work), with any
new colours added to their palettes. A monster's step that was changed keeps both steps
in the sprite (`walk`); a tile of the engine's that was changed becomes the game's own.
A sheet saved without see-through pixels, on its background, comes back too. Nothing is
written until you save. From the command line it is written at once, if the game then
has no problems:

```
python clio.py rootless --import-sheet rootless-monsters.png    # with rootless-monsters.json beside it
```

## Arcade stages

A scene can hold a stage played in real time: a platformer seen from the side, or a chase
seen from above. `"stage": "id"` in the scene; the stage in `stages.json`:

```json
{
  "run": {
    "title": "The Long Run",
    "mode": "platformer",
    "goal": "exit",
    "need": 3,
    "intro": ["Three chips, then the exit."],
    "map": ["###################",
            "#.................#",
            "#..*.....===*..E..#",
            "#.====.......H.####",
            "#@..*..w..^^.H....#",
            "###################"],
    "on_clear": [{"say": "You made it."}, {"goto": "after_the_run"}]
  }
}
```

The map, a line a row:

| | | | |
| --- | --- | --- | --- |
| `#` wall | `=` platform (stood on from above, jumped up through; down and jump drop through it) | `H` ladder | `^` spikes (a hit) |
| `~` a pit (lava, the void: a life) | `D` door (a key opens it, and is used up) | `E` exit | `!` checkpoint (lives come back here) |
| `*` chip | `+` heart (taken when it is needed) | `k` key | `@` the start |

and enemies by their letter: `w` walker (turns at walls and at the edge of what it walks on),
`h` hopper (and jumps), `f` flyer (comes for the player it sees, through the air), `c` chaser
(walks at the player it sees, and waits at an edge), `t` turret (still, and shoots when the
player is in sight - from the side only along its row). Jumping on an enemy beats it; touching
it otherwise hurts. A hit leaves the player safe for a moment.

- `mode`: `platformer` (gravity, jumps, ladders) or `topdown` (any way and the diagonals; a
  platform is a low wall there).
- `goal`: `exit` (reach it, with `need` chips if said - `"all"` for every one), `chips` (take
  them all), `clear` (no enemy left) or `survive` (`time` seconds). For the others `time` is a
  limit.
- `lives` (3), `health` (3, hits a life takes), `gun` (the fire key shoots where the player
  faces), `music`, `intro` (shown before it starts).
- `physics`: `speed` (tiles a second, 5), `jump` (tiles high, 3.5 - a jump let go early is
  lower), `gravity` (1), `fall` (12), `climb` (4), `shot` (12), `range` (12), `every` (seconds
  between shots, 0.3).
- `legend` gives characters a meaning: a tile (`"B": "wall"`), a pickup, or an enemy, with
  anything of its own: `"G": {"enemy": "walker", "speed": 4, "dir": "left"}`; top-down,
  `"axis": "y"` walks it up and down.
- `colors` (`sky`, `wall`, `wall_top`, `platform`, `ladder`, `spikes`, `pit`, `door`, `exit`,
  `chip`, `player`... as `"#rrggbb"`) and `sounds` (`jump`, `chip`, `stomp`, `kill`, `hurt`,
  `die`, `shoot`, `door_open`, `checkpoint`, `clear`: the game's sound for each).

`"arcade"` in game.json holds the same for every stage - `enemies`, `colors`, `physics`,
`sounds` - and is where a game's own enemies go:

```json
"arcade": {"enemies": {"bugrat": {"move": "walk", "char": "r", "speed": 3, "score": 40,
                                  "color": "#b08858", "color2": "#f0d8b0", "sound_death": "bugrat_death"}}}
```

An enemy has `move` (`walk`, `hop`, `fly`, `chase`, `still`), `char`, `speed` (tiles a second),
`hp`, `damage`, `score`, `sight` (tiles), `stomp` (false: it cannot be jumped on), `edges`
(`fall`: it walks off them), `shoots`, `every` (seconds between shots, or hops), `shot` (its
shots' speed), `aim` (`level` or `any`), `hop` (tiles high), `color` and `color2` (body and top),
`glyph` (in plain text), `sound_death`.

When it ends, the scene's `on_stage_clear` (or the stage's `on_clear`) runs; failed,
`on_stage_fail` (or `on_fail`), and without one the game is lost (`death_text`); left,
`on_stage_quit`, and without one the game ends. The flag `<stage>_cleared` is set, and the
variable `stages` keeps each one's result, score, chips, kills, deaths and seconds.

**Playing it.** The arrows (or WASD, or hjkl) run and climb; Space, Z or Up jumps; Down and
Space drop through a platform; X or F fires; P or Esc pauses (Q then leaves). It runs at 20
ticks a second, and is drawn in half-block pixels - a tile two by two - with the camera
following, or a character a tile in plain text. A terminal that says when keys are let go
(kitty, the Windows console; try `--keys`) holds a key exactly as long as it is held; any
other is guessed from its repeats. Piped, with `--lines` or on a screen under 30 x 12, a stage
is played a typed line at a time: `right 10, jump right 8, wait 5` holds keys for ticks.

Everything is in whole numbers and nothing is left to chance, so the same keys at the same
ticks play a stage the same way. That is how **the stage bot** checks a stage: it tries moves
on copies of it until it finds a way through without losing a life, and plays its keys back
on the stage to be sure:

```
python -m engine.stagebot rootless          # sim5: cleared in 34.6 seconds of play (...)
```

`--level ID` starts a game at the scene that plays stage ID, as for levels.

## Skirmishes (real-time strategy)

A scene can hold a skirmish: workers gather crystal and put up buildings, buildings train units,
units fight, and a side is out when its buildings are gone. `"skirmish": "id"` in the scene; the
skirmish in `skirmishes.json`:

```json
{
  "border": {
    "title": "Border Clash",
    "map": ["##############################",
            "#..$$$...........#........$$$#",
            "#..$$$...........#........$$$#",
            "#......1.........#....2......#",
            "#............................#",
            "#~~~~~~......................#",
            "##############################"],
    "sides": [{"name": "You", "control": "player"},
              {"name": "Raiders", "control": "ai", "ai": {"wave": 4, "first": 180}}],
    "on_win": [{"say": "The border holds."}, {"goto": "after_the_clash"}]
  }
}
```

The map: `.` ground, `#` rock, `~` water, `T` trees (none of them walked on), `$` crystal
(`"crystal"`: how much in each, 600), `&` gas (`"gas"`, 1500; what the two are called:
`"names": {"crystal": "Xantrium", "gas": "Plasma"}`), and `1`-`4` where each side starts - its headquarters
there, its workers round it. A `legend` gives other characters a meaning: a terrain
(`"r": "rock"`) or something standing there from the start
(`"g": {"unit": "soldier", "side": 2}`, `{"building": "tower", "side": 1}`).

- `sides`: `name`, `control` (`player` - one side at most -, `ai`, or `none`: there, and doing
  nothing), `credits` (200), `workers` (4), `units` (`{"soldier": 2}` more at the start),
  `faction` (the kinds it may have, below), `color`, and for the computer `ai`: `workers` it
  keeps (8), `wave` (army units in its first attack, 5; two more each time, up to `most`, 14),
  `first` (seconds before its first attack, 150), `towers` (1), `mix` (how many of each role,
  `{"melee": 2, "ranged": 2, "heavy": 1}`; `"air": 1` and it builds an airfield too), `gas`
  (workers it puts on gas, 2), `research` (upgrades with crystal to spare, true), `every`
  (seconds between its decisions, 1). It mends what was hurt, and when its crystal runs out it
  attacks with what it has.
- `goal`: `destroy` (every other side out) or `survive` (`time` seconds). `limit`: units a
  side may have (40). `intro`, `music`.
- When it ends, the scene's `on_skirmish_win` (or the skirmish's `on_win`) runs; lost,
  `on_skirmish_lose` (or `on_lose`), and without one the game is lost (`death_text`); left,
  `on_skirmish_quit`, and without one the game ends. The flag `<skirmish>_won` is set and the
  variable `skirmishes` keeps each one's result, time, units and buildings.

**Kinds.** The engine has a worker, soldier, ranger and tank, a headquarters, barracks,
factory and tower. A game's own go in game.json `"rts"` (`"engine_kinds": false` leaves the
engine's out), each with `faction` - a side has the kinds of its faction (none: those without):

```json
"rts": {"engine_kinds": false, "kinds": {
  "rig": {"name": "Mining Rig", "role": "worker", "faction": "tam", "hp": 45, "speed": 2.6,
          "cost": 50, "time": 10, "char": "m", "carry": 6, "gather": 3},
  "command": {"name": "Command Post", "role": "hq", "faction": "tam", "building": true,
              "size": [3, 3], "hp": 1400, "cost": 400, "time": 60, "char": "C",
              "produces": ["rig"], "dropoff": true}}}
```

A kind has `role` (`worker`, `melee`, `ranged`, `heavy`, `hq`, `barracks`, `factory`, `tower`:
what the computer player builds by), `char` (lower case for units, upper for buildings, by
custom), `hp`, `armor` (taken off each hit), `speed` (tiles a second), `damage`, `range`
(tiles), `cooldown` (seconds between shots), `splash` (tiles round the target hit for half),
`sight` (tiles), `cost`, `time` (seconds to train or build); workers `carry` and `gather`
(seconds a load); buildings `building`, `size` [w, h], `produces`, `dropoff` (crystal and gas
are brought here); `gas` (a second cost, beside `cost`); `needs` (a building kind built, or an
upgrade made, before it is built or trained). A tower is a building with `damage`. `air`: it
flies, straight over anything, and only what hits the air hits it - `hits`: `ground`, `air` or
`both` (ranged kinds, `range` 2 or more, hit both; the rest the ground). `carries`: a transport
for that many (units board it, ride, and are set down; lost with it). The engine has an
airfield, a gunship and a lifter (it carries 6).

**Upgrades** (game.json `"rts": {"upgrades": ...}`, or a skirmish's): made at a building like a
unit, once a side, and from then on adding to every kind (or role) in `to`:

```json
"rifles": {"name": "Rifles", "at": "barracks", "cost": 150, "gas": 50, "time": 40,
           "to": ["trooper", "gunner"], "damage": 2}
```

An upgrade may add `hp` (those there already get it too), `armor`, `speed`, `damage`, `range`,
`cooldown`, `sight`, `splash` or `carry`, and may `needs` a building or another upgrade first. The
engine's: weapons, plating, drills, tracks (a tank needs it), optics.

**Playing it.** The arrows move the cursor (held, they run on; Shift or Ctrl and an arrow,
five at a time). Space chooses what is under it; Enter acts on it with what is chosen: an
enemy is attacked, crystal gathered, a building of yours begun is helped along, else they go
there - Enter on a transport of yours boards it, on a hurt building of yours sends workers to
repair it (for crystal: half its cost for the whole of it). `v` starts and ends a box to choose
by; Tab goes to an idle worker; `u` chooses the army, `e` everything like what is chosen; `G`
and a digit keep what is chosen as a group (Ctrl and the digit too, where the terminal sends
it), the digit chooses it again, and twice goes to it. A group sent somewhere keeps its shape
and goes at its slowest one's pace. `a` attacks on the way to the cursor, `m` goes there (past
enemies), `o` patrols between here and there, `s` stops, `h` holds (fights only what comes in
range), `g` gathers, `d` sets down what a transport carries. `b` opens the build menu (a digit,
then Enter where the cursor shows it fits); with a building chosen, digits train or make an
upgrade (shown with a +), `c` takes the last back (paid back), `r` sets where new units go. P
or Esc pauses (Q then leaves). Where the terminal reports the mouse, a click chooses, a drag draws a box, and the
right button acts. The panel shows crystal, units, the time, what is chosen and a map of the
whole field with the view's frame on it. Piped, with `--lines` or on a screen under 40 x 14, a
skirmish is played a typed line at a time: `select workers; gather; wait 20`,
`build barracks 12,26`, `train trooper 2`, `research rifles`, `patrol 30,10`, `board 14,20`,
`unload 40,8`, `repair 8,28`, `group 1`, `recall 1`, `look 30,10`, `map`, `status` (`help`
lists them).

It runs at 10 ticks a second in whole numbers with nothing left to chance, and paths come from
flow fields (one per place units are sent to, shared by all of them). The orders a player gives
are kept by tick (the world's `journal`); played back on the same skirmish they give the same
game - which is all lockstep multiplayer needs. The computer plays any side; to see who wins:

```
python -m engine.rts rootless              # sim7: won (destroyed) at 5:50 of play, 1.4s
```

(the player's side is played with the skirmish's `player_ai`). `--level ID` starts a game at
the scene that plays skirmish ID.

## Simulators

A scene can hold a sim: a vehicle driven, sailed or flown in real time over a map, with its
instruments, fuel and systems - or a model of systems alone, run with controls. `"sim": "id"`
in the scene; the sim in `sims.json`:

```json
{
  "delivery": {
    "title": "Night Delivery",
    "map": ["##################",
            "#@...1.....,,,,..#",
            "#....====2===....#",
            "#..::::.....3..H.#",
            "##################"],
    "vehicle": {"model": "hover", "fuel": 40},
    "land": true, "time": 90,
    "systems": {"heat": {"rate": "thrust * 9 - (heat - 20) * 0.25", "start": 20, "min": 20,
                         "damage_over": 95}},
    "on_done": [{"say": "Delivered."}, {"goto": "the_depot"}]
  }
}
```

The map: `.` ground, `,` grass (slower), `=` road (faster, more grip), `:` mud (slow,
slippery), `~` water, `#` rock (3 high), `T` trees (1), `B` buildings (2), `H` a pad, `F` fuel
(stand on it, or land on it, and the tank fills), `@` the start, `1`-`9` checkpoints, passed in
order. A `legend` gives other characters one of these.

`vehicle`: `model` and its numbers (tiles and seconds):

- `car` - `accel`, `brake`, `max_speed`, `reverse`, `drag`, `turn` (degrees a second, at speed
  `turn_speed` and above), `grip` (how fast it stops sliding sideways). ↑ goes, ↓ brakes (and
  backs), ←→ steer, Space the handbrake. Rock, trees, buildings and water stop it; the harder
  the hit, the more damage.
- `boat` - the same, on water only, and with little grip: it drifts.
- `hover` - `thrust`, `max_speed`, `drag`, `turn`, `max_climb`, `descend` (how fast S sinks it,
  1.4), `gravity` (when the fuel is gone), `ceiling`, `safe_climb` and `safe_speed` (faster than
  that when it touches down hurts). ↑↓ thrust along its heading, ←→ turn, W climbs, S sinks,
  neither holds it where it is. What is higher than it stops it.
- `plane` - `accel`, `max_speed`, `stall` (slower than that it drops), `climb`, `land_speed`.
  ↑↓ the throttle, ←→ turn, W climbs, S dives, Space brakes on the ground. It takes off above
  its stall speed with W, and lands on a road or a pad.

Every model has `fuel` (its tank), `burn` (a second at full thrust), `idle`, `toughness`, and
`heading`, `altitude`, `fuel_start`. Out of fuel, a car rolls to a stop, the hopper falls.

**Goals.** `goal`: `checkpoints` (all of them, in order; with `"land": true`, then a landing on
a pad), `land` (on a pad), or `survive` (`time` seconds); `time` is otherwise a limit. A
landing hard enough, a crash, a sinking, an empty tank on the ground, or `fail_if` ends it
(`fail_text` names it); `win_if` is done at once. When it ends, the scene's `on_sim_done` (or the
sim's `on_done`) runs; failed, `on_sim_fail` (or `on_fail`), and without one the game is lost
(`death_text`); left, `on_sim_quit`. The flag `<sim>_done` is set and the variable `sims` keeps its
result, time, damage and fuel.

**Systems** are stocks that change each tick: `rate` (a formula, how much a second), `start`,
`min`, `max`; or `value` (a formula worked out afresh each tick). `damage_over` hurts the vehicle
while a system is above it (`damage_rate`). Formulas use numbers, + - * / % //, comparisons,
`and`, `or`, `not`, `a if c else b`, `min`, `max`, `abs`, `clamp`, `floor`, `sqrt`, and names:
`speed`, `forward`, `altitude`, `height` (above the ground), `climb`, `heading`, `throttle`,
`thrust`, `fuel`, `damage`, `time`, `landed`, `passed`, `next` (to the next checkpoint), the
model's numbers, the controls and the other systems.

**Instruments** (`gauges`, else the model's): each `{"show": NAME, "label", "max" (a number or a
name), "style", "warn", "scale", "unit"}` - `style` `bar`, `center` (a bar either way from zero,
for climbing), `number` or `compass` (a strip of the compass round the heading); `warn` turns it
red at that part of `max` and above, or (below zero) at that part and below.

**Systems alone** (`"mode": "systems"`): no map, no vehicle - `controls` the player moves
(`{"rods": {"keys": ["up", "down"], "min": 0, "max": 100, "start": 40, "step": 20}}`: a key
raises it, the other lowers it, `step` a second), `systems`, `gauges`, `chart` (systems drawn as
lines over time), `win_if`, `fail_if`, `time`, and `score` (a formula: better when higher, for
the autopilot below). An economy, an ecology, a reactor: whatever stocks and flows say.

**Playing it.** At 20 ticks a second; the map follows the vehicle (north up), an arrow at its
edge points to what is next, and the instruments stand beside it. Piped, or on a small screen,
it is played a typed line at a time: keys held for seconds - `up 2; up right 1.5; w 1; wait 3`,
`status`, `map`.

Floats, but only + - * / and square roots - the same on every machine - and the sines and
cosines of a table made with whole numbers: the same keys at the same ticks fly the same flight.
**The autopilot** flies, drives or runs each sim (a systems sim by trying the controls ahead on
copies) and its keys play the run back:

```
python -m engine.sim rootless       # sim8: won (done) at 33.7 seconds, damage 0, fuel 22
```

## Demos

`demo.json` in a game's folder is a demo: clips that play themselves, each with a caption
line under it. The title screen offers it (`[Enter to begin, d: the demo]`) and plays it by
itself after 45 seconds with no key (`CLIO_DEMO_IDLE=SECONDS` changes that, `0` turns it
off); `python clio.py GAME --demo` plays it once, `--attract` over and over. Any key goes
back. CLIo's own tech demo (`engine/demos/clio.json`) is on the launcher's menu, and plays
there the same way.

```json
{"title": "RØØTLESS: a demo", "game": "rootless", "clips": [
  {"card": "RØØTLESS", "palette": "toxic", "text": ["Episode 1"], "seconds": 4},
  {"level": "e1m1", "seconds": 24, "caption": "Boot Sector: the shotgun"},
  {"level": "e1m4", "skip": 120, "views": ["pixel", "dots"]},
  {"sim": "sim8"}, {"stage": "sim6"}, {"skirmish": "sim7"},
  {"models": ["drone_hornet", "hopper"], "seconds": 3.5, "views": ["pixel", "dots"]},
  {"adventure": "derelict", "commands": "walkthrough", "seconds": 24}]}
```

| Clip | What plays |
| --- | --- |
| `card` | big letters (a banner: `style`, `palette`, `effect`) and `text` lines under them |
| `logo` | the CLIo logo (or the one named) and `text` |
| `level` | the level, played by its bot (the level's `"bot"` goals, or `goals`). `skip` beats, or `skip_until` `"vehicle"` or `"fight"`, go by unseen first; `views` take turns (`view_every` seconds); `beat` is the seconds between moves (0.16) |
| `sim` | the sim, flown by its autopilot |
| `stage` | the stage, played by its bot (it looks for the way first: a second or more) |
| `skirmish` | the skirmish, with the computer on every side; the view follows the fighting |
| `models` | each model turning in a yard under the sky, `seconds` each, scaled to about one size (`size`) |
| `adventure` | a game (a folder under games/) played by typed `commands`, or its `"walkthrough"` |

A clip plays its `seconds` (or less, if its game ends); `game` names another game's folder.
The caption shows the clip's `caption`, the view, and how long a picture took (with CLIo
Picture or in Python). `--check` checks demo.json; a clip that cannot play is passed over.

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
