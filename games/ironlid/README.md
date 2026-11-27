# IRONLID

A test demo for CLIo: two first-person levels in which everybody is moved by
[CLIo Motion](https://github.com/eryxgames/clio-motion).

```
python clio.py ironlid            # play
python clio.py ironlid --demo     # its crowds, and the bot in the yard
python clio.py ironlid --level relocation
```

**Halden, the outpost.** Thane, of a garrison whose supplies arrived a hundred years late, stands
guard at a research outpost when the machines come in. The helmet shows one colour. Its scanner
(on the bench beside you; **B** or F2) shows Halden's plan: eleven sectors, each with how many of
them are in it, the staff (`+`), the garrison's troopers (`*`) and you. Six of the staff are
there, going about their work; two must live. They run from what they see, and the machines go
for whoever of ours is nearest - unless you are nearer. Walk up to one and it follows you: bring
it to the barracks, the shelter, and it is secured. Three troopers fight where they stand. The
attack comes in two waves; when the outpost is quiet, something larger comes.

**The relocation yard.** What was made of him sees in lines, and on whoever is open to a shot -
while it aims, while it reels, from behind - there is a mark: a shot there counts twice. The
gunner at the ramp is its lock.

| Who | Moved as | Fights as |
| --- | --- | --- |
| line android, breacher | soldier (rifle, shotgun) | a fire team; comes through the door |
| burner, heavy gunner | gunner (flamethrower, chaingun) | in line at three cells; two beats to spin up |
| hound | hyena | a pack: keeps off, then all at once |
| stalker, mantis, wasp | raptor, mantis, wasp | round your side; straight at you; from the air |
| the Spider | spider | - |
| the staff | scientist, technician, hazmat, woman | they do not |
| trooper | soldier (rifle) | beside you |

What it tries of the engine is in [Making games with CLIo](../../docs/AUTHORING.md): civilians,
a shelter and who is secured, allies, sectors and the plan, `on_clear`, `death_after` and
`on_level_death`, a level's own `player`, `criticals`, `"tint"`.

All rights reserved - see [LICENSE.md](LICENSE.md).
