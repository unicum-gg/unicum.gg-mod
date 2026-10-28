// The unicum.gg account card in the garage, under the mission widgets: Connect
// while the game is not linked to an account, who it is linked to once it is.
//
// Run by the loader (res/gui/gameface/mods/unicum/TankButton/TankButton.js)
// beside the tank menu and the Twitch panel, as the body of a function of
// `api` = { model, media, playSound, report }, and run again whenever this file
// changes: it returns { stop() }. It reads the same JSON as the Twitch panel,
// the loader model's `twitch` string (src/unicum/twitch_panel.py), for its
// `account` = { linked, name, hidden }; Connect sends accountConnect through
// the model's onItemClick, which links the account alone
// (src/unicum/game_link.py), the gear accountSettings, which opens the mod's
// settings window, and the cross accountHide, which hides the card for the
// Wargaming account logged in only. Linked, the card itself sends
// accountProfile, which opens the player's own page on the site: the hangar's
// cards are clickable and this one sat beside them doing nothing.
//
// The card is not painted by this mod: it wears the hangar's own decor classes,
// read off a real mission card below. account_card.css says why.

const { model, report } = api;
// Replaced by Python with data URIs of web/hangar/panel_icons/*.png.
const PANEL_ICONS = __PANEL_ICONS__;

// `linked` decides whether the card is a link at all: unlinked there is no
// page to open, and the Connect button is the only thing to press. `data` is
// the last state rendered, so the card can be drawn again once the hangar has
// lent its decor; `decor` is what it lent.
const state = { alive: true, json: null, data: null, linked: false, decor: null };

// Pixels to the rem the hangar lays out in; 1 when the view does not say.
const toRem = (px) => (typeof viewEnv !== "undefined" && viewEnv.pxToRem ? viewEnv.pxToRem(px) : px);
// The hangar's mission cards, daily and personal; their classes carry a hash.
const MISSION_CARDS = '[class*="QuestCard_base"], [class*="PersonalMissionCard_base"]';
// The gap the hangar leaves between two mission cards.
const CARD_GAP = 8;

// The three layers the hangar paints a card with, each a class on a child of
// the card: the white veil, the border that colours in under the pointer, and
// the noise fill. The hash in every one of those names changes with each
// client build, so they are found by their stable half and then kept whole.
const DECOR = [
    { key: "veil", needle: "hoverBg", exact: /^[A-Za-z]+_hoverBg_[0-9a-f]+$/ },
    { key: "border", needle: "Card_border_", exact: /^Card_border_[0-9a-f]+$/ },
    { key: "fill", needle: "Card_borderHelper_", exact: /^Card_borderHelper_[0-9a-f]+$/ },
];

const root = document.createElement("div");
root.className = "UnicumAccountCard";
root.style.display = "none";

const logo = document.createElement("div");
logo.className = "UnicumAccountCard_logo";
logo.style.backgroundImage = `url(${PANEL_ICONS.unicum})`;
const text = document.createElement("div");
text.className = "UnicumAccountCard_text";
const title = document.createElement("div");
title.className = "UnicumAccountCard_title";
const subtitle = document.createElement("div");
subtitle.className = "UnicumAccountCard_subtitle";
text.appendChild(title);
text.appendChild(subtitle);
const connect = document.createElement("div");
connect.className = "UnicumAccountCard_connect";
connect.textContent = "Connect";
// Under the rest, across the card, which leaves the text the card's width.
const settings = document.createElement("div");
settings.className = "UnicumAccountCard_button";
settings.style.backgroundImage = `url(${PANEL_ICONS.settings})`;
const close = document.createElement("div");
close.className = "UnicumAccountCard_button";
close.style.backgroundImage = `url(${PANEL_ICONS.close})`;

const row = document.createElement("div");
row.className = "UnicumAccountCard_row";
row.appendChild(logo);
row.appendChild(text);
row.appendChild(settings);
row.appendChild(close);
root.appendChild(row);
root.appendChild(connect);
document.body.appendChild(root);

function stop(event) {
    event.stopPropagation();
}

function onConnectClick(event) {
    event.stopPropagation();
    if (model.model) {
        model.model.onItemClick({ item: "accountConnect", text: "" });
    }
    subtitle.textContent = "Finish in your browser";
}

// Hides the card for the account logged in; another account shows it again.
function onCloseClick(event) {
    event.stopPropagation();
    root.style.display = "none";
    if (model.model) {
        model.model.onItemClick({ item: "accountHide", text: "" });
    }
}

// Opens the mod's settings window, on the unicum.gg page.
function onSettingsClick(event) {
    event.stopPropagation();
    if (model.model) {
        model.model.onItemClick({ item: "accountSettings", text: "" });
    }
}

// The card itself: the player's own page on the site. The gear, the cross and
// Connect all stop the click before it gets here, so each keeps its own job.
function onCardClick(event) {
    event.stopPropagation();
    if (!state.linked || !model.model) {
        return;
    }
    model.model.onItemClick({ item: "accountProfile", text: "" });
}

connect.addEventListener("click", onConnectClick);
settings.addEventListener("click", onSettingsClick);
close.addEventListener("click", onCloseClick);
root.addEventListener("click", onCardClick);
root.addEventListener("mousedown", stop);

// Right under the lowest mission card on the right of the screen: how many
// there are changes with the missions, the events and the screen's size. The
// stylesheet's place when there are none.
function shown(element) {
    for (let node = element; node && node !== document.body; node = node.parentElement) {
        const style = getComputedStyle(node);
        if (style.opacity === "0" || style.visibility === "hidden" || style.display === "none") {
            return false;
        }
    }
    return true;
}

// The mission cards on show, which are the ones this card follows and borrows
// from. The hangar keeps cards laid out but transparent below the ones on show
// (missions done, cards on their way in or out): not a place to follow, and
// not a card to read a style off either.
function missionCards() {
    const cards = [];
    for (const card of document.querySelectorAll(MISSION_CARDS)) {
        const rect = card.getBoundingClientRect();
        if (rect.height > 0 && rect.left > window.innerWidth / 2 && shown(card)) {
            cards.push(card);
        }
    }
    return cards;
}

function place() {
    let bottom = 0;
    for (const card of missionCards()) {
        bottom = Math.max(bottom, card.getBoundingClientRect().bottom);
    }
    root.style.top = bottom > 0 ? `${Math.round(toRem(bottom)) + CARD_GAP}rem` : "";
}

function classesOf(node) {
    return String(node.className || "").split(/\s+/).filter(Boolean);
}

function classMatching(node, exact) {
    for (const name of classesOf(node)) {
        if (exact.test(name)) {
            return name;
        }
    }
    return null;
}

// What a mission card is drawn with: its own class, which styles the layers and
// which the hangar hangs its :hover rules off, and the class of each layer.
// Null for a card this cannot read, which leaves the fallback in place.
function readDecor(card) {
    const base = classMatching(card, /^Card_[0-9a-f]+$/);
    if (!base) {
        return null;
    }
    const layers = [];
    for (const spec of DECOR) {
        const node = card.querySelector(`[class*="${spec.needle}"]`);
        const name = node ? classMatching(node, spec.exact) : null;
        if (name) {
            layers.push({ key: spec.key, name: name });
        }
    }
    if (!layers.length) {
        return null;
    }
    // Two classes drive the hover, and neither is one of the layers': the
    // card's `enabled` class fades the fill in and colours the border, and its
    // component class fades the veil. That component class carries a hash of
    // its own, so it is found through the veil's name rather than guessed.
    const veil = layers.filter((layer) => layer.key === "veil")[0];
    const prefix = veil ? veil.name.split("_")[0] : null;
    return {
        base: base,
        enabled: classMatching(card, /^Card_card__enabled_[0-9a-f]+$/),
        component: prefix ? classMatching(card, new RegExp(`^${prefix}_[0-9a-f]+$`)) : null,
        layers: layers,
    };
}

// The layers go in ahead of the content, in the hangar's own order: the veil
// under the border, the noise fill over both, this card's own content above
// all three (account_card.css).
function addLayers(decor) {
    for (const layer of decor.layers) {
        const node = document.createElement("div");
        node.className = layer.name;
        if (layer.key === "veil") {
            // The client parks the veil at z-index -1, which puts it behind
            // the nearest stacking context rather than behind its own card.
            // For the hangar's cards that context is the card; for this one it
            // would be the page, and the veil would go under the hangar. It is
            // pinned here instead, and draws the same, in the same place in
            // the pile.
            node.style.zIndex = "0";
        }
        root.insertBefore(node, row);
    }
}

// Reads the hangar's decor once and keeps it: the hashes in those class names
// hold for the life of a client build, and the loader runs this script again
// on every new hangar. Says whether this call is the one that found it.
function syncDecor() {
    if (state.decor) {
        return false;
    }
    const cards = missionCards();
    const decor = cards.length ? readDecor(cards[0]) : null;
    if (!decor) {
        return false;
    }
    state.decor = decor;
    addLayers(decor);
    report(`account card: drawn by the hangar (${decor.layers.length} layers, ${decor.base})`);
    return true;
}

function render(data) {
    const account = data.account || {};
    state.data = data;
    state.linked = Boolean(account.linked);
    root.style.display = account.hidden ? "none" : "";
    const names = ["UnicumAccountCard"];
    if (account.linked) {
        names.push("UnicumAccountCard__linked");
    }
    if (state.decor) {
        names.push(state.decor.base);
        // The hover classes only while the card is a link: a card that lights
        // up under the pointer and then opens nothing is worse than a quiet one.
        if (account.linked) {
            for (const name of [state.decor.enabled, state.decor.component]) {
                if (name) {
                    names.push(name);
                }
            }
        }
    } else {
        names.push("UnicumAccountCard__plain");
    }
    root.className = names.join(" ");
    if (account.linked) {
        title.textContent = "unicum.gg";
        subtitle.textContent = account.name ? `Connected as ${account.name}` : "Connected";
        connect.style.display = "none";
    } else {
        title.textContent = "Link your unicum.gg account";
        subtitle.textContent = "Sign in with Wargaming, nothing to type";
        connect.style.display = "";
    }
}

function poll() {
    if (!state.alive) {
        return;
    }
    const current = model.model;
    const json = current && current.twitch;
    if (root.style.display !== "none") {
        place();
    }
    // The hangar's cards can arrive after this script does: until they do the
    // card is drawn plainly, and drawn again here as soon as they are there.
    if (syncDecor() && state.data) {
        render(state.data);
    }
    if (!json || json === state.json) {
        return;
    }
    state.json = json;
    try {
        render(JSON.parse(json));
    } catch (error) {
        report(`account card: render failed: ${error}`);
    }
    place();
}

const timer = setInterval(poll, 250);
poll();


return {
    stop() {
        state.alive = false;
        clearInterval(timer);
        connect.removeEventListener("click", onConnectClick);
        settings.removeEventListener("click", onSettingsClick);
        close.removeEventListener("click", onCloseClick);
        root.removeEventListener("click", onCardClick);
        root.removeEventListener("mousedown", stop);
        if (root.parentNode) {
            root.parentNode.removeChild(root);
        }
    },
};
