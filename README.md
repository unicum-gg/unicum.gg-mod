# unicum.gg-mod

World of Tanks client mod for [unicum.gg](https://unicum.gg). Shows where
players come from, using the language unicum.gg knows for each of them and
the same Flagpack flags as the site.

Not affiliated with Wargaming.net.

## What it does

| Surface | What is shown | Hook |
|---|---|---|
| Contacts list | flag after the name | `ContactConverter.makeBaseUserProps` |
| Player profile window title | flag after the name (language code without the SWF) | `ProfileWindow.as_setInitDataS` |
| Battle player panels | flag after the name | `player_format.getRegionCode` |
| Skirmish room members and volunteers | flag after the name | `StrongholdBattleRoom.as_setMembersS`, `SortieCandidatesLegionariesDP._makePlayerVO` |
| Stronghold detachment list (web page) | flags after the clan tag; "Places" folded into "Members"; sort by rating | `src/unicum/web/stronghold.js`, injected by `src/unicum/browser.py` |

Every surface shows all of a player's or clan's flags, up to three
(`config.MAX_FLAGS`), in the order the API gives them.

Everything comes from `GET /api/{region}/resolve` on unicum.gg: languages
and flags, lifetime and 30-day ratings, win rates and a player's clan, for
players and clans by id and for clans by tag, in batches of at most 100 per
kind (`src/unicum/api/resolve.py`). The API answers with flag codes already
resolved, so the mod never needs to know that `en` is the UK flag on EU and
the US one elsewhere. Clan languages are declared by the clan owner; player
languages are inferred by unicum.gg. Rating colours come from
`GET /api/ratings/scales`, fetched at most daily (`src/unicum/api/scales.py`).

A server without `/resolve` answers 404, and the mod then falls back to the
older languages-only endpoints (`src/unicum/api/legacy.py`): flags keep
working, ratings are absent.

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

### Profile title

A window title is plain text unless its AS3 `Window` has `titleUseHtml` on,
and the profile window never turns it on. Python cannot reach the `Window`
through the GFx proxy, so `as3/src/unicum/TitleHtml.as` does it: a view with
no display, loaded once into the lobby's service layer by
`src/unicum/titles.py`, that flips the switch on every profile window. What
the title says is still decided in Python and still hot reloads.

Without the SWF in the resource tree, titles fall back to the language code.

## Development

The client loads one file from this repo: a bootstrap, packaged as a
`.wotmod`, that watches `src/` and reimports it whenever a file changes.
**Editing the mod does not need a client restart.**

```
cd tools/flags && npm install && npm run build && cd ../..
python tools/build_as3.py --game "C:/Games/World_of_Tanks_EU"
python tools/install_dev.py --game "C:/Games/World_of_Tanks_EU"
```

That installs the bootstrap into `mods/<version>/`, and the flags and the
title SWF into `res_mods/<version>/`. Start the client once; after that,
saving a file under `src/` reloads the mod in place within half a second.

`build_as3.py` downloads Apache Royale (about 200 MB) and `playerglobal.swc`
into `build/as3` on first run, and compiles against the client's own `.swc`
files, taken from its `gui-part*.pkg` packages.

Logs go to `game.log` in the game directory, under loggers named `unicum.*`.

Still needs a restart: the bootstrap itself, any new flag PNG, and the SWF.

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
as3/      the profile title view, built once into a SWF
dev/      bootstrap template, packaged into the game once
src/      everything reloadable; the only thing you edit
tools/    installer, flag rasteriser, AS3 build, selftest
```

## Requirements

- World of Tanks 2.4.0.0 (EU)
- Python 2.7, as the client is, and Python 3 for the tooling
- Node.js, to rasterise the flags
- Java 11 or later, to compile the AS3 view

## License

AGPL-3.0, same as unicum.gg.
