// The player's Twitch chat in the garage: messages as they come, and a field
// to write in the chat.
//
// Run by the loader (res/gui/gameface/mods/unicum/TankButton/TankButton.js)
// beside the tank menu, as the body of a function of `api` = { model, media,
// playSound, report }, and run again whenever this file changes: it returns
// { stop() }, which takes back everything it added. Python
// (src/unicum/twitch_panel.py) puts the chat in the model's `twitch` string
// as JSON; the panel reads it on a timer, since the model observer has no way
// to unsubscribe and every reload would stack one more callback. What the
// player does goes back through the model's onItemClick: twitchSend,
// twitchConnect, twitchCollapse, twitchMove ("left,top" in rem, or "" for the
// panel's own place under the mission widgets) and twitchResize
// ("width,height" in rem, or "" for the stylesheet's size).
//
// Gameface: a plain focused <input type="text"> is what the game's own chats
// use, and the hangar's hotkeys skip themselves while one has focus. Images
// are sized divs with a background (an <img> ignores its size). Scrolling is
// done by hand on an overflow: hidden list, as the game does.

const { model, report } = api;
// Replaced by Python with data URIs of web/hangar/panel_icons/*.png.
const PANEL_ICONS = __PANEL_ICONS__;

const state = {
    alive: true, json: null, data: null, stuckToBottom: true, drag: null, resize: null,
    // The key code that types "a" on this keyboard, and the last key typed.
    selectAllKey: 65, lastKey: 0,
};

// Pixels to the rem the hangar lays out in; 1 when the view does not say.
const toRem = (px) => (typeof viewEnv !== "undefined" && viewEnv.pxToRem ? viewEnv.pxToRem(px) : px);
const DRAG_THRESHOLD = 4;

const root = document.createElement("div");
root.className = "UnicumTwitchPanel";
// Hidden until Python has said anything: a button made before this panel
// existed has no `twitch` property at all.
root.style.display = "none";

const header = document.createElement("div");
header.className = "UnicumTwitchPanel_header";
const logo = document.createElement("div");
logo.className = "UnicumTwitchPanel_logo";
const heading = document.createElement("div");
heading.className = "UnicumTwitchPanel_heading";
const title = document.createElement("div");
title.className = "UnicumTwitchPanel_title";
// Only without a channel, where the panel folds into a card like the account's.
const subtitle = document.createElement("div");
subtitle.className = "UnicumTwitchPanel_subtitle";
subtitle.textContent = "Link your Twitch to see your chat here";
heading.appendChild(title);
heading.appendChild(subtitle);
const cardConnect = document.createElement("div");
cardConnect.className = "UnicumTwitchPanel_cardConnect";
cardConnect.textContent = "Connect";
// Under the header, across the card, as on the account card.
const reset = document.createElement("div");
reset.className = "UnicumTwitchPanel_reset";
// An image: the hangar's font has no arrow glyphs, so a "↺" drew nothing.
reset.style.backgroundImage = `url(${PANEL_ICONS.reset})`;
const toggle = document.createElement("div");
toggle.className = "UnicumTwitchPanel_toggle";
const close = document.createElement("div");
close.className = "UnicumTwitchPanel_close";
close.style.backgroundImage = `url(${PANEL_ICONS.close})`;
header.appendChild(logo);
header.appendChild(heading);
header.appendChild(reset);
header.appendChild(toggle);
header.appendChild(close);

const list = document.createElement("div");
list.className = "UnicumTwitchPanel_list";
const lines = document.createElement("div");
lines.className = "UnicumTwitchPanel_lines";
// A chat nobody has written in yet looks exactly like a panel that failed to
// load, so the list says which it is until the first message arrives.
const empty = document.createElement("div");
empty.className = "UnicumTwitchPanel_empty";
const emptyTitle = document.createElement("div");
emptyTitle.className = "UnicumTwitchPanel_emptyTitle";
const emptyText = document.createElement("div");
emptyText.className = "UnicumTwitchPanel_emptyText";
empty.appendChild(emptyTitle);
empty.appendChild(emptyText);
list.appendChild(lines);
list.appendChild(empty);

const footer = document.createElement("div");
footer.className = "UnicumTwitchPanel_footer";
const input = document.createElement("input");
input.type = "text";
input.maxLength = 500;
input.className = "UnicumTwitchPanel_input";
input.placeholder = "Send a message";
const connect = document.createElement("div");
connect.className = "UnicumTwitchPanel_connect";
connect.textContent = "Connect to write in your chat";
footer.appendChild(input);
footer.appendChild(connect);

// Bottom right, as every resizable window in the game: drag to size the panel.
const grip = document.createElement("div");
grip.className = "UnicumTwitchPanel_grip";

root.appendChild(header);
root.appendChild(cardConnect);
root.appendChild(list);
root.appendChild(footer);
root.appendChild(grip);
document.body.appendChild(root);

function send(item, text) {
    if (model.model) {
        model.model.onItemClick({ item, text: text === undefined ? "" : String(text) });
    }
}

function stop(event) {
    event.stopPropagation();
}

function onHeaderMouseDown(event) {
    if (event.button !== undefined && event.button !== 0) {
        return;
    }
    event.stopPropagation();
    const rect = root.getBoundingClientRect();
    state.drag = { x: event.clientX, y: event.clientY, left: rect.left, top: rect.top, moved: false };
    document.addEventListener("mousemove", onDragMove);
    document.addEventListener("mouseup", onDragEnd);
}

function onDragMove(event) {
    const drag = state.drag;
    if (!drag) {
        return;
    }
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.moved && Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD) {
        return;
    }
    if (!drag.moved) {
        drag.moved = true;
        root.classList.add("UnicumTwitchPanel__dragging");
        // On the page too, or the cursor changes back as soon as it leaves the header.
        drag.cursor = document.body.style.cursor;
        document.body.style.cursor = "grabbing";
    }
    const rect = root.getBoundingClientRect();
    const left = Math.min(Math.max(0, drag.left + dx), Math.max(0, window.innerWidth - rect.width));
    const top = Math.min(Math.max(0, drag.top + dy), Math.max(0, window.innerHeight - rect.height));
    place([toRem(left), toRem(top)]);
    event.stopPropagation();
}

function onDragEnd(event) {
    const drag = state.drag;
    state.drag = null;
    document.removeEventListener("mousemove", onDragMove);
    document.removeEventListener("mouseup", onDragEnd);
    if (!drag) {
        return;
    }
    event.stopPropagation();
    if (drag.moved) {
        root.classList.remove("UnicumTwitchPanel__dragging");
        document.body.style.cursor = drag.cursor || "";
        const rect = root.getBoundingClientRect();
        send("twitchMove", `${Math.round(toRem(rect.left))},${Math.round(toRem(rect.top))}`);
    } else if (state.data) {
        state.data.collapsed = !state.data.collapsed;
        renderFrame(state.data);
        send("twitchCollapse", state.data.collapsed ? "1" : "0");
    }
}

function onGripMouseDown(event) {
    if (event.button !== undefined && event.button !== 0) {
        return;
    }
    event.stopPropagation();
    const rect = root.getBoundingClientRect();
    state.resize = { x: event.clientX, y: event.clientY,
                     width: toRem(rect.width), height: toRem(rect.height),
                     left: rect.left, top: rect.top };
    document.addEventListener("mousemove", onResizeMove);
    document.addEventListener("mouseup", onResizeEnd);
}

function onResizeMove(event) {
    const resize = state.resize;
    if (!resize) {
        return;
    }
    event.stopPropagation();
    // Never past the screen: the panel is dragged by a corner that would
    // otherwise end up somewhere the player cannot reach it again.
    const room = { width: toRem(window.innerWidth - resize.left), height: toRem(window.innerHeight - resize.top) };
    const width = Math.round(Math.min(Math.max(resize.width + toRem(event.clientX - resize.x), MIN_WIDTH),
                                      Math.min(MAX_WIDTH, room.width)));
    const height = Math.round(Math.min(Math.max(resize.height + toRem(event.clientY - resize.y), MIN_HEIGHT),
                                       Math.min(MAX_HEIGHT, room.height)));
    resize.wanted = [width, height];
    size(resize.wanted);
    if (state.stuckToBottom) {
        list.scrollTop = Math.max(0, lines.offsetHeight - list.clientHeight);
    }
}

function onResizeEnd(event) {
    const resize = state.resize;
    state.resize = null;
    document.removeEventListener("mousemove", onResizeMove);
    document.removeEventListener("mouseup", onResizeEnd);
    if (!resize) {
        return;
    }
    event.stopPropagation();
    if (resize.wanted) {
        if (state.data) {
            state.data.size = resize.wanted;
        }
        send("twitchResize", `${resize.wanted[0]},${resize.wanted[1]}`);
    }
}

// Learns the layout: the key last pressed, and the letter it put in the field.
function onInput() {
    const at = input.selectionStart;
    const typed = at > 0 ? input.value.charAt(at - 1).toLowerCase() : "";
    if (typed === "a" && state.lastKey) {
        state.selectAllKey = state.lastKey;
    }
}

function onResetMouseDown(event) {
    event.stopPropagation();
}

function onResetClick(event) {
    event.stopPropagation();
    if (state.data) {
        state.data.position = null;
        state.data.size = null;
        renderFrame(state.data);
    }
    send("twitchMove", "");
    send("twitchResize", "");
}

// Turns the panel off in the settings; the settings window turns it back on.
function onCloseClick(event) {
    event.stopPropagation();
    root.style.display = "none";
    send("twitchClose");
}

// The gap the hangar leaves between two mission cards.
const CARD_GAP = 8;
// The panel's parts, in rem, as the stylesheet draws them: the list is what is
// left of the panel once the header, the footer and the two borders are taken.
const HEADER_HEIGHT = 34;
const FOOTER_HEIGHT = 40;
const BORDERS = 2;
const LIST_PADDING = 12;
// Small enough to tuck away, large enough for a name and a line of chat. The
// same bounds as the settings' (src/unicum/settings.py), which has the last word.
const MIN_WIDTH = 220;
const MIN_HEIGHT = 120;
const MAX_WIDTH = 1600;
const MAX_HEIGHT = 1200;
// The stylesheet's own size, which the panel keeps until the player drags it.
const DEFAULT_WIDTH = 322;
const DEFAULT_HEIGHT = 220;

// The panel at the size the player dragged it to, or the stylesheet's.
function size(wanted) {
    const collapsed = root.classList.contains("UnicumTwitchPanel__collapsed");
    const compact = root.classList.contains("UnicumTwitchPanel__compact");
    root.style.width = wanted ? `${wanted[0]}rem` : "";
    // Folded or without a chat, the height is the class's; the width is kept.
    root.style.height = wanted && !collapsed && !compact ? `${wanted[1]}rem` : "";
    const height = wanted ? wanted[1] - HEADER_HEIGHT - FOOTER_HEIGHT - BORDERS : 0;
    list.style.height = height > 0 ? `${height}rem` : "";
    empty.style.height = height > 0 ? `${height - LIST_PADDING}rem` : "";
}

// How far down the hangar's widget column goes: the tank carousel's top edge,
// the page's bottom where a screen has no carousel. The mission cards and the
// account card stop well short of it, but the panel hangs under them and, with
// the account card's Connect adding a row, it ended up flush against the
// carousel.
function floorOf() {
    const carousel = document.querySelector('[class*="Page_carousel"]');
    if (carousel) {
        const rect = carousel.getBoundingClientRect();
        if (rect.height > 0 && rect.top > 0) {
            return rect.top;
        }
    }
    const page = document.querySelector('[class*="HangarScreen_hangarPage"]');
    if (page) {
        const rect = page.getBoundingClientRect();
        if (rect.bottom > 0) {
            return rect.bottom;
        }
    }
    return window.innerHeight;
}

// The panel shortened to what is left above that floor, when what it is asking
// for does not fit. Shorter beats hidden behind the carousel; the player's own
// size is left in the settings, so a screen with room enough shows it again.
function fit() {
    if (root.classList.contains("UnicumTwitchPanel__collapsed")
            || root.classList.contains("UnicumTwitchPanel__compact")) {
        return;
    }
    const wanted = state.data && state.data.size;
    const room = Math.round(toRem(floorOf() - root.getBoundingClientRect().top)) - CARD_GAP;
    const height = wanted ? wanted[1] : DEFAULT_HEIGHT;
    if (room < height) {
        size([wanted ? wanted[0] : DEFAULT_WIDTH, Math.max(MIN_HEIGHT, room)]);
    } else {
        size(wanted);
    }
}

// Where the player put the panel, or its own place: right under the account
// card when it is on screen (its height changes with the link), else the
// stylesheet's.
function place(position) {
    if (position) {
        root.style.left = `${position[0]}rem`;
        root.style.top = `${position[1]}rem`;
        root.style.right = "auto";
        return;
    }
    root.style.left = "";
    root.style.right = "";
    const card = document.querySelector(".UnicumAccountCard");
    const rect = card && card.style.display !== "none" ? card.getBoundingClientRect() : null;
    root.style.top = rect && rect.height > 0 ? `${Math.round(toRem(rect.bottom)) + CARD_GAP}rem` : "";
    if (!state.resize) {
        fit();
    }
}

function onConnectClick(event) {
    event.stopPropagation();
    send("twitchConnect");
}

function handled(event) {
    event.stopPropagation();
    event.preventDefault();
    if (typeof viewEnv !== "undefined" && viewEnv.setEventHandled) {
        viewEnv.setEventHandled();
    }
}

function onKeyDown(event) {
    if (!event.ctrlKey && !event.metaKey && !event.altKey) {
        state.lastKey = event.keyCode;
    }
    if (event.key === "Enter" || event.keyCode === 13) {
        const text = input.value.trim();
        if (text) {
            send("twitchSend", text);
            input.value = "";
            state.stuckToBottom = true;
        }
        handled(event);
    } else if (event.key === "Escape" || event.keyCode === 27) {
        input.blur();
        handled(event);
    } else if ((event.ctrlKey || event.metaKey) && event.keyCode === state.selectAllKey) {
        // Gameface's input has no select-all of its own. Its key events name
        // a key by its QWERTY place whatever the layout, so the key that types
        // "a" is learnt from typing (onInput): Q on AZERTY, A until then.
        try {
            input.select();
        } catch (error) {
            report(`twitch panel: select failed: ${error}`);
        }
        try {
            input.setSelectionRange(0, input.value.length);
        } catch (error) {
            report(`twitch panel: setSelectionRange failed: ${error}`);
        }
        handled(event);
    } else {
        event.stopPropagation();
    }
}

function onWheel(event) {
    event.stopPropagation();
    event.preventDefault();
    const max = Math.max(0, lines.offsetHeight - list.clientHeight);
    list.scrollTop = Math.min(max, Math.max(0, list.scrollTop + event.deltaY));
    state.stuckToBottom = list.scrollTop >= max - 4;
}

input.addEventListener("input", onInput);
header.addEventListener("mousedown", onHeaderMouseDown);
reset.addEventListener("mousedown", onResetMouseDown);
reset.addEventListener("click", onResetClick);
close.addEventListener("mousedown", onResetMouseDown);
close.addEventListener("click", onCloseClick);
grip.addEventListener("mousedown", onGripMouseDown);
connect.addEventListener("click", onConnectClick);
cardConnect.addEventListener("mousedown", onResetMouseDown);
cardConnect.addEventListener("click", onConnectClick);
input.addEventListener("keydown", onKeyDown);
input.addEventListener("keyup", stop);
root.addEventListener("mousedown", stop);
root.addEventListener("wheel", onWheel);

function line(message) {
    const row = document.createElement("div");
    row.className = "UnicumTwitchPanel_line";
    for (const badge of message.badges || []) {
        const image = document.createElement("div");
        image.className = "UnicumTwitchPanel_badge";
        image.style.backgroundImage = `url(${badge})`;
        row.appendChild(image);
    }
    const name = document.createElement("span");
    name.className = "UnicumTwitchPanel_name";
    name.textContent = `${message.name}:`;
    if (message.color) {
        name.style.color = message.color;
    }
    const text = document.createElement("span");
    text.className = "UnicumTwitchPanel_text";
    text.textContent = message.text;
    row.appendChild(name);
    row.appendChild(text);
    return row;
}

// The panel's frame alone: shown, folded, where. What a click changes, drawn
// at once rather than after the round trip through Python.
function renderFrame(data) {
    root.style.display = data.shown ? "" : "none";
    // No channel, no chat to show: a card with its Connect, as the account's.
    const compact = !data.channel;
    root.className = "UnicumTwitchPanel" + (compact ? " UnicumTwitchPanel__compact" : "") +
        (data.collapsed && !compact ? " UnicumTwitchPanel__collapsed" : "") +
        (state.drag && state.drag.moved ? " UnicumTwitchPanel__dragging" : "");
    if (!state.resize) {
        size(data.size);
    }
    if (!state.drag) {
        place(data.position);
    }
    // The arrow puts the panel back where and as the stylesheet has it.
    reset.style.display = data.position || data.size ? "" : "none";
    logo.style.backgroundImage = data.icon ? `url(${data.icon})` : "";
    title.textContent = data.channel ? `Twitch · ${data.channel}` : "Twitch";
    toggle.style.backgroundImage = `url(${data.collapsed ? PANEL_ICONS.expand : PANEL_ICONS.collapse})`;
    input.style.display = data.linked ? "" : "none";
    connect.style.display = data.linked ? "none" : "";
}

function render(data) {
    renderFrame(data);
    while (lines.firstChild) {
        lines.removeChild(lines.firstChild);
    }
    const messages = data.messages || [];
    for (const message of messages) {
        lines.appendChild(line(message));
    }
    // Twitch sends no history, so a chat that is quiet stays blank however
    // long it has been joined: say so rather than leave an empty box.
    empty.style.display = messages.length ? "none" : "";
    emptyTitle.textContent = data.joined ? "No messages yet" : "Connecting to the chat";
    emptyText.textContent = data.joined
        ? `What is written in ${data.channel}'s chat from now on shows up here.`
        : `Joining ${data.channel}'s chat on Twitch.`;
    if (state.stuckToBottom) {
        list.scrollTop = Math.max(0, lines.offsetHeight - list.clientHeight);
    }
}

function poll() {
    if (!state.alive) {
        return;
    }
    const current = model.model;
    const json = current && current.twitch;
    if (!json || json === state.json) {
        // The account card can change height on its own: follow it.
        if (state.data && !state.data.position && !state.drag) {
            place(null);
        }
        return;
    }
    state.json = json;
    try {
        state.data = JSON.parse(json);
        render(state.data);
        // A second pass once the new lines have a height.
        setTimeout(() => state.alive && state.stuckToBottom && render(state.data), 50);
    } catch (error) {
        report(`twitch panel: render failed: ${error}`);
    }
}

const timer = setInterval(poll, 250);
poll();

return {
    stop() {
        state.alive = false;
        clearInterval(timer);
        if (state.drag && state.drag.moved) {
            document.body.style.cursor = state.drag.cursor || "";
        }
        input.removeEventListener("input", onInput);
        header.removeEventListener("mousedown", onHeaderMouseDown);
        reset.removeEventListener("mousedown", onResetMouseDown);
        reset.removeEventListener("click", onResetClick);
        close.removeEventListener("mousedown", onResetMouseDown);
        close.removeEventListener("click", onCloseClick);
        grip.removeEventListener("mousedown", onGripMouseDown);
        document.removeEventListener("mousemove", onDragMove);
        document.removeEventListener("mouseup", onDragEnd);
        document.removeEventListener("mousemove", onResizeMove);
        document.removeEventListener("mouseup", onResizeEnd);
        connect.removeEventListener("click", onConnectClick);
        cardConnect.removeEventListener("mousedown", onResetMouseDown);
        cardConnect.removeEventListener("click", onConnectClick);
        input.removeEventListener("keydown", onKeyDown);
        input.removeEventListener("keyup", stop);
        root.removeEventListener("mousedown", stop);
        root.removeEventListener("wheel", onWheel);
        if (root.parentNode) {
            root.parentNode.removeChild(root);
        }
    },
};
