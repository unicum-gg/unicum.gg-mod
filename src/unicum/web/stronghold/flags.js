// Flags for every clan tag on the page.
//
// Part of the Stronghold content script, see core.js.
//
// Two placements, because the page has two kinds of place to put them.
//
// In the detachment list, at the FAR END of the clan's own column, pushed
// there by the layout rather than by a measurement. Between the tag and the
// name is where they were, and there they spent the width the clan's name
// needed: "[SURI4] <flags> [ Les suricates ]" against "[SURI4] [ Les
// suricates ] ............ <flags>".
//
// Anywhere else, beside the tag as before. Nowhere else is a column, so
// there is no far end to push them to.
//
// Takes out every flag box that is not where it belongs any more. React
// reuses a row for another clan by changing only its text, which would
// otherwise leave a flag next to the wrong tag and add another one on every
// render.
function prune() {
    var boxes = document.querySelectorAll('[' + FLAG_ATTR + ']');
    for (var i = 0; i < boxes.length; i++) {
        if (!belongs(boxes[i])) {
            boxes[i].parentNode.removeChild(boxes[i]);
        }
    }
}

// Whether a box is still standing for the tag it was made for: in a column,
// that the column still shows it; beside a tag, that the tag is still the
// one in front of it.
function belongs(box) {
    var tag = box.getAttribute(FLAG_ATTR);
    if (isCell(box.parentNode)) {
        return cellTag(box.parentNode) === tag;
    }
    var prev = box.previousSibling;
    return !!(prev && prev.nodeType === 1 && prev.tagName === 'SPAN' &&
              tagOf(prev) === tag);
}

// A cell of the detachment list, which is the only place with a far end.
function isCell(el) {
    return !!(el && el.getAttribute &&
              String(el.getAttribute('class') || '').indexOf('UnitsList_td') >= 0);
}

function cellOf(el) {
    for (var up = 0; up < 5 && el; up++) {
        if (isCell(el)) {
            return el;
        }
        el = el.parentNode;
    }
    return null;
}

// The clan tag a cell shows, or null.
function cellTag(cell) {
    var spans = cell.getElementsByTagName('span');
    for (var i = 0; i < spans.length; i++) {
        var tag = tagOf(spans[i]);
        if (tag) {
            return tag;
        }
    }
    return null;
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

// One box at the end of a column, and only one.
//
// Moved back to the end rather than added to when it is not last any more:
// React puts its own nodes back after ours, and a second box would pass
// `belongs` as happily as the first, so the row would collect one per
// render. The move is skipped when it is already last, because appending a
// node that is already there is still a change to the tree, and this script
// runs on changes to the tree.
function atColumnEnd(cell, tag) {
    var box = cell.querySelector('[' + FLAG_ATTR + ']');
    if (box && box.getAttribute(FLAG_ATTR) !== tag) {
        cell.removeChild(box);
        box = null;
    }
    if (!box) {
        cell.appendChild(makeBox(tag));
    } else if (cell.lastChild !== box) {
        cell.appendChild(box);
    }
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
        var cell = cellOf(el);
        if (cell) {
            atColumnEnd(cell, tag);
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
    squad();
}
