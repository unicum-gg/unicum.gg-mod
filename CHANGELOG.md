# Changelog

## 0.7.1

### Fixed

- Read the client's battle result types, not our own module
- Stop a recovered battle closing the player's results screen

## 0.7.0

### Added

- Sending a replay in pieces when it is too long for one request
- Ask for a battle's results as soon as it is announced

### Improved

- Set the sort dropdown as far from its edge as the title is from its
- Ask the disk once whether a badge is drawn, not once per draw
- Pick the newest replays by name instead of statting the folder
- Let the battle tab screen rest while it is not on screen
- Announce a reload as its report lands, not half a second later

### Fixed

- Keep the wanted replays through a rate limit
- Let the queue past a replay the server keeps refusing
- Stop offering replays the game will never put on the wire
- Stop freezing the game thread for a second to save the lookup cache
- Announce the reload a change of shell starts

### Removed

- The stack sampler, which broke the game it was measuring

## 0.6.0

### Added

- The ratings to the battle Tab screen, drawn in its page

### Fixed

- Send the ammunition and supplies cost the client reports as tuples
- Stop asking for battle results from inside a battle, and keep the try
- Sample a battle with one timer instead of one per battle
- Count a claim before it is sent, so a synchronous answer cannot break it
- Rebuild the whole receiver list, so the chat keeps its caret
- Take back the panel marker written before the view drew
- Answer whether the battle view draws, instead of always no

## 0.5.2

### Fixed

- The tank page button, the Twitch window and the ratings on the battle
  results screen, none of which appeared on game client 2.4.1.0. That client
  registers a mod's own views itself, and answers the older request with "not
  registered", which reads exactly like a missing file. The mod now declares
  those views the way the client asks for, and still the old way for an
  earlier client.

## 0.5.1

### Fixed

- The mod not loading at all on game client 2.4.1.0. The client moved the
  registry a Scaleform view declares itself in, and the mod read it by name at
  import time, so that one name took everything down with it: no ratings, no
  flags, no panel, nothing. It is now read through the GUI loader, and a
  client that moves it again costs the views that need it rather than the
  whole mod.

## 0.5.0

For game client 2.4.1.0.

### Added

- Report the battles this client played, with everything the game's own
  detailed report shows.
- Sampling where everybody was, while the battle runs, so a battle can be
  watched back on its map at unicum.gg.
- Sending the battle's own replay file, when the client kept one, under a
  setting of its own.
- Report the mark of excellence a battle left the gun at, and send the whole
  fleet's mark progress from the garage, for every tank ever played rather
  than only those still owned.
- A minimap label choice: the vehicle, the player, or both, which can wait for
  Alt like the other battle readings and takes effect without leaving battle.
- A replay tab on the battle results screen.

### Improved

- openwg_gameface 1.2.2, the build this client runs.
- Share battles by default.
- Ask whether the garage is loaded instead of waiting it out.
- Name the Alt row after its screen, not after the other setting.

### Fixed

- Resend only the arena description, so another mod's own labels on the
  players panel survive a rating landing.
- The hangar card offering Connect for a Twitch already linked.

<!-- Not shown, being invisible to a player: thirteen fixes to the battle
     reporting, the replay collection, the mark reading, the minimap labels
     and the results tab, all of them to work added in this same version; one
     code comment; and the release build reading the client version off the
     installed client rather than a mirror that lags a game update.
-->

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
