# What this is

A World of Tanks client mod for [unicum.gg](https://unicum.gg): language flags and ratings next to player and clan names, on the client's own screens. Client 2.4.0.0 EU, Python 2.7 inside the game. Everything the mod shows comes from the unicum.gg API; the mod holds no game data of its own.

Read `README.md` for the feature table and setup, `CONTRIBUTING.md` for commits.

# Layout

- **`dev/mod_unicum_dev.py.in`**, the bootstrap. The only file the client loads, packaged once as a `.wotmod`. It watches `src/` and reloads the package in place. Changing it needs a client restart; nothing else in the repo does, except the resource files below.
- **`src/unicum/`**, everything reloadable.
  - `__init__.py`: `start()` / `stop()`. Builds the shared services and installs each surface.
  - `settings.py`: `settings.json`, the one source of truth for what is shown; every surface takes it and redraws on `on_change`. `settings_window.py` mirrors it into modsSettingsApi when that mod is installed, never as a dependency; `mods_list.py` adds the mod to modsListApi's menu the same way, and `tank_button.py` adds a button and menu to the hangar's vehicle menu through openwg_gameface (its Gameface files and `res_map` entry are in `res/`); `build.py` writes the vehicle's setup as the site's `setup` token, whose format lives in unicum-gg/unicum.gg `config-url.ts`.
  - `runtime/session.py`: the ownership registry, see [Hot reload](#hot-reload).
  - `api/`: the unicum.gg client. `resolve.py` (batched lookup), `entry.py` (one player or clan), `store.py` (disk cache), `scales.py` (rating colours), `http.py` (what counts as an answer).
  - Surfaces: `lobby.py` (contacts, profile title, skirmish room), `battle.py` (players panel, Tab, loading screen), `name_markers.py` (the vehicle markers above tanks), `browser.py` + `web/stronghold/*.js` (the Stronghold detachment list, a web page), `room_sort.py` (saves the skirmish room's members order), `views.py` (loads the AS3 views and reloads them when their SWF changes).
  - `textures.py`: flag PNGs, as `img://` paths for Scaleform and data URIs for web pages.
  - `local_settings.py`: gitignored, points `API_BASE` at a local server.
- **`as3/`**, one AS3 view per app: `LobbyView.as` (made of `TitleHtml.as`, and `RoomTools.as` + `MembersSection.as` for the skirmish room's members sort and average) built into `unicum.lobby.swf`, `TeamNamesHtml.as` (with `VehicleMarkers.as`, the icon columns) into `unicum.battle.swf`. `markers/` is added to the client's `battleVehicleMarkersApp.swf` (`UnicumMarkersApp.as`, `MarkersBoot.as`) and built into `unicum.markers.classes.swf` (the marker subclasses), `NameMarkerView.as` into `unicum.markers.swf`; `stubs/` stands in for client classes at compile time only. One per app because a second view in an app's service layer destroys the first.
- **`tools/`**: `install_dev.py`, `build_as3.py`, `flags/` (Flagpack SVG to PNG), `selftest.py` + `checks/`.

# Commands

| Command | What it does |
|---|---|
| `python tools/install_dev.py --game "C:/Games/World_of_Tanks_EU"` | Installs the bootstrap, flag PNGs, badges and SWFs into a client. Python 3. |
| `cd tools/flags && npm install && npm run build` | Rasterises the flags into `build/flags`. |
| `python tools/build_as3.py --game "C:/Games/World_of_Tanks_EU"` | Fetches Apache Royale and the client's `.swc` files into `build/as3`, compiles the SWFs and the patched `battleVehicleMarkersApp.swf` (from the client's own packages); `--install` copies them into the client, where a running client reloads them, except the patched app, which needs a restart. Needs Java 11+. |
| `python2.7 tools/selftest.py` | The test suite, Python 2.7, against fake client modules and a real API. Set `UNICUM_API_BASE` to test against another server than production. |

Logs go to `game.log` in the game directory (not `python.log`), under loggers named `unicum.*`. Read it after every change: a reload that failed says so there and nowhere else.

# Hot reload

The whole design rests on one property: after `stop()`, every game function is back, by identity. So nothing takes ownership of anything directly. Every patch, callback, subscription, request and teardown goes through the `Session` handed to `install()`, and `Session.close()` gives it all back before the package is purged and reimported.

- **Patch with `session.patch(holder, name, build)`.** It restores what the owner's `__dict__` held, which is what makes classmethods and inherited methods come back right. A hook that survives a reload stacks under the next one and runs code whose module globals are gone; the log then says `LEAK`, and only a client restart clears it.
- **Never `BigWorld.callback` or `BigWorld.fetchURL` directly.** Use `session.callback` / `session.fetch`, which are gated on `session.alive`.
- **Share, don't duplicate, services.** One `Lookup`, one `FlagCache`, one `RatingScales` per start, passed to every surface. Two lookups once overwrote each other's disk store.
- **`start()` rolls back on failure**, so a half-installed load never orphans its patches.
- Saving a file mid-edit triggers a reload of a broken state. That is expected and recovers on the next save; do not "fix" the watcher.

# Rules learned the hard way

**Mark names at the presentation layer, never in a shared accessor.** A value used by several screens reaches plain-text fields too, and `<IMG>` markup then shows as characters. Each hook sits where the field is known to be rendered as `htmlText`:

- contacts: `ContactConverter.makeBaseUserProps`
- skirmish room: `StrongholdBattleRoom.as_setMembersS` **and** `as_updateRallyS` (going into battle redraws through the second one)
- battle: `VehicleInfoComponent.addVehicleInfo`, not `player_format.getRegionCode`, which also feeds the damage panel
- vehicle markers: `MarkersManager.createMarker`, swapping the client's marker symbol for our subclass of it
- profile title: `ProfileWindow.as_setInitDataS`, and only when `views.html_titles()` says the SWF made the title HTML

**Leave a field untouched when there is nothing to add.** Some VOs type `region` as Object, and `''` is a cast error where `None` is not. Onslaught logs `incorrect cast value` for a string there but assigns it anyway, so flags still draw.

**The vehicle markers movie is its own world.** `battleVehicleMarkersApp.swf` is a separate movie, not the battle app, and the engine's canvas makes markers only from classes defined in it, calling into them natively: a marker that is not a real subclass of the client's marker symbol classes brings the client down. Those classes come from libraries the app loads after it starts, so a class extending them only verifies once they are in: ours load from `UnicumMarkersApp.onLibsLoadingComplete`, before the app registers with Python. `WG.doLog` rejects calls from mod code; report through an `ExternalInterface` callback Python logs. Images there load with a `Loader` and a path relative to `gui/flash` (`../maps/...`).

**Scaleform images must exist when the client starts.** `img://` resolves through ResMgr, indexed at boot. A URL is treated as a SWF export name and never fetched; a memory texture (`wg_addScaleformTexture`) draws only one image at a time.

**The GFx proxy is fragile.** It reads AS3 getters and `parent`, but interface-typed getters (`window`, `wrapper`) come back `None`. Walking the display tree down from the app root crashed the client with an access violation. Anything Python cannot reach goes through a small AS3 view instead (`as3/`).

**The Stronghold list is a React web page in CEF.** `WebBrowser.executeJavascript` is dead code; `loadURL('javascript:...')` works and the page answers through `console.log`, read from `onConsoleMessage`. Anything sent that way must not contain `%` or `#`, which is why scripts and payloads travel base64-encoded, and the JS must stay ASCII (`atob`). React reuses rows by changing their text and re-renders anything added, so the content script rescans on every mutation, prunes what no longer matches, writes only what differs, and never moves React's nodes (sorting uses CSS `order`). Its columns are addressed by position among the site's own cells, never by English titles.

**Network failure is not an answer.** A timeout, 403 or 5xx must not be cached as "unknown": that once blanked every flag. Only a 200 (or a 404 on a per-entity route) is an answer; failures back off and retry.

**Stale beats blank.** Cached answers are drawn however old while the refresh runs in the background.

# API

`GET /api/{region}/resolve?players=&clans=&tags=` (≤ 100 per kind) returns languages, flag codes, lifetime and 30-day ratings and win rates per player and clan; see the OpenAPI document at `/api/openapi.json` on the server. Absent means the server holds nothing; a 30-day win rate of `null` with recent battles means "not computed yet", so `Entry.rating()` falls back to lifetime. `GET /api/ratings/scales` gives the site's colour bands; each scale declares its unit, and callers say which unit their value is in. Flag codes are Flagpack codes (`GB-UKM`), not ISO.

The API lives in [unicum-gg/unicum.gg](https://github.com/unicum-gg/unicum.gg). If the mod needs data no endpoint serves, the endpoint is added there first; the mod never scrapes the site.

# Conventions

- Keep files under ~400 lines. When one grows past that, split it into modules instead of letting it sprawl.
- No section divider comments (e.g. `# --- X ---`, `// ------`). Split the file instead.
- English only in code, comments and anything shown in the client.
- Python 2.7 in `src/` and `tools/checks/`, Python 3 in the other tools.
- Comments explain why, and keep the history of a decision when the obvious alternative was tried and failed.
- A change to a surface comes with a check in `tools/checks/`, and the suite passes before a commit.
