// The detachment list table.
//
// Part of the Stronghold content script, see core.js.
//
// Flex rows of five cells: name, rating, server, members, places, plus a
// sixth icon cell on rows the player cannot join. Rating is not sortable on
// the site; server and places are, members is not.
//
//   - "Places" only restates "Members" (7 places minus 2/7 members). The
//     sortable places header is kept, with its native sort arrow, and
//     relabelled with the members header's own text; the members header and
//     the places cells are hidden. Sorting by free places is sorting by
//     members, with the arrow reversed.
//   - The rating chosen in the mod's settings (RATING_TITLE, e.g. "30d WNX")
//     is written INTO the site's own Rating column, as the site's coloured
//     badge, and that column is relabelled; unless SHOW_RATING is false.
//     The site's stronghold rating is overwritten and is then not shown
//     anywhere on the page. That is the trade, and it was asked for: a
//     table one column narrower, and one number in the column named for it
//     rather than two numbers meaning different things side by side.
//   - That column is made sortable, by our figure, see sorting.js.
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
    probe();
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

    if (!SHOW_RATING) {
        hideRows();
        sorting(head);
        return;
    }

    // The site's Rating header becomes ours: relabelled, and marked as the
    // score column so sorting.js finds it where it used to find the one we
    // inserted. Taken over rather than added, so there is no sixth column
    // and the header row lines up with the body without being forced to.
    var scoreHead = cells[1];
    takeOver(scoreHead);
    headerLabel(scoreHead, RATING_TITLE);

    var rows = bodyRows();
    for (var r = 0; r < rows.length; r++) {
        var row = rows[r];
        var rowCells = siteCells(row);
        // Five cells, or six: a detachment the player cannot join carries a
        // trailing icon cell (crossed swords) after places.
        if (rowCells.length < 5) {
            continue;
        }
        rowCells[4].setAttribute(HIDE_ATTR, '1');
        takeOver(rowCells[1]);
        fillScore(rowCells[1], rowTag(rowCells[0]));
    }
    sorting(head);
}

// A site cell we write into rather than one we add. TAKEN_ATTR marks what
// the teardown has to undo on it: the badge's inline style, the sort value,
// and the site's own tooltip, which described the rating the column no
// longer holds.
function takeOver(cell) {
    cell.setAttribute(TAKEN_ATTR, '1');
    cell.setAttribute(COL_ATTR, 'score');
    for (var a = 0; a < TIP_ATTRS.length; a++) {
        var name = TIP_ATTRS[a];
        if (cell.hasAttribute(name)) {
            cell.setAttribute('data-unicum-was-' + name, cell.getAttribute(name));
            cell.removeAttribute(name);
        }
    }
}

// The column's name, as the chip the mod stamps into the corner of a badge
// everywhere else.
//
// Added beside the site's own header content rather than written over it.
// That header is an icon, not a word: writing text into it put our label
// where a glyph was, in a font that has no letters for it. The icon is
// hidden instead, which the teardown already knows how to give back, and
// our label is a node we added, which it already knows how to remove.
function headerLabel(cell, text) {
    var title = cell.querySelector('[class*="UnitsList_thTitle"]') || cell;
    for (var i = 0; i < title.children.length; i++) {
        var kid = title.children[i];
        if (!kid.hasAttribute(ADDED_ATTR)) {
            kid.setAttribute(HIDE_ATTR, '1');
        }
    }
    var label = title.querySelector('[' + COL_ATTR + '="title"]');
    if (!label) {
        label = document.createElement('span');
        label.setAttribute(ADDED_ATTR, '1');
        label.setAttribute(COL_ATTR, 'title');
        label.setAttribute('style', CHIP_CSS);
        title.appendChild(label);
    }
    setText(label, text);
}

// Places cells hidden as with the column, for rows without it.
function hideRows() {
    var rows = bodyRows();
    for (var r = 0; r < rows.length; r++) {
        var rowCells = siteCells(rows[r]);
        if (rowCells.length >= 5) {
            rowCells[4].setAttribute(HIDE_ATTR, '1');
        }
    }
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

// Grouped the way the site writes ratings, "3 323", with a narrow no-break
// space. Built from its code point: the script has to stay ASCII.
var THOUSANDS = String.fromCharCode(0x202F);

function formatRating(value) {
    return String(Math.round(value)).replace(/\B(?=(\d{3})+(?!\d))/g, THOUSANDS);
}

// The site's rating badge: the scale's colour as the background, white text.
var BADGE_CSS = 'display:inline-block;padding:1px 5px;border-radius:3px;' +
                'color:#FFFFFF;line-height:16px;text-shadow:none';

// The column's name, in the shape the mod names a figure everywhere else:
// the small dark chip it stamps into a badge's corner, shouted and short.
// Same band as the chip's (badge_png.TAG_BAND), so the two read as one
// naming and not as two.
var CHIP_CSS = 'display:inline-block;padding:0 4px;border-radius:2px;' +
               'background-color:#1F1F1F;color:#FFFFFF;font-size:10px;' +
               'line-height:14px;letter-spacing:0.04em;text-transform:uppercase;' +
               'white-space:nowrap;text-shadow:none';

function fillScore(cell, tag) {
    paintScore(cell, tag && clans[tag] ? clans[tag].score : null);
}

// One figure into one cell we have taken over, left table or preview panel.
// Shared because they draw the same badge; the lookup is not, because one is
// keyed by clan tag and the other by nickname.
function paintScore(cell, score) {
    var span = scoreSpan(cell);
    if (!span) {
        return false;
    }
    if (!span.hasAttribute(LABEL_ATTR)) {
        span.setAttribute(LABEL_ATTR, span.textContent);
    }
    setText(span, score ? formatRating(score.value) : '-');
    var style = score && score.color ? BADGE_CSS + ';background-color:' + score.color : '';
    if (span.getAttribute('style') !== style) {
        span.setAttribute('style', style);
    }
    cell.setAttribute('data-value', score ? String(score.value) : '-1');
    return true;
}

// The element the badge is painted onto: the cell's own span where it has
// one, a span we add where it does not.
//
// `querySelector`, not `firstChild`: this used to be a cell we had built
// ourselves, whose only child was its span. It is the site's cell now, and
// the two tables do not agree about it. The left one wraps its number in a
// span; the preview panel on the right holds it as a bare text node, so
// looking for a span there found nothing and the paint returned silently
// while everything around it reported success -- the header was renamed over
// rows still showing Wargaming's own figures.
//
// The cell's own text goes into LABEL_ATTR on the cell, which the teardown
// restores, and the span is marked as ours, which the teardown removes.
function scoreSpan(cell) {
    var span = cell.querySelector('span');
    if (span) {
        return span;
    }
    span = cell.querySelector('[' + COL_ATTR + '="value"]');
    if (!span) {
        if (!cell.hasAttribute(LABEL_ATTR)) {
            cell.setAttribute(LABEL_ATTR, cell.textContent);
        }
        span = donorSpan();
        span.setAttribute(ADDED_ATTR, '1');
        span.setAttribute(COL_ATTR, 'value');
        cell.textContent = '';
        cell.appendChild(span);
    } else if (!span.className) {
        // Born before the list had drawn anything, so it was born bare. The
        // donor exists now, and the classes are the whole of what makes the
        // two badges one badge.
        var donor = donorSpan();
        if (donor.className) {
            span.className = donor.className;
        }
    }
    return span;
}

// An empty copy of the element the site puts a figure in, taken from the
// detachment list on the left.
//
// The panel on the right holds its figure as a bare text node, so there is
// nothing there to paint onto and one has to be made. Made by cloning the
// list's rather than by building a span and dressing it: the two tables set
// type differently, so a bare span inherits the panel's size and the same
// badge comes out bigger on one side than the other. Matching that by hand
// means a number in this file that is right until either table is restyled.
// A clone carries the site's own classes, so the two are the same component
// and agree by construction, whatever the site does to it later.
//
// A plain span when the list has drawn nothing yet, which is the first pass
// of a fresh page; the branch above re-dresses it once a donor exists.
function donorSpan() {
    var drawn = document.querySelector(
        '[class*="UnitsList_tr"] [' + TAKEN_ATTR + '] span');
    if (!drawn) {
        return document.createElement('span');
    }
    // The classes are what is wanted; everything else on the donor belongs
    // to the row it came from. Its inline style is one clan's band colour,
    // which `paintScore` would overwrite anyway, and its LABEL_ATTR is that
    // clan's own figure, which the teardown would read as this cell's.
    var copy = drawn.cloneNode(false);
    copy.removeAttribute('style');
    copy.removeAttribute(LABEL_ATTR);
    copy.removeAttribute('data-value');
    return copy;
}
