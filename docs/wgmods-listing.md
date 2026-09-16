# wgmods.net listing (draft)

The text for the mod's page on wgmods.net, in English and Russian (the hub's
official language; other languages need a Russian translation beside them).

## English

### unicum.gg

Player ratings and language flags everywhere in the game, straight from
unicum.gg, and your Twitch chat in battle and in the garage.

**In battle**
- Each player's rating (WN7, WN8 or WNx, overall or last 30 days) and the
  flags of the languages their clan speaks: in the players panel, the Tab
  screen, the loading screen and by the names above vehicles.
- Team averages on the Tab and loading screens.
- Per battle mode, choose whose ratings you see: allies, enemies, or both.
- Optionally, show ratings only while Alt is held.
- Optionally, announce your own reload in the team chat after a shot, as F8 does.

**In the garage**
- Ratings and flags in the contacts list, profile windows, skirmish rooms and
  Stronghold detachment list.
- A unicum.gg button beside the vehicle menu: the tank's page, its marks,
  history and videos, your current build, or the page opened in an AI assistant.

**Twitch (for streamers)**
- Your Twitch chat, with its badges, in the battle chat and in a movable
  garage panel.
- Write in your Twitch chat from the game: the battle chat's TO TWITCH channel
  (Tab), or the garage panel.

**Requirements**
- openwg_gameface (for the garage features).
- Optional: modsSettingsApi (settings window), modsListApi (menu entry).

**Installation**
Put `gg.unicum_<version>.wotmod` into `World_of_Tanks/mods/<game version>/`.
The first start may restart the game once (openwg_gameface registers the
garage button). If ratings show as plain numbers on the very first launch,
restart once: the badges draw from then on.

**What the mod sends, and to whom**
- To unicum.gg (https://unicum.gg): the account ids and clan tags of the
  players on your screen, to get their ratings and languages, and your own
  nickname, to find the Twitch channel linked to it on unicum.gg. Nothing else
  about you unless you link your account.
- Linking your account (the Connect button) is optional. It opens your own
  browser, signs you in on Wargaming with the game's web sign-in (the one the
  game uses to open the Premium Shop), and links the game to your unicum.gg
  account. That sign-in token goes from the game to Wargaming only; unicum.gg
  never receives it. The game then keeps a random key in
  `mods/configs/unicum/account.json`, which only lets it read which account it
  is linked to and send messages to your own Twitch chat.
- Twitch chat is read anonymously from Twitch. Messages you write go through
  unicum.gg, which holds the Twitch permission you granted, and can be revoked
  from your Twitch settings at any time.

**Fair play**
The mod shows public statistics and your own reload only. It does not reveal
enemy positions, reload timers, or anything the game hides.

## Русский

### unicum.gg

Рейтинги игроков и флаги языков по всей игре — прямо с unicum.gg, а также чат
вашего Twitch-канала в бою и в ангаре.

**В бою**
- Рейтинг каждого игрока (WN7, WN8 или WNx, за всё время или за последние 30 дней)
  и флаги языков его клана: в ушах, на экране Tab, на экране загрузки и рядом с
  никами над техникой.
- Средние значения команд на экранах Tab и загрузки.
- Для каждого режима боя можно выбрать, чьи рейтинги видны: союзников,
  противников или обеих команд.
- По желанию: показывать рейтинги только при зажатом Alt.
- По желанию: сообщать команде о своей перезарядке после выстрела, как клавиша F8.

**В ангаре**
- Рейтинги и флаги в списке контактов, в окнах профиля, в комнатах
  отрядов/сражений и в списке отряда Укрепрайона.
- Кнопка unicum.gg рядом с меню техники: страница танка, отметки, история и
  видео, ваша текущая сборка или страница, открытая в ИИ-ассистенте.

**Twitch (для стримеров)**
- Чат вашего Twitch-канала со значками — в боевом чате и в перемещаемой панели
  в ангаре.
- Пишите в свой Twitch-чат из игры: канал TO TWITCH боевого чата (Tab) или
  панель в ангаре.

**Требования**
- openwg_gameface (для функций ангара).
- По желанию: modsSettingsApi (окно настроек), modsListApi (пункт в меню модов).

**Установка**
Поместите `gg.unicum_<версия>.wotmod` в `World_of_Tanks/mods/<версия игры>/`.
При первом запуске игра может один раз перезапуститься (openwg_gameface
регистрирует кнопку ангара). Если при самом первом запуске рейтинги показаны
простыми числами — перезапустите игру один раз: дальше значки отображаются.

**Какие данные мод отправляет и кому**
- На unicum.gg (https://unicum.gg): идентификаторы аккаунтов и теги кланов
  игроков на вашем экране — чтобы получить их рейтинги и языки, а также ваш
  ник — чтобы найти привязанный к нему Twitch-канал на unicum.gg. Больше ничего
  о вас, если вы не привяжете аккаунт.
- Привязка аккаунта (кнопка Connect) необязательна. Она открывает ваш браузер,
  выполняет вход в Wargaming через веб-вход игры (тот же, которым игра открывает
  Премиум магазин) и привязывает игру к вашему аккаунту unicum.gg. Токен этого
  входа передаётся только из игры в Wargaming; unicum.gg его никогда не получает.
  Затем игра хранит случайный ключ в `mods/configs/unicum/account.json`, который
  позволяет лишь узнать, к какому аккаунту привязана игра, и отправлять
  сообщения в ваш собственный Twitch-чат.
- Twitch-чат читается анонимно напрямую с Twitch. Ваши сообщения проходят через
  unicum.gg, у которого есть выданное вами разрешение Twitch; его можно отозвать
  в настройках Twitch в любой момент.

**Честная игра**
Мод показывает только публичную статистику и вашу собственную перезарядку. Он
не раскрывает позиции противников, их таймеры перезарядки или что-либо ещё,
что скрывает игра.
