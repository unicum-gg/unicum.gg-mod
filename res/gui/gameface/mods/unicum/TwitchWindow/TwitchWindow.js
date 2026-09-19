// Loader for the unicum.gg Twitch window: the garage's Twitch panel, where
// the hangar and the panel with it are gone (the battle queue screen).
//
// Opened by src/unicum/twitch_window.py as a window of its own, panel-sized.
// Like the tank button's loader (../TankButton/TankButton.js) it holds no
// feature of its own, so it never needs to change: the panel is
// src/unicum/web/hangar/twitch_panel.js and .css, the garage's very code,
// which Python puts in this view's model (`script`, `style`) with a new
// `revision` whenever they change on disk. It runs as
// new Function("api", script)(api) with api.windowed set, and returns
// { stop() }.
//
// Its one job of its own is the window's size. Gameface does not size a
// window from its content: until told, the window keeps a fallback size, and
// telling it too early does nothing. So once the engine and the page are
// ready and laid out, the window is given the panel's size, again whenever
// the panel changes it (folded, unfolded), and Python hears of it
// (twitchWindowSize) to place the window.
import { MediaContext } from "../../libs/media.js";
import { ModelObserver } from "../../libs/model.js";
import { playSound } from "../../libs/sound.js";

const media = MediaContext();
const model = ModelObserver();
const style = document.createElement("style");

let running = null;
let loaded = null;
let sized = "";

function send(item, text) {
    if (model.model) {
        model.model.onItemClick({ item, text: String(text).slice(0, 4000) });
    }
}

function report(text) {
    send("log", text);
}

// The client's language on the page, as the game's pages have it, for the
// fonts TwitchWindow.html picks by it.
function setLanguage(current) {
    try {
        const lang = JSON.parse(current.twitch).lang;
        if (lang && document.documentElement.lang !== lang) {
            document.documentElement.lang = lang;
        }
    } catch (error) {
        // No state yet.
    }
}

function load() {
    const current = model.model;
    if (current) {
        setLanguage(current);
    }
    if (!current || !current.script || current.revision === loaded) {
        return;
    }
    loaded = current.revision;
    if (running) {
        try {
            running.stop();
        } catch (error) {
            report(`twitch window: stop failed: ${error}`);
        }
        running = null;
    }
    style.textContent = current.style || "";
    try {
        running = new Function("api", current.script)({ model, media, playSound, report, windowed: true });
    } catch (error) {
        report(`twitch window: script failed: ${error} ${error && error.stack ? error.stack : ""}`);
    }
}

// The window at the panel's size, in pixels, when that size changes.
function fit() {
    const panel = document.querySelector(".UnicumTwitchPanel");
    if (!panel || panel.style.display === "none") {
        return;
    }
    const rect = panel.getBoundingClientRect();
    const width = Math.ceil(rect.width);
    const height = Math.ceil(rect.height);
    const text = `${width},${height}`;
    if (!width || !height || text === sized) {
        return;
    }
    sized = text;
    viewEnv.resizeViewPx(width, height);
    send("twitchWindowSize", text);
}

const domBuilt = window.isDomBuilt
    ? Promise.resolve()
    : new Promise((resolve) => engine.on("self.onDomBuilt", resolve));

Promise.all([engine.whenReady, domBuilt]).then(() => {
    document.head.appendChild(style);
    media.subscribe();
    model.onUpdate(load);
    model.subscribe();
    load();
    // Two frames, so the panel is laid out before its size is read.
    requestAnimationFrame(() => requestAnimationFrame(() => {
        fit();
        setInterval(fit, 100);
    }));
});
