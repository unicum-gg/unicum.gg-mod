// The unicum.gg button in the hangar's vehicle menu, and its menu of links
// for the selected tank.
//
// Run by the loader (res/gui/gameface/mods/unicum/TankButton/TankButton.js) as
// the body of a function of `api` = { model, media, playSound, report }, and
// run again whenever this file changes: it returns { stop() }, which takes
// back everything it added. Picking an entry calls the model's onItemClick
// with the entry's id; Python (src/unicum/tank_button.py) knows the tank and
// its setup, builds the link and opens it in the player's browser.
//
// Button and menu are built from the game's own markup and classes, so the
// game's stylesheet draws them: a MenuButton, and a MenuList of MenuItems as
// the vehicle button opens (captured from the 2.4 hangar). The class names
// carry a build hash, so each is read from the page when the game has one on
// screen, and the 2.4 name is used until then.
//
// ICONS is replaced by Python with data URIs of web/hangar/icons/*.png.

const { model, media, playSound, report } = api;
const ICONS = __MENU_ICONS__;

const WIDGET_SELECTOR = 'div[class^="VehicleMenu_menu_"] div[class^="VehicleMenuWidget_"]';

// Class name -> its hashed name in the 2.4 hangar.
const CLASSES = {
    MenuButton: "MenuButton_3f57027c",
    MenuButton_base__opened: "MenuButton_base__opened_d9d84dd",
    MenuButton_background: "MenuButton_background_80afe673",
    MenuButton_background__hidden: "MenuButton_background__hidden_a0ead688",
    MenuButton_icon: "MenuButton_icon_e994a077",
    VehicleMenuWidget_menu: "VehicleMenuWidget_menu_54752133",
    VehicleMenuWidget_menu__vehicle: "VehicleMenuWidget_menu__vehicle_6691c8cb",
    MenuList: "MenuList_cea03bfd",
    MenuList_content: "MenuList_content_102c53c8",
    MenuList_border: "MenuList_border_478c22c4",
    MenuList_bottom: "MenuList_bottom_c28a1943",
    MenuList_bottomBorder: "MenuList_bottomBorder_bad1a96",
    MenuList_notch: "MenuList_notch_265b362a",
    MenuItem: "MenuItem_37b3ba75",
    MenuItem_inner: "MenuItem_inner_7b3a0c1",
    MenuItem_hover: "MenuItem_hover_344959e8",
    MenuItem_sideBorders: "MenuItem_sideBorders_52632696",
    MenuItem_sideBorder: "MenuItem_sideBorder_7c07d72d",
    MenuItem_sideBorder__left: "MenuItem_sideBorder__left_3188559f",
    MenuItem_sideBorder__right: "MenuItem_sideBorder__right_b63d0a05",
    MenuItem_icon: "MenuItem_icon_cfe743f0",
    MenuItem_iconImage: "MenuItem_iconImage_5c399bab",
    MenuItem_title: "MenuItem_title_4f50bf02",
    FormatText: "FormatText_db904f12",
};

// Only from inside the vehicle menu: the hangar has other components with the
// same short names (another MenuItem, another FormatText), and taking theirs
// drew the menu at twice the size.
function isOurs(element) {
    for (let node = element; node; node = node.parentElement) {
        if (node.classList && (node.classList.contains("UnicumTankMenu") || node.classList.contains("UnicumTankButton"))) {
            return true;
        }
    }
    return false;
}

function learnClasses() {
    const widget = document.querySelector(WIDGET_SELECTOR);
    if (!widget) {
        return;
    }
    for (const element of widget.querySelectorAll("div, span")) {
        if (isOurs(element)) {
            continue;
        }
        for (const name of element.classList) {
            const match = /^(.+)_([0-9a-f]{6,8})$/.exec(name);
            if (match && CLASSES[match[1]] && CLASSES[match[1]] !== name) {
                CLASSES[match[1]] = name;
            }
        }
    }
}

const c = (...names) => names.map((name) => CLASSES[name]).join(" ");

const GAME_ICON = (name) => `img://gui/maps/icons/hangar/vehicleMenu/large/${name}.png`;

// Groups of [id, label, icon]; ids are what tank_button.py understands.
const MENU = [
    [
        ["specifications", "Specifications", GAME_ICON("aboutVehicle")],
        ["performances", "Performances", GAME_ICON("compare")],
        ["marks", "Marks", GAME_ICON("achievements")],
        ["history", "History", ICONS.history],
        ["videos", "Videos", ICONS.videos],
        ["community", "Community", ICONS.community],
    ],
    [
        ["chatgpt", "Open in ChatGPT", ICONS.chatgpt],
        ["claude", "Open in Claude", ICONS.claude],
        ["scira", "Open in Scira AI", ICONS.scira],
    ],
    [
        ["build", "Open build", GAME_ICON("easyEquip")],
    ],
];

const state = {
    alive: true,
    // Where the game draws its menu against its button, right edge to right
    // edge, measured whenever one is open. Until then, what the 2.4 hangar does.
    rightOverhang: 12,
    hovered: false,
    size: "small",
    menu: null,
};

function image(className, url) {
    const element = document.createElement("div");
    element.className = className;
    element.style.backgroundImage = `url(${url})`;
    element.style.backgroundRepeat = "no-repeat";
    element.style.backgroundSize = "contain";
    element.style.backgroundPositionX = "50%";
    element.style.backgroundPositionY = "50%";
    return element;
}

function paint(button) {
    const opened = !!state.menu;
    const [normal, open, hover] = button.querySelectorAll(`.${CLASSES.MenuButton_background}`);
    const base = `img://gui/maps/icons/hangar/vehicleMenu/${state.size}/btn_enabled`;
    normal.style.backgroundImage = `url(${base}.png)`;
    open.style.backgroundImage = `url(${base}_opened.png)`;
    hover.style.backgroundImage = `url(${base}_hover.png)`;
    normal.classList.toggle(CLASSES.MenuButton_background__hidden, opened || state.hovered);
    open.classList.toggle(CLASSES.MenuButton_background__hidden, !opened);
    hover.classList.toggle(CLASSES.MenuButton_background__hidden, opened || !state.hovered);
    button.classList.toggle(CLASSES.MenuButton_base__opened, opened);
    const icon = button.querySelector(`.${CLASSES.MenuButton_icon}`);
    icon.style.backgroundImage = `url(img://gui/maps/icons/unicum/tankButton/${state.size}.png)`;
    // Our image fills its square where the game's leave a margin around the glyph.
    icon.style.backgroundSize = "62%";
    const enabled = !model.model || model.model.enabled !== false;
    button.style.display = enabled ? "" : "none";
    if (!enabled) {
        closeMenu();
    }
}

function paintAll() {
    state.size = media.scale > 1 ? "upscale" : media.width > 1366 ? "large" : "small";
    document.querySelectorAll(".UnicumTankButton").forEach((button) => {
        space(button);
        paint(button);
    });
}

// The gap the game leaves between two of its own buttons, on our right: the
// buttons' class does not carry it, so ours sat against the next one.
function space(button) {
    const buttons = Array.from(button.parentElement.children).filter(
        (child) => child !== button && child.classList.contains(CLASSES.MenuButton) && child.offsetWidth);
    for (let i = 1; i < buttons.length; i++) {
        const gap = buttons[i].offsetLeft - (buttons[i - 1].offsetLeft + buttons[i - 1].offsetWidth);
        if (gap > 0) {
            button.style.marginRight = `${gap}px`;
            return;
        }
    }
}

function closeMenu() {
    if (state.menu) {
        state.menu.remove();
        state.menu = null;
        document.querySelectorAll(".UnicumTankButton").forEach(paint);
    }
}

function menuItem([id, label, icon]) {
    const item = document.createElement("div");
    item.className = c("MenuItem");
    const inner = document.createElement("div");
    inner.className = c("MenuItem_inner");
    inner.dataset.testId = `unicum-${id}`;
    const hover = document.createElement("div");
    hover.className = c("MenuItem_hover");
    const borders = document.createElement("div");
    borders.className = c("MenuItem_sideBorders");
    for (const side of ["MenuItem_sideBorder__left", "MenuItem_sideBorder__right"]) {
        const border = document.createElement("div");
        border.className = c("MenuItem_sideBorder", side);
        borders.appendChild(border);
    }
    const iconBox = document.createElement("div");
    iconBox.className = c("MenuItem_icon");
    iconBox.appendChild(image(c("MenuItem_iconImage"), icon));
    const title = document.createElement("div");
    title.className = c("MenuItem_title");
    const text = document.createElement("span");
    text.className = c("FormatText");
    text.textContent = label.toUpperCase();
    title.appendChild(text);
    inner.append(hover, borders, iconBox, title);
    item.appendChild(inner);
    inner.addEventListener("mouseenter", () => playSound("highlight"));
    inner.addEventListener("click", (event) => {
        event.stopPropagation();
        closeMenu();
        if (model.model) {
            model.model.onItemClick({ item: id });
            playSound("yes1");
        }
    });
    return item;
}

// The game's own menu, closed the way a player would: by pressing the button
// it is open on. Two menus open at once overlapped. React answers mouse
// events rather than a bare click(), so the whole press is sent; our own
// document listener is told to ignore it.
function closeGameMenu() {
    for (const other of gameButtons()) {
        if (!other.classList.contains(CLASSES.MenuButton_base__opened)) {
            continue;
        }
        state.pressing = true;
        try {
            for (const type of ["mousedown", "mouseup", "click"]) {
                other.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window, button: 0 }));
            }
        } catch (error) {
            report(`closing the game menu failed: ${error}`);
        } finally {
            state.pressing = false;
        }
    }
}

function gameButtons() {
    const widget = document.querySelector(WIDGET_SELECTOR);
    if (!widget) {
        return [];
    }
    return Array.from(widget.children).filter(
        (child) => child.classList.contains(CLASSES.MenuButton) && !child.classList.contains("UnicumTankButton"));
}

function openMenu(button) {
    learnClasses();
    closeGameMenu();
    const container = document.createElement("div");
    // With the vehicle button's modifier, which sizes the menu like that one.
    container.className = `${c("VehicleMenuWidget_menu", "VehicleMenuWidget_menu__vehicle")} UnicumTankMenu`;
    const list = document.createElement("div");
    list.className = c("MenuList");
    list.style.opacity = "1";
    const content = document.createElement("div");
    content.className = c("MenuList_content");
    MENU.forEach((group, index) => {
        if (index > 0) {
            // The game's own divider image, as its menus draw between groups.
            const divider = image("UnicumTankMenu_divider", "img://gui/maps/icons/hangar/vehicleMenu/menu_divider.png");
            divider.style.backgroundSize = "100% 100%";
            content.appendChild(divider);
        }
        group.forEach((entry) => content.appendChild(menuItem(entry)));
    });
    const border = document.createElement("div");
    border.className = c("MenuList_border");
    const bottom = document.createElement("div");
    bottom.className = c("MenuList_bottom");
    const notch = document.createElement("div");
    notch.className = c("MenuList_notch");
    bottom.append(
        image(c("MenuList_bottomBorder"), "img://gui/maps/icons/hangar/vehicleMenu/menu_bottom_left_default.png"),
        notch,
        image(c("MenuList_bottomBorder"), "img://gui/maps/icons/hangar/vehicleMenu/menu_bottom_right_default.png"));
    list.append(content, border, bottom);
    container.appendChild(list);
    // In the widget like the game's menu, then moved sideways so it sits
    // against our button the way theirs sits against its own.
    button.parentElement.insertBefore(container, button);
    container.style.left = `${button.offsetLeft + button.offsetWidth / 2}px`;
    const menuRect = container.getBoundingClientRect();
    const buttonRect = button.getBoundingClientRect();
    const shift = (buttonRect.right + state.rightOverhang) - menuRect.right;
    container.style.left = `${button.offsetLeft + button.offsetWidth / 2 + shift}px`;
    state.menu = container;
    paint(button);
}

function createButton() {
    learnClasses();
    const button = document.createElement("div");
    button.className = `${c("MenuButton")} UnicumTankButton`;
    button.dataset.testId = "unicum";
    for (let i = 0; i < 3; i++) {
        button.appendChild(image(c("MenuButton_background"), ""));
    }
    button.appendChild(image(c("MenuButton_icon"), ""));
    // Not stopped: the game closes its own menu on clicks outside it.
    button.addEventListener("click", (event) => {
        event.unicumOwnClick = true;
        if (state.menu) {
            closeMenu();
        } else {
            openMenu(button);
            playSound("yes1");
        }
    });
    button.addEventListener("mouseenter", () => {
        state.hovered = true;
        paint(button);
        playSound("highlight");
    });
    button.addEventListener("mouseleave", () => {
        state.hovered = false;
        paint(button);
    });
    return button;
}

function ensureButton() {
    const widget = document.querySelector(WIDGET_SELECTOR);
    if (!widget || widget.querySelector(".UnicumTankButton")) {
        return;
    }
    const button = createButton();
    const skill = widget.querySelector(".SkillButton");
    widget.insertBefore(button, skill ? skill.nextSibling : widget.firstChild);
    paintAll();
}

// Where the game draws its menu against the button it is open on, whenever
// one is on screen, so ours is placed the same way.
const measured = new WeakSet();

function learnPlacement() {
    const container = Array.from(document.querySelectorAll('[class*="VehicleMenuWidget_menu_"]')).find(
        (element) => !element.classList.contains("UnicumTankMenu") && element.querySelector('[class*="MenuItem_inner_"]'));
    if (container && !measured.has(container)) {
        measured.add(container);
        const opened = gameButtons().find((other) => other.classList.contains(CLASSES.MenuButton_base__opened));
        if (opened) {
            state.rightOverhang = container.getBoundingClientRect().right - opened.getBoundingClientRect().right;
        }
    }
}

const observer = new MutationObserver(() => {
    ensureButton();
    learnPlacement();
});
const onDocumentClick = (event) => {
    if (!event.unicumOwnClick && !state.pressing) {
        closeMenu();
    }
};
const onKeyDown = (event) => {
    if (event.keyCode === 27) {
        closeMenu();
    }
};

media.onUpdate(() => {
    if (state.alive) {
        closeMenu();
        paintAll();
    }
});
model.onUpdate(() => {
    if (state.alive) {
        paintAll();
    }
});
observer.observe(document.body, { childList: true, subtree: true });
document.addEventListener("click", onDocumentClick);
document.addEventListener("keydown", onKeyDown);
ensureButton();

return {
    stop() {
        state.alive = false;
        observer.disconnect();
        document.removeEventListener("click", onDocumentClick);
        document.removeEventListener("keydown", onKeyDown);
        closeMenu();
        document.querySelectorAll(".UnicumTankButton").forEach((button) => button.remove());
    },
};
