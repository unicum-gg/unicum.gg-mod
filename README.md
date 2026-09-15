# unicum.gg-mod

World of Tanks client mod for [unicum.gg](https://unicum.gg). Shows where
players and clans come from, with the same Flagpack flags as the site, and
their WN7, WN8 or WNX painted with the site's colour scale.

Not affiliated with Wargaming.net.

## What it does

| Surface | What is shown | Hook |
|---|---|---|
| Contacts list | flag after the name | `ContactConverter.makeBaseUserProps` |
| Player profile window title | flag after the name (language code without the SWF) | `ProfileWindow.as_setInitDataS` |
| Battle player panels, Tab, loading screen | flags and rating after the name; team averages after the team names | `VehicleInfoComponent.addVehicleInfo`, `BattleStatisticsDataController.as_setArenaInfoS` |
| Skirmish room members and volunteers | flags and rating after the name; members sort dropdown (the special battles' orders, plus the rating and personal rating) and average rating beside the title | `StrongholdBattleRoom.as_setMembersS` / `as_updateRallyS`, `SortieCandidatesLegionariesDP._makePlayerVO` |
| Stronghold detachment list (web page) | flags after the clan tag; a rating column; "Places" folded into "Members"; sort by personal rating or rating | `src/unicum/web/stronghold/`, injected by `src/unicum/browser.py` |

Every surface shows a player's or clan's flags, up to three, in the order the
API gives them.

### Settings

`mods/configs/unicum/settings.json`, written with the defaults on first start
(`src/unicum/settings.py`):

| Key | Default | |
|---|---|---|
| `enabled` | `true` | the whole mod |
| `metric` | `"wnx"` | the one rating shown everywhere: `"wn7"`, `"wn8"` or `"wnx"` |
| `window` | `"recent"` | its period: `"recent"` (last 30 days, lifetime while not computed) or `"total"` |
| `maxFlags` | `3` | flags per player or clan, 1 to 3 |
| `contacts`, `profile`, `stronghold` | `{"flags": true, "rating": ...}` | whether each surface shows flags and the rating; the rating is off for contacts and profile |
| `skirmishRoom`, `battle` | `{"flags": true, "rating": true, "average": true}` | the same, plus the detachment's or team's average |

One rating for the whole mod, so a number means the same thing on every
screen. A settings.json written by an earlier version is converted on first
read.

The file is checked every second and changes apply to what is on screen. With
izeberg's modsSettingsApi installed, the same settings also appear in its
window, and in anything that reads that API (`src/unicum/settings_window.py`);
nothing else is required. With poliroid's modsListApi installed, the mod also
has an entry with its icon in the "Open settings" menu, which opens that
window (`src/unicum/mods_list.py`). The icon is `assets/icon.svg`, rendered by
`cd tools/badges && npm run icon`.

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
through the GFx proxy, so `as3/src/unicum/TitleHtml.as` does it, as part of
the lobby view that `src/unicum/views.py` loads into the lobby's service
layer: it flips the switch on every profile window. What
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

That installs the bootstrap into `mods/<version>/`, and the flags, badges and
SWFs into `res_mods/<version>/`. Start the client once; after that,
saving a file under `src/` reloads the mod in place within half a second.

`build_as3.py` downloads Apache Royale (about 200 MB) and `playerglobal.swc`
into `build/as3` on first run, and compiles against the client's own `.swc`
files, taken from its `gui-part*.pkg` packages.

Logs go to `game.log` in the game directory, under loggers named `unicum.*`.

A SWF rebuilt with `build_as3.py --install` is reloaded in place too: its
view is destroyed and loaded again within a second.

Still needs a restart: the bootstrap itself, any new flag PNG or badge, and a
SWF that did not exist when the client started.

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

Runs outside the game against fake client modules (`tools/checks/`): the
edit/reload cycle, recovery from a broken save, patch restoration, every
surface, the page script protocol, and the unicum.gg client against the live
API. Set `UNICUM_API_BASE` to a server that has `/resolve` to test it;
production is used to test the fallback.

### Layout

```
as3/      the profile title view, built once into a SWF
dev/      bootstrap template, packaged into the game once
src/      everything reloadable; the only thing you edit
tools/    installer, flag rasteriser, AS3 build, selftest
```

Working on the mod: read [`AGENTS.md`](./AGENTS.md) for the rules that keep
hot reload safe, and [`CONTRIBUTING.md`](./CONTRIBUTING.md) for commits.

## Requirements

- World of Tanks 2.4.0.0 (EU)
- Python 2.7, as the client is, and Python 3 for the tooling
- Node.js, to rasterise the flags
- Java 11 or later, to compile the AS3 view

## License

AGPL-3.0, same as unicum.gg.
