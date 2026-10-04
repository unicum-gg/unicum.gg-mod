# Changelog

## 0.4.1

### Fixed

- In the battle players list, the language flags no longer sit a couple of pixels above the badges beside them.
- On the loading screen, an image tag no longer shows for a moment next to the team names while the ratings are waiting for Alt.

## 0.4.0

### Added

- Your tank setups on your own unicum.gg page: equipment, directives, crew skills, field modifications, ammunition and consumables, for every vehicle in your garage. Sent when they change and when you take a tank into battle. On by default; untick Share my loadouts in the settings to stop, and everything already sent is deleted. Supporters can keep theirs off their public page while still contributing to the figures.
- Every rating now carries the player's win rate and battle count beside it, as badges in the same style. Each has its own switch and its own period, and the win rate can be shown to a tenth of a point.
- The Twitch chat a battle opens on carries what was said before it started, instead of opening empty.
- A Measure what this mod costs switch: it times what the mod does on the game's own thread, and samples which mod that thread is actually in, writing a table to python.log every ten seconds. For answering a frame rate question with a number instead of a guess.

### Improved

- The mod no longer lists a folder nine times a second in battle. That one call was 3.5% of all the Python the game's own thread ran.

### Fixed

- The contacts list no longer draws flags and badges over the player's name while its images are still loading.

## 0.3.0

### Added

- Right-click a player, anywhere in the game, and open their unicum.gg page or hand it to ChatGPT, Claude or Scira. In battle, in the battle results, in your contacts and in a skirmish room.
- The same on any tank: the carousel, the tech tree, the shop and the comparison.
- Two switches in the settings turn each of them off.

### Changed

- Installing is only the two files in the archive now. The mod makes what it needs on its first run and restarts the game once, so ratings are coloured badges from your very first battle instead of bare numbers.

## 0.2.0

### Added

- A settings box that brings back the unicum.gg account card once closed
- A notice saying where the account card went when it is closed
- The garage twitch panel to the battle queue screen, in a window of its own
- The twitch panel to the battle loading screen
- A unicum.gg tab to the game's own settings window
- A support button to both settings pages
- Discord and github links beside the support button
- The alt only choice to the skirmish room
- The stronghold alt choice, a reset button and a scrolling page
- Announcing reloads for autoloaders only
- One command that cuts a release from the commits

### Improved

- The hot reload note to say a changed AS3 class waits for its app to be rebuilt
- The settings page into a garage and a battle column, one dropdown per screen, mode and alt choice
- The tank menu button icon to the hangar's own brushed silver
- The battle markers to place themselves only when something moved
- The vehicle markers to draw their shadow without a filter
- The ai entries to name the build instead of encoding it
- The written build to read as a list
- The chatgpt entry to open the page carrying the build

### Fixed

- The twitch panel notice naming a settings box that does not exist
- The team average showing its image markup as text while the battle view is still loading
- The skirmish room's member list jumping as it refreshes
- The settings tab's ground to start under its sub-tabs, with no frame
- The settings tab's buttons never reaching python
- The settings tab reaching python, and its dropdowns' row count
- The skirmish sort order not coming back from the view
- A team losing its average on the tab screen
- The skirmish sort menu showing five rows whatever it holds
- The markers covering what appears beside a row
- The claude and chatgpt entries handing a link they refuse to open
- The scroll bar running to the very bottom of the page
- The page missing the fade at its edges and its scroll bar sitting too far right
- Settings tab fade and scroll bar to match the General tab
- The release finding the client's python, not a name no PATH holds
