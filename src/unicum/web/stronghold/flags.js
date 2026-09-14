// Flags after every clan tag on the page.
//
// Part of the Stronghold content script, see core.js.
//
// Takes out every flag box that is not directly after the tag it was made
// for. React reuses a row for another clan by changing only its text, which
// would otherwise leave a flag next to the wrong tag, and add another one on
// every render.
function prune() {
    var boxes = document.querySelectorAll('[' + FLAG_ATTR + ']');
    for (var i = 0; i < boxes.length; i++) {
        var box = boxes[i];
        var prev = box.previousSibling;
        if (prev && prev.nodeType === 1 && prev.tagName === 'SPAN' &&
                tagOf(prev) === box.getAttribute(FLAG_ATTR)) {
            continue;
        }
        box.parentNode.removeChild(box);
    }
}

function makeBox(tag) {
    var box = document.createElement('span');
    box.setAttribute(FLAG_ATTR, tag);
    // inline-flex centres the flags on the tag's line box, whatever the
    // font size of the row, rather than on the text baseline.
    box.style.cssText = 'display:inline-flex;align-items:center;vertical-align:middle;' +
                        'white-space:nowrap;height:1em';
    var uris = clans[tag].flags;
    for (var i = 0; i < uris.length; i++) {
        var img = document.createElement('img');
        img.src = uris[i];
        img.style.cssText = 'display:block;width:16px;height:12px;margin-left:4px';
        box.appendChild(img);
    }
    return box;
}

function flags() {
    prune();
    var spans = document.getElementsByTagName('span');
    var need = [];
    for (var i = 0; i < spans.length; i++) {
        var el = spans[i];
        var tag = tagOf(el);
        if (!tag) {
            continue;
        }
        if (!(tag in clans)) {
            if (!asked[tag]) {
                asked[tag] = 1;
                need.push(tag);
            }
            continue;
        }
        if (!clans[tag].flags.length) {
            continue;
        }
        var next = el.nextSibling;
        if (next && next.nodeType === 1 && next.getAttribute(FLAG_ATTR) === tag) {
            continue;
        }
        el.parentNode.insertBefore(makeBox(tag), next);
    }
    if (need.length) {
        console.log(NEED_PREFIX + need.join(','));
    }
}

function scan() {
    flags();
    table();
}
