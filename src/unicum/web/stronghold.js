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
// Python answers by calling window.__unicum.set({TAG: [dataUri, ...]}).
//
// GENERATION is the mod's session generation. A reload injects the new
// version, which finds the old one by its older generation and stops it
// first, so the page never runs two observers or holds two sets of flags.

var NEED_PREFIX = '[unicum] need ';
var FLAG_ATTR = 'data-unicum-flag';
var STYLE_ATTR = 'data-unicum-style';
var LABEL_ATTR = 'data-unicum-label';

var current = window.__unicum;
if (current && current.v === GENERATION) {
    current.scan();
    return;
}
if (current && current.stop) {
    current.stop();
}

var alive = true;  // false once stopped; listeners left on page nodes check it
var flags = {};   // tag -> [data URI], an empty list meaning "no flag"
var asked = {};   // tags already reported, so each is asked for once
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
// Detachment list columns
//
// "Places" only restates "Members" (7 places minus 2/7 members). The table is
// flex rows of five cells: name, rating, server, members, places. Rating,
// server and places are sortable, members is not. So the sortable places
// header is kept, with its native sort arrow, and relabelled with the members
// header's own text; the members header and the places cells are hidden.
// Sorting by free places is sorting by members, with the arrow reversed.
//
// Cells are addressed by position rather than by their English titles, so this
// holds in any client language.
//
// The freed width has to be claimed, and the columns kept aligned. The site
// sizes cells as flex shares (name 4, capped at 180px; the rest 1) from a zero
// basis, and header and body cells carry different padding (10/0 against
// 10/10). That only lines up while the shares stay as the site set them;
// hiding one cell per row upset it. So the number columns get a fixed
// border-box width, identical in both rows, and the name column takes the
// rest.

var NUMBER_COLUMN_WIDTH = '80px';

var COLUMN_CSS = [
    '[class*="UnitsList_tr__thead"] > :nth-child(4) { display: none; }',
    '[class*="UnitsList_tr--"]:not([class*="UnitsList_tr__thead"]) > :nth-child(5) { display: none; }',
    '[class*="UnitsList_tr--"] > :nth-child(n+2) {' +
        ' flex: 0 0 ' + NUMBER_COLUMN_WIDTH + ' !important;' +
        ' box-sizing: border-box !important; max-width: none !important; }',
    '[class*="UnitsList_tr--"] > :first-child {' +
        ' flex: 1 1 0 !important; min-width: 0 !important; max-width: none !important; }',
    // The site's sort arrow on its own header, while rating sorting leads.
    '.unicum-unsorted::after { visibility: hidden !important; }'
].join('\n');

function columns() {
    if (!document.querySelector('style[' + STYLE_ATTR + ']')) {
        var style = document.createElement('style');
        style.setAttribute(STYLE_ATTR, '1');
        style.textContent = COLUMN_CSS;
        (document.head || document.body).appendChild(style);
    }
    var heads = document.querySelectorAll('[class*="UnitsList_tr__thead"]');
    for (var i = 0; i < heads.length; i++) {
        if (heads[i].children.length !== 5) {
            continue;
        }
        var from = heads[i].children[3].querySelector('span');
        var to = heads[i].children[4].querySelector('span');
        if (!from || !to || to.textContent === from.textContent) {
            continue;
        }
        if (!to.hasAttribute(LABEL_ATTR)) {
            to.setAttribute(LABEL_ATTR, to.textContent);
        }
        to.textContent = from.textContent;
    }
    ratingSort(heads);
}

// ---------------------------------------------------------------------------
// Sorting by rating
//
// The site sorts by server and places but not by rating. The rating header is
// made to look and act sortable: a click sorts by rating, descending first,
// then flips. Rows are not moved in the DOM -- React owns them, and moving its
// nodes would desynchronise its next render. The rows container becomes a
// flex column and each row gets a CSS `order` from its rating instead, which
// is recomputed on every scan, so rows the site adds or updates fall in place.
//
// The site's own sort keeps running underneath. Clicking one of its sortable
// headers hands control back to it.
//
// The sorted look (title glow, arrow) comes from the site's own modifier
// classes, UnitsList_th__desc--<hash> and __asc--<hash>. The hash changes with
// every site build, so the names are read from its stylesheets.

var SORT_ATTR = 'data-unicum-sort';
var ADDED_ATTR = 'data-unicum-added';
var ratingOrder = null;   // null, 'desc' or 'asc'
var sortClasses = null;   // {desc, asc, sortable}

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

function ratingSort(heads) {
    if (!heads.length || heads[0].children.length !== 5) {
        return;
    }
    if (!sortClasses) {
        sortClasses = findSortClasses();
        if (!sortClasses) {
            return;
        }
    }
    var head = heads[0];
    var rating = head.children[1];
    if (!rating.hasAttribute(SORT_ATTR)) {
        rating.setAttribute(SORT_ATTR, '1');
        // The hover and active underlines, copied from a sortable header.
        var template = head.children[2].querySelectorAll('[class*="UnitsList_thCondition"]');
        for (var i = 0; i < template.length; i++) {
            var copy = template[i].cloneNode(false);
            copy.setAttribute(ADDED_ATTR, '1');
            rating.appendChild(copy);
        }
        rating.addEventListener('click', function () {
            if (!alive) {
                return;
            }
            ratingOrder = ratingOrder === 'desc' ? 'asc' : 'desc';
            scan();
        });
        // Any other header click is the site's sort taking over again.
        head.addEventListener('click', function (event) {
            if (alive && !rating.contains(event.target)) {
                ratingOrder = null;
                setTimeout(scan, 0);
            }
        }, true);
    }
    rating.classList.add(sortClasses.sortable);
    rating.classList.toggle(sortClasses.desc, ratingOrder === 'desc');
    rating.classList.toggle(sortClasses.asc, ratingOrder === 'asc');
    // While rating leads, the site's sorted header must not look sorted too.
    for (var h = 2; h < head.children.length; h++) {
        var title = head.children[h].querySelector('[class*="UnitsList_thTitle"]');
        if (title) {
            title.style.cssText = ratingOrder ? 'color:inherit;text-shadow:none' : '';
            title.classList.toggle('unicum-unsorted', !!ratingOrder);
        }
    }
    orderRows();
}

function orderRows() {
    var body = document.querySelector('[class*="UnitsList_tbody"]');
    if (!body) {
        return;
    }
    if (!ratingOrder) {
        if (body.hasAttribute(SORT_ATTR)) {
            body.removeAttribute(SORT_ATTR);
            body.style.display = '';
            body.style.flexDirection = '';
            for (var c = 0; c < body.children.length; c++) {
                body.children[c].style.order = '';
            }
        }
        return;
    }
    body.setAttribute(SORT_ATTR, ratingOrder);
    body.style.display = 'flex';
    body.style.flexDirection = 'column';
    var rows = [];
    for (var i = 0; i < body.children.length; i++) {
        var cell = body.children[i].children[1];
        var value = parseInt(cell ? cell.textContent.replace(/\D/g, '') : '', 10);
        rows.push({row: body.children[i], value: isNaN(value) ? -1 : value, index: i});
    }
    rows.sort(function (a, b) {
        var diff = ratingOrder === 'desc' ? b.value - a.value : a.value - b.value;
        return diff || a.index - b.index;
    });
    for (var k = 0; k < rows.length; k++) {
        rows[k].row.style.order = String(k);
    }
}

function stopRatingSort() {
    ratingOrder = null;
    orderRows();
    var added = document.querySelectorAll('[' + ADDED_ATTR + ']');
    for (var i = 0; i < added.length; i++) {
        added[i].parentNode.removeChild(added[i]);
    }
    var marked = document.querySelectorAll('[' + SORT_ATTR + ']');
    for (var j = 0; j < marked.length; j++) {
        if (sortClasses) {
            marked[j].classList.remove(sortClasses.sortable, sortClasses.desc, sortClasses.asc);
        }
        marked[j].removeAttribute(SORT_ATTR);
    }
    var titles = document.querySelectorAll('.unicum-unsorted');
    for (var t = 0; t < titles.length; t++) {
        titles[t].style.cssText = '';
        titles[t].classList.remove('unicum-unsorted');
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
    for (var i = 0; i < flags[tag].length; i++) {
        var img = document.createElement('img');
        img.src = flags[tag][i];
        img.style.cssText = 'display:block;width:16px;height:12px;margin-left:4px';
        box.appendChild(img);
    }
    return box;
}

function scan() {
    columns();
    prune();
    var spans = document.getElementsByTagName('span');
    var need = [];
    for (var i = 0; i < spans.length; i++) {
        var el = spans[i];
        var tag = tagOf(el);
        if (!tag) {
            continue;
        }
        if (!(tag in flags)) {
            if (!asked[tag]) {
                asked[tag] = 1;
                need.push(tag);
            }
            continue;
        }
        if (!flags[tag].length) {
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

// ---------------------------------------------------------------------------
// Lifecycle

// The app is React: rows are re-rendered and anything added is gone at the
// next render, so every DOM change schedules a rescan. Scans that change
// nothing cause no mutation, so this settles.
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
    stopRatingSort();
    if (timer) {
        clearTimeout(timer);
    }
    var added = document.querySelectorAll('[' + FLAG_ATTR + '], style[' + STYLE_ATTR + ']');
    for (var i = 0; i < added.length; i++) {
        added[i].parentNode.removeChild(added[i]);
    }
    var labels = document.querySelectorAll('[' + LABEL_ATTR + ']');
    for (var j = 0; j < labels.length; j++) {
        labels[j].textContent = labels[j].getAttribute(LABEL_ATTR);
        labels[j].removeAttribute(LABEL_ATTR);
    }
    window.__unicum = null;
}

window.__unicum = {
    v: GENERATION,
    scan: scan,
    set: function (answers) {
        for (var tag in answers) {
            flags[tag] = answers[tag];
        }
        scan();
    },
    stop: stop
};

scan();
