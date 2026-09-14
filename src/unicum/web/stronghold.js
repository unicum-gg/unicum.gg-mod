// Content script for the Stronghold pages of the embedded browser.
//
// Injected by src/unicum/browser.py, which wraps this file in
//   (function(GENERATION){ <this file> })(<n>);
// and runs that as javascript:eval(atob('<base64>')). So it may use any
// syntax and comments, and `return` at the top level, but must stay ASCII
// (atob decodes to Latin-1). It is read again at every injection: reopening
// the Stronghold window picks up an edit without a client restart.
//
// Talks back through console.log, which the client forwards to Python:
//   [unicum] need TAG1,TAG2   tags this page has no answer for yet
// Python answers by calling window.__unicum.set({TAG: clan}), where clan is
//   {flags: [dataUri, ...], wnx: {value: 1792, color: '#6D9521'} or null}
//
// GENERATION is the mod's session generation. A reload injects the new
// version, which finds the old one by its older generation and stops it
// first, so the page never runs two observers or holds two sets of flags.

var NEED_PREFIX = '[unicum] need ';
var FLAG_ATTR = 'data-unicum-flag';     // a flag box, valued with its tag
var STYLE_ATTR = 'data-unicum-style';   // our stylesheet
var LABEL_ATTR = 'data-unicum-label';   // a relabelled header, valued with its text
var HIDE_ATTR = 'data-unicum-hide';     // a site cell we hide
var COL_ATTR = 'data-unicum-col';       // a cell we added, valued with its column
var ADDED_ATTR = 'data-unicum-added';   // any node we added inside the site's table
var SORT_ATTR = 'data-unicum-sort';     // a header we made sortable

var current = window.__unicum;
if (current && current.v === GENERATION) {
    current.scan();
    return;
}
if (current && current.stop) {
    current.stop();
}

var alive = true;  // false once stopped; listeners left on page nodes check it
var clans = {};    // tag -> {flags, wnx}
var asked = {};    // tags already reported, so each is asked for once
var timer = null;

// The clan tag inside a leaf span, "[TAG]" -> "TAG", or null.
function tagOf(el) {
    if (el.children.length > 0) {
        return null;
    }
    var text = (el.textContent || '').trim();
    if (text.length < 4 || text.length > 8) {
        return null;
    }
    if (text.charAt(0) !== '[' || text.charAt(text.length - 1) !== ']') {
        return null;
    }
    return text.substring(1, text.length - 1);
}

// ---------------------------------------------------------------------------
// The detachment list table
//
// Flex rows of five cells: name, rating, server, members, places. Rating is
// not sortable on the site; server and places are, members is not.
//
//   - "Places" only restates "Members" (7 places minus 2/7 members). The
//     sortable places header is kept, with its native sort arrow, and
//     relabelled with the members header's own text; the members header and
//     the places cells are hidden. Sorting by free places is sorting by
//     members, with the arrow reversed.
//   - A WNx column, the clan's recent WNx painted with the site's scale, goes
//     after rating.
//   - Rating and WNx are made sortable, see "Sorting" below.
//
// The site's own cells are told apart from ours by ADDED_ATTR and addressed
// by position among themselves, never by their English titles, so this holds
// in any client language and wherever our cells sit.
//
// Widths: the site sizes cells as flex shares (name 4, capped at 180px; the
// rest 1) from a zero basis, and header and body cells carry different
// padding (10/0 against 10/10). That only lines up with the site's own five
// cells. So every number column gets the same fixed border-box width in both
// rows, and the name column takes the rest.

var NUMBER_COLUMN_WIDTH = '70px';
var WNX_TITLE = 'WNx';

var TABLE_CSS = [
    '[' + HIDE_ATTR + '] { display: none !important; }',
    '[class*="UnitsList_tr--"] > :nth-child(n+2) {' +
        ' flex: 0 0 ' + NUMBER_COLUMN_WIDTH + ' !important;' +
        ' box-sizing: border-box !important; max-width: none !important; }',
    '[class*="UnitsList_tr--"] > :first-child {' +
        ' flex: 1 1 0 !important; min-width: 0 !important; max-width: none !important; }',
    // The site's sort arrow on its own header, while one of our sorts leads.
    '.unicum-unsorted::after { visibility: hidden !important; }'
].join('\n');

function siteCells(row) {
    var out = [];
    for (var i = 0; i < row.children.length; i++) {
        if (!row.children[i].hasAttribute(ADDED_ATTR)) {
            out.push(row.children[i]);
        }
    }
    return out;
}

function headRow() {
    var head = document.querySelector('[class*="UnitsList_tr__thead"]');
    return head && siteCells(head).length === 5 ? head : null;
}

function bodyRows() {
    var body = document.querySelector('[class*="UnitsList_tbody"]');
    return body ? Array.prototype.slice.call(body.children) : [];
}

function setText(el, text) {
    if (el.textContent !== text) {
        el.textContent = text;
    }
}

function table() {
    if (!document.querySelector('style[' + STYLE_ATTR + ']')) {
        var style = document.createElement('style');
        style.setAttribute(STYLE_ATTR, '1');
        style.textContent = TABLE_CSS;
        (document.head || document.body).appendChild(style);
    }
    var head = headRow();
    if (!head) {
        return;
    }
    var cells = siteCells(head);

    // Members folded into places.
    cells[3].setAttribute(HIDE_ATTR, '1');
    var from = cells[3].querySelector('span');
    var to = cells[4].querySelector('span');
    if (from && to && to.textContent !== from.textContent) {
        if (!to.hasAttribute(LABEL_ATTR)) {
            to.setAttribute(LABEL_ATTR, to.textContent);
        }
        to.textContent = from.textContent;
    }

    // The WNx header, built from the rating header so it looks the same.
    var wnxHead = head.querySelector('[' + COL_ATTR + '="wnx"]');
    if (!wnxHead) {
        wnxHead = cells[1].cloneNode(false);
        wnxHead.removeAttribute('data-tip');
        wnxHead.removeAttribute('data-for');
        wnxHead.removeAttribute(SORT_ATTR);
        wnxHead.setAttribute(ADDED_ATTR, '1');
        wnxHead.setAttribute(COL_ATTR, 'wnx');
        var title = cells[2].querySelector('[class*="UnitsList_thTitle"]').cloneNode(false);
        var label = document.createElement('span');
        label.textContent = WNX_TITLE;
        title.appendChild(label);
        wnxHead.appendChild(title);
    }
    if (wnxHead.nextSibling !== cells[2]) {
        head.insertBefore(wnxHead, cells[2]);
    }

    var rows = bodyRows();
    for (var r = 0; r < rows.length; r++) {
        var row = rows[r];
        var rowCells = siteCells(row);
        if (rowCells.length !== 5) {
            continue;
        }
        rowCells[4].setAttribute(HIDE_ATTR, '1');
        var cell = row.querySelector('[' + COL_ATTR + '="wnx"]');
        if (!cell) {
            cell = rowCells[1].cloneNode(false);
            cell.setAttribute(ADDED_ATTR, '1');
            cell.setAttribute(COL_ATTR, 'wnx');
            cell.appendChild(document.createElement('span'));
        }
        if (cell.nextSibling !== rowCells[2]) {
            row.insertBefore(cell, rowCells[2]);
        }
        fillWnx(cell, rowTag(rowCells[0]));
    }
    sorting(head);
}

function rowTag(nameCell) {
    var spans = nameCell.getElementsByTagName('span');
    for (var i = 0; i < spans.length; i++) {
        var tag = tagOf(spans[i]);
        if (tag) {
            return tag;
        }
    }
    return null;
}

function fillWnx(cell, tag) {
    var wnx = tag && clans[tag] ? clans[tag].wnx : null;
    var span = cell.firstChild;
    setText(span, wnx ? String(Math.round(wnx.value)) : '-');
    var color = wnx && wnx.color ? wnx.color : '';
    if (span.style.color !== color) {
        span.style.color = color;
    }
    cell.setAttribute('data-value', wnx ? String(wnx.value) : '-1');
}

// ---------------------------------------------------------------------------
// Sorting
//
// The site sorts by server and places but not by rating, and knows nothing of
// WNx. Both headers are made to look and act sortable: a click sorts by that
// column, descending first, then flips. Rows are not moved in the DOM -- React
// owns them, and moving its nodes would desynchronise its next render. The
// rows container becomes a flex column and each row gets a CSS `order`
// instead, recomputed on every scan, so rows the site adds or updates fall in
// place.
//
// The site's own sort keeps running underneath. Clicking one of its sortable
// headers hands control back to it.
//
// The sorted look (title glow, arrow) comes from the site's own modifier
// classes, UnitsList_th__desc--<hash> and __asc--<hash>. The hash changes with
// every site build, so the names are read from its stylesheets.

var sortKey = null;       // null, 'rating' or 'wnx'
var sortOrder = 'desc';
var sortClasses = null;   // {desc, asc, sortable}

var SORT_VALUES = {
    rating: function (row) {
        var value = parseInt(siteCells(row)[1].textContent.replace(/\D/g, ''), 10);
        return isNaN(value) ? -1 : value;
    },
    wnx: function (row) {
        var cell = row.querySelector('[' + COL_ATTR + '="wnx"]');
        return cell ? parseFloat(cell.getAttribute('data-value')) : -1;
    }
};

function findSortClasses() {
    var found = {};
    for (var s = 0; s < document.styleSheets.length; s++) {
        var rules;
        try {
            rules = document.styleSheets[s].cssRules;
        } catch (e) {
            continue;   // another origin's stylesheet
        }
        for (var r = 0; rules && r < rules.length; r++) {
            var text = rules[r].selectorText || '';
            var match = text.match(/UnitsList_th__(desc|asc|sortable)--[\w-]+/g);
            for (var m = 0; match && m < match.length; m++) {
                found[match[m].split('__')[1].split('--')[0]] = match[m];
            }
        }
    }
    return found.desc && found.asc && found.sortable ? found : null;
}

function sorting(head) {
    if (!sortClasses) {
        sortClasses = findSortClasses();
        if (!sortClasses) {
            return;
        }
    }
    var cells = siteCells(head);
    var ours = {rating: cells[1], wnx: head.querySelector('[' + COL_ATTR + '="wnx"]')};
    for (var key in ours) {
        var header = ours[key];
        if (!header) {
            continue;
        }
        if (!header.hasAttribute(SORT_ATTR)) {
            makeSortable(header, key, cells[2]);
        }
        header.classList.add(sortClasses.sortable);
        header.classList.toggle(sortClasses.desc, sortKey === key && sortOrder === 'desc');
        header.classList.toggle(sortClasses.asc, sortKey === key && sortOrder === 'asc');
    }
    if (!head.hasAttribute(SORT_ATTR)) {
        head.setAttribute(SORT_ATTR, '1');
        // Any other header click is the site's sort taking over again.
        head.addEventListener('click', function (event) {
            if (alive && !event.target.closest('[' + SORT_ATTR + '="column"]')) {
                sortKey = null;
                setTimeout(scan, 0);
            }
        }, true);
    }
    // While one of ours leads, the site's sorted header must not look sorted.
    for (var h = 2; h < cells.length; h++) {
        var title = cells[h].querySelector('[class*="UnitsList_thTitle"]');
        if (title) {
            title.style.cssText = sortKey ? 'color:inherit;text-shadow:none' : '';
            title.classList.toggle('unicum-unsorted', !!sortKey);
        }
    }
    orderRows();
}

function makeSortable(header, key, template) {
    header.setAttribute(SORT_ATTR, 'column');
    // The hover and active underlines, copied from a sortable header.
    var conditions = template.querySelectorAll('[class*="UnitsList_thCondition"]');
    for (var i = 0; i < conditions.length; i++) {
        var copy = conditions[i].cloneNode(false);
        copy.setAttribute(ADDED_ATTR, '1');
        header.appendChild(copy);
    }
    header.addEventListener('click', function () {
        if (!alive) {
            return;
        }
        sortOrder = sortKey === key && sortOrder === 'desc' ? 'asc' : 'desc';
        sortKey = key;
        scan();
    });
}

function orderRows() {
    var body = document.querySelector('[class*="UnitsList_tbody"]');
    if (!body) {
        return;
    }
    var rows = bodyRows();
    if (!sortKey) {
        if (body.hasAttribute(SORT_ATTR)) {
            body.removeAttribute(SORT_ATTR);
            body.style.display = '';
            body.style.flexDirection = '';
            for (var c = 0; c < rows.length; c++) {
                rows[c].style.order = '';
            }
        }
        return;
    }
    body.setAttribute(SORT_ATTR, sortKey);
    body.style.display = 'flex';
    body.style.flexDirection = 'column';
    var entries = [];
    for (var i = 0; i < rows.length; i++) {
        entries.push({row: rows[i], value: SORT_VALUES[sortKey](rows[i]), index: i});
    }
    entries.sort(function (a, b) {
        var diff = sortOrder === 'desc' ? b.value - a.value : a.value - b.value;
        return diff || a.index - b.index;
    });
    for (var k = 0; k < entries.length; k++) {
        var order = String(k);
        if (entries[k].row.style.order !== order) {
            entries[k].row.style.order = order;
        }
    }
}

// ---------------------------------------------------------------------------
// Flags

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

// ---------------------------------------------------------------------------
// Lifecycle

// The app is React: rows are re-rendered and anything added is gone at the
// next render, so every DOM change schedules a rescan. Scans only write what
// differs, so a scan that changes nothing causes no mutation, and this settles.
var observer = new MutationObserver(function () {
    if (timer) {
        return;
    }
    timer = setTimeout(function () {
        timer = null;
        scan();
    }, 150);
});
observer.observe(document.body, {childList: true, subtree: true, characterData: true});

function stop() {
    alive = false;
    observer.disconnect();
    if (timer) {
        clearTimeout(timer);
    }
    sortKey = null;
    orderRows();
    var added = document.querySelectorAll(
        '[' + FLAG_ATTR + '], [' + ADDED_ATTR + '], style[' + STYLE_ATTR + ']');
    for (var i = 0; i < added.length; i++) {
        added[i].parentNode.removeChild(added[i]);
    }
    var hidden = document.querySelectorAll('[' + HIDE_ATTR + ']');
    for (var h = 0; h < hidden.length; h++) {
        hidden[h].removeAttribute(HIDE_ATTR);
    }
    var labels = document.querySelectorAll('[' + LABEL_ATTR + ']');
    for (var j = 0; j < labels.length; j++) {
        labels[j].textContent = labels[j].getAttribute(LABEL_ATTR);
        labels[j].removeAttribute(LABEL_ATTR);
    }
    var sortable = document.querySelectorAll('[' + SORT_ATTR + ']');
    for (var s = 0; s < sortable.length; s++) {
        if (sortClasses) {
            sortable[s].classList.remove(sortClasses.sortable, sortClasses.desc, sortClasses.asc);
        }
        sortable[s].removeAttribute(SORT_ATTR);
    }
    var titles = document.querySelectorAll('.unicum-unsorted');
    for (var t = 0; t < titles.length; t++) {
        titles[t].style.cssText = '';
        titles[t].classList.remove('unicum-unsorted');
    }
    window.__unicum = null;
}

window.__unicum = {
    v: GENERATION,
    scan: scan,
    set: function (answers) {
        for (var tag in answers) {
            clans[tag] = answers[tag];
        }
        scan();
    },
    stop: stop
};

scan();
