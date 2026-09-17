// Ratings and language flags of the players in the post-battle results.
//
// Run by the loader (res/gui/gameface/mods/unicum/TankButton/TankButton.js),
// added to the results view by src/unicum/battle_results.py, as the body of a
// function of `api` = { model, media, playSound, report }; returns { stop() }.
// The players come as JSON in the model's `data`, keyed by the name the page
// shows, and none are drawn while `hidden` (waiting for Alt):
// { hidden, players: { name: { score: { value, color } | null, flags: [image url] } } }.
//
// As on the battle's Tab screen, they sit outside each team's table, in two
// columns lined up down the team: left of the allies' rows, right of the
// enemies', the badge nearest the row and the flags beyond it. So nothing of
// the table moves and no name is cut shorter.
//
// React owns the rows and moves them as the player sorts or switches tab, so
// the names are looked for on a timer, and the markers, in a layer of their
// own over the page, follow their rows there. Gameface: images are sized divs
// with a background.

const { model, report } = api;

// The account cell's name, in the team tables: a class with a hash the
// client's next build may change.
const NAME = '[class*="AccountInfoCell_accountName_"]';
const BOX = "UnicumResults";
const POLL_MS = 150;
// Between the row's edge and the badge column, and between the two columns.
const GAP = 10;
const SPACE = 6;
// A row is the widest ancestor of the name still about as tall as a row.
const ROW_HEIGHT_RATIO = 3;

const state = { alive: true, json: null, players: {}, markers: {} };

// Pixels to the rem the view lays out in; 1 when the view does not say.
const toRem = (px) => (typeof viewEnv !== "undefined" && viewEnv.pxToRem ? viewEnv.pxToRem(px) : px);

const layer = document.createElement("div");
layer.className = `${BOX}_layer`;
document.body.appendChild(layer);

function group(value) {
    const digits = String(value);
    let out = "";
    for (let i = 0; i < digits.length; i++) {
        if (i > 0 && (digits.length - i) % 3 === 0) {
            out += " ";
        }
        out += digits[i];
    }
    return out;
}

// { key, badge, flags } for a player: the elements, remade when what they show changes.
function markerFor(text, player) {
    const key = JSON.stringify(player);
    const current = state.markers[text];
    if (current && current.key === key) {
        return current;
    }
    if (current) {
        removeMarker(current);
    }
    const marker = { key, badge: null, flags: null };
    if (player.score) {
        marker.badge = document.createElement("div");
        marker.badge.className = `${BOX}_badge`;
        marker.badge.style.backgroundColor = player.score.color;
        marker.badge.textContent = group(player.score.value);
        layer.appendChild(marker.badge);
    }
    if (player.flags && player.flags.length) {
        marker.flags = document.createElement("div");
        marker.flags.className = `${BOX}_flags`;
        for (const url of player.flags) {
            const flag = document.createElement("div");
            flag.className = `${BOX}_flag`;
            flag.style.backgroundImage = `url(${url})`;
            marker.flags.appendChild(flag);
        }
        layer.appendChild(marker.flags);
    }
    state.markers[text] = marker;
    return marker;
}

function removeMarker(marker) {
    for (const element of [marker.badge, marker.flags]) {
        if (element && element.parentElement) {
            element.parentElement.removeChild(element);
        }
    }
}

// Whether an element is on show: the page keeps other copies of the names
// laid out but transparent or hidden, elsewhere on the screen.
function shown(element) {
    for (let node = element; node && node !== document.body; node = node.parentElement) {
        const style = getComputedStyle(node);
        if (style.opacity === "0" || style.visibility === "hidden" || style.display === "none") {
            return false;
        }
    }
    return true;
}

function rowOf(name) {
    const own = name.getBoundingClientRect();
    let row = own;
    for (let node = name.parentElement; node && node !== document.body; node = node.parentElement) {
        const rect = node.getBoundingClientRect();
        if (rect.height > own.height * ROW_HEIGHT_RATIO) {
            break;
        }
        if (rect.width > row.width) {
            row = rect;
        }
    }
    return { left: row.left, right: row.right, middle: own.top + own.height / 2 };
}

function place(element, leftPx, middlePx) {
    element.style.left = `${Math.round(toRem(leftPx))}rem`;
    element.style.top = `${Math.round(toRem(middlePx - element.offsetHeight / 2))}rem`;
}

function decorate() {
    const sides = { left: [], right: [] };
    const seen = {};
    const names = document.querySelectorAll(NAME);
    for (let i = 0; i < names.length; i++) {
        const name = names[i];
        const text = (name.textContent || "").trim();
        const player = state.players[text];
        const rect = name.getBoundingClientRect();
        if (!player || seen[text] || rect.width === 0 || rect.height === 0 || !shown(name)) {
            continue;
        }
        seen[text] = true;
        const row = rowOf(name);
        const marker = markerFor(text, player);
        const side = rect.left + rect.width / 2 < window.innerWidth / 2 ? "left" : "right";
        sides[side].push({ marker, row });
    }
    for (const text of Object.keys(state.markers)) {
        if (!seen[text]) {
            removeMarker(state.markers[text]);
            delete state.markers[text];
        }
    }
    for (const side of ["left", "right"]) {
        const rows = sides[side];
        // One badge column for the team, as wide as its widest badge.
        let badges = 0;
        for (const item of rows) {
            if (item.marker.badge) {
                badges = Math.max(badges, item.marker.badge.offsetWidth);
            }
        }
        for (const item of rows) {
            const { marker, row } = item;
            if (side === "left") {
                const edge = row.left - GAP;
                if (marker.badge) {
                    place(marker.badge, edge - marker.badge.offsetWidth, row.middle);
                }
                if (marker.flags) {
                    place(marker.flags, edge - (badges ? badges + SPACE : 0) - marker.flags.offsetWidth, row.middle);
                }
            } else {
                const edge = row.right + GAP;
                if (marker.badge) {
                    place(marker.badge, edge, row.middle);
                }
                if (marker.flags) {
                    place(marker.flags, edge + (badges ? badges + SPACE : 0), row.middle);
                }
            }
        }
    }
}

function removeAll() {
    for (const text of Object.keys(state.markers)) {
        removeMarker(state.markers[text]);
    }
    state.markers = {};
}

function poll() {
    if (!state.alive) {
        return;
    }
    const current = model.model;
    const json = current && current.data;
    if (json && json !== state.json) {
        state.json = json;
        try {
            const data = JSON.parse(json) || {};
            state.players = data.hidden ? {} : data.players || {};
        } catch (error) {
            report(`battle results: bad data: ${error}`);
            state.players = {};
        }
    }
    try {
        decorate();
    } catch (error) {
        report(`battle results: decorate failed: ${error}`);
    }
}

const timer = setInterval(poll, POLL_MS);
poll();

return {
    stop() {
        state.alive = false;
        clearInterval(timer);
        removeAll();
        if (layer.parentElement) {
            layer.parentElement.removeChild(layer);
        }
    },
};
