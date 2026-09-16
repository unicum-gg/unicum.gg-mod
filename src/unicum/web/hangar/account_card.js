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
// Wargaming account logged in only.

const { model, report } = api;
// Replaced by Python with data URIs of web/hangar/panel_icons/*.png.
const PANEL_ICONS = __PANEL_ICONS__;

const state = { alive: true, json: null };

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
const settings = document.createElement("div");
settings.className = "UnicumAccountCard_button";
settings.style.backgroundImage = `url(${PANEL_ICONS.settings})`;
const close = document.createElement("div");
close.className = "UnicumAccountCard_button";
close.style.backgroundImage = `url(${PANEL_ICONS.close})`;

root.appendChild(logo);
root.appendChild(text);
root.appendChild(connect);
root.appendChild(settings);
root.appendChild(close);
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

connect.addEventListener("click", onConnectClick);
settings.addEventListener("click", onSettingsClick);
close.addEventListener("click", onCloseClick);
root.addEventListener("mousedown", stop);

function render(data) {
    const account = data.account || {};
    root.style.display = account.hidden ? "none" : "";
    root.className = "UnicumAccountCard" + (account.linked ? " UnicumAccountCard__linked" : "");
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
    if (!json || json === state.json) {
        return;
    }
    state.json = json;
    try {
        render(JSON.parse(json));
    } catch (error) {
        report(`account card: render failed: ${error}`);
    }
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
        root.removeEventListener("mousedown", stop);
        if (root.parentNode) {
            root.parentNode.removeChild(root);
        }
    },
};
