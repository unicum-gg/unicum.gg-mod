// Loader for the unicum.gg button in the hangar's vehicle menu.
//
// Injected into the hangar by openwg_gameface (src/unicum/tank_button.py). It
// holds no feature of its own, so it never needs to change: the button and its
// menu are src/unicum/web/hangar/tank_menu.js and .css, which Python reads
// and puts in the view model (`script`, `style`), again whenever they change
// on disk. Each new `revision` stops the running code and runs the new one,
// which is what lets the menu be edited while the client runs. A file here
// is read by the client once, at startup.
//
// The code runs as new Function("api", script)(api), and returns
// { stop() } to undo everything it added. `api.report(text)` reaches the
// game log through the model's onItemClick command.
import { MediaContext } from "../../libs/media.js";
import { ModelObserver } from "../../libs/model.js";
import { playSound } from "../../libs/sound.js";

const media = MediaContext();
const model = ModelObserver("UnicumTankButton");
const style = document.createElement("style");

let running = null;
let loaded = null;

function report(text) {
    if (model.model) {
        model.model.onItemClick({ item: "log", text: String(text).slice(0, 4000) });
    }
}

function load() {
    const current = model.model;
    if (!current || !current.script || current.revision === loaded) {
        return;
    }
    loaded = current.revision;
    if (running) {
        try {
            running.stop();
        } catch (error) {
            report(`tank menu: stop failed: ${error}`);
        }
        running = null;
    }
    style.textContent = current.style || "";
    try {
        running = new Function("api", current.script)({ model, media, playSound, report });
    } catch (error) {
        report(`tank menu: script failed: ${error} ${error && error.stack ? error.stack : ""}`);
    }
}

engine.whenReady.then(() => {
    document.head.appendChild(style);
    media.subscribe();
    model.onUpdate(load);
    model.subscribe();
    load();
});
