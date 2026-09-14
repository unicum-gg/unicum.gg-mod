# unicum.gg-mod

World of Tanks client mod for [unicum.gg](https://unicum.gg). Shows the
language of each clan and player on the Stronghold rosters, using the same
Flagpack flags as the site.

Not affiliated with Wargaming.net.

## What it does

Two places in the client name clans and players without saying where they
are from:

| Screen | What is added | How |
|---|---|---|
| Stronghold → Clan Battles → detachment list | clan language | JS injected into the clan-portal page the client renders in its embedded browser |
| Skirmish room → detachment members and volunteers | player language | `makePlayerVO` hook, before the VO reaches Flash |

Clan languages are declared by the clan owner. Player languages are
inferred by unicum.gg from clan history, and fall back to the player's
current clan; the tooltip always says which of the three it was.

## Development

The client only loads one file from this repo: a stub that watches `src/`
and reimports it whenever a file changes. **Editing the mod does not need a
client restart** — start the game once, then save and look.

```
python tools/install_dev.py --game "C:/Games/World_of_Tanks_EU"
```

That renders `dev/mod_unicum_dev.py.in` into
`res_mods/<version>/scripts/client/gui/mods/`, pointing at this checkout.
Start the client once; after that, saving a file under `src/` reloads the
mod in place within half a second.

Watch `python.log` in the game directory for lines tagged `unicum`.

### Why the reload works

`src/unicum/runtime/session.py` is the whole trick. Nothing takes ownership
of anything directly — every hook, callback and subscription goes through a
`Session`, and `stop()` hands all of it back before the package is dropped
from `sys.modules` and reimported. A hook that survived a reload would run
the previous load's code against the new load's state, so the registry is
not bookkeeping, it is the correctness argument.

What still needs a restart: the stub itself, and any resource the client
reads once at boot (flag PNGs, XML). Python and injected JS do not.

### Layout

```
dev/      stub template, copied into the game once
src/      everything reloadable; the only thing you edit
tools/    installer and build scripts
```

## Requirements

- World of Tanks 2.4.0.0 (EU)
- Python 3 to run the tooling; the mod itself is Python 2.7, as the client is

## License

AGPL-3.0, same as unicum.gg.
