# unicum.gg-mod

World of Tanks client mod for [unicum.gg](https://unicum.gg). Shows where
players come from, using the language unicum.gg knows for each of them and
the same Flagpack flags as the site.

Not affiliated with Wargaming.net.

## What it does

| Surface | What is shown | Hook |
|---|---|---|
| Contacts list | flag after the name | `ContactConverter.makeBaseUserProps` |
| Player profile window title | language code, e.g. `EN` | `ProfileWindow.as_setInitDataS` |
| Battle player panels | flag after the name | `player_format.getRegionCode` |
| Stronghold detachment list and skirmish room | not yet | see `src/unicum/browser.py` |

Languages come from `GET /api/{region}/languages/resolve` on unicum.gg,
asked for in batches of at most 100 ids. The API answers with country codes
already resolved, so the mod never needs to know that `en` is the UK flag on
EU and the US one elsewhere. Clan languages are declared by the clan owner;
player languages are inferred by unicum.gg.

Images get countries, text gets languages: a country code only exists to
name a flag file, and something like `GB-UKM` means nothing written out.

### Flags

Flags are PNGs in the client's resource tree, under
`res_mods/<version>/gui/maps/icons/unicum/flags/`, referenced as
`img://gui/maps/icons/unicum/flags/<CODE>.png`.

They have to be there when the client starts. ResMgr indexes the tree once
at boot, and a file that appears later is never resolved. Two other routes
were tried and do not work in these Scaleform text fields:

- **A URL.** It is looked up as a SWF export name and never fetched.
- **A memory texture** (`wg_addScaleformTexture`). It draws, but only one
  image at a time: with all 252 flags registered, a contacts list drew one.

`tools/flags` rasterises the Flagpack SVGs to PNG, and `tools/install_dev.py`
copies them in. A flag missing at startup is downloaded from
`https://unicum.gg/flags/s/<CODE>.png` and shows up next session, once the
site serves PNGs there.

## Development

The client loads one file from this repo: a bootstrap, packaged as a
`.wotmod`, that watches `src/` and reimports it whenever a file changes.
**Editing the mod does not need a client restart.**

```
cd tools/flags && npm install && npm run build && cd ../..
python tools/install_dev.py --game "C:/Games/World_of_Tanks_EU"
```

That installs the bootstrap into `mods/<version>/` and the flags into
`res_mods/<version>/`. Start the client once; after that, saving a file
under `src/` reloads the mod in place within half a second.

Logs go to `game.log` in the game directory, under loggers named `unicum.*`.

Still needs a restart: the bootstrap itself, and any new flag PNG.

### Why the reload works

`src/unicum/runtime/session.py` is the whole trick. Nothing takes ownership
of anything directly: every hook, callback, subscription and request goes
through a `Session`, and `stop()` hands all of it back before the package is
dropped from `sys.modules` and reimported. A hook that survived a reload
would stack under the next one and run code whose module is gone, so the
registry is not bookkeeping, it is the correctness argument.

The bootstrap loads sources through its own finder on `sys.meta_path`.
BigWorld resolves `sys.path` entries through ResMgr, so a plain directory
there is never found.

### Tests

```
python2.7 tools/selftest.py
```

Runs outside the game against fake client modules: the edit/reload cycle,
recovery from a broken save, patch restoration for module functions,
classmethods and inherited methods, and the language lookup against the
live API.

### Layout

```
dev/      bootstrap template, packaged into the game once
src/      everything reloadable; the only thing you edit
tools/    installer, flag rasteriser, selftest
```

## Requirements

- World of Tanks 2.4.0.0 (EU)
- Python 2.7, as the client is, and Python 3 for the tooling
- Node.js, to rasterise the flags

## License

AGPL-3.0, same as unicum.gg.
