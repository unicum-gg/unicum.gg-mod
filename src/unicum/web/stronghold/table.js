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
//   - What each detachment's LINE-UP averages, in the rating chosen in the
//     mod's settings (RATING_TITLE, e.g. "30d WNX"), is written INTO the
//     site's own Rating column, and that column is relabelled; unless
//     SHOW_RATING is false. Where that figure comes from, and why it is the
//     line-up's rather than the clan's, is units.js.
//     The site's own average is overwritten and is then not shown anywhere
//     on the page. That is the trade, and it was asked for: a table one
//     column narrower, and one number in the column named for it rather
//     than two numbers meaning different things side by side.
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
    // Our column's figure under our column's name, on one centre line.
    //
    // The same cell is padded differently in the header row and in the body
    // row, so its two boxes do not begin at the same place: the chip sits at
    // the start of one and the badge at the start of the other, and the
    // badge reads as pushed aside. Centring on its own does not settle it
    // either -- centred inside boxes of different widths is still two centre
    // lines, unless that padding is symmetric, and the site is not held to
    // that.
    //
    // So the horizontal padding goes and the content is centred, in both
    // rows: two boxes of the same width, one centre each, the same one. The
    // vertical padding is the site's and stays -- it is what gives a row its
    // height. No figure measured here, which is the point: a nudge in pixels
    // would be true of this build of the site and of nothing else.
    '[class*="UnitsList_tr--"] > [' + COL_ATTR + '="score"] {' +
        ' display: flex !important; align-items: center !important;' +
        ' justify-content: center !important; text-align: center !important;' +
        ' padding-left: 0 !important; padding-right: 0 !important; }',
    // What the header puts the chip inside, which may be the thing filling
    // the cell rather than the chip itself. Centred both ways a wrapper can
    // be, because which of the two it is belongs to the site's build and not
    // to us.
    '[class*="UnitsList_tr--"] > [' + COL_ATTR + '="score"] > * {' +
        ' justify-content: center !important; text-align: center !important; }',
    // The clan's column: a row of its own, so the flags can be pushed to its
    // far end and the name keeps everything between. `min-width: 0` on what
    // the site put in it so that its name still gives way before the flags
    // do -- a flex item refuses to shrink past its content without it, and
    // a long clan name would have pushed the flags out of the column.
    '[class*="UnitsList_tr--"] > :first-child {' +
        ' flex: 1 1 0 !important; min-width: 0 !important; max-width: none !important;' +
        ' display: flex !important; align-items: center !important; }',
    '[class*="UnitsList_tr--"] > :first-child > :first-child { min-width: 0 !important; }',
    '[class*="UnitsList_tr--"] > :first-child > [' + FLAG_ATTR + '] {' +
        ' margin-left: auto !important; padding-left: 8px !important; }',
    // The site's sort arrow on its own header, while one of our sorts leads.
    '.unicum-unsorted::after { visibility: hidden !important; }',
    SKELETON_KEYFRAMES
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
        setText(to, from.textContent);
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
    // The detachments in the order the site drew them (units.js), and the
    // rows they were drawn into. Paired by position, which is the only thing
    // they share: a row carries no id of its own, only a key that is its
    // index. So the pairing is CHECKED before it is used -- the two counts
    // must agree -- and when they do not, no row is paired with anything.
    // Painting a detachment's figure onto another detachment's row would be
    // worse than painting nothing, and nothing here could tell afterwards.
    //
    // An unpaired row shows the placeholder, NOT a dash. A dash is an
    // answer, and "I have not matched this row to a detachment yet" is not
    // one: the list is drawn before its data settles, so the first scans of
    // a fresh page have rows and no detachments, and a column of dashes
    // that turned into figures a moment later is exactly what that looked
    // like from the outside.
    var ordered = orderedUnits();
    var seen = 0;
    for (var r = 0; r < rows.length; r++) {
        var rowCells = siteCells(rows[r]);
        // Five cells, or six: a detachment the player cannot join carries a
        // trailing icon cell (crossed swords) after places. Fewer is the
        // "Other Clans Detachments" subtitle, which is a row of the table
        // and not a detachment.
        if (rowCells.length < 5) {
            continue;
        }
        seen++;
    }
    if (!ordered) {
        unpaired('none', seen);
    } else if (ordered.length !== seen) {
        unpaired(ordered.length, seen);
        ordered = null;
    }
    // What to fetch, rebuilt from what is on screen right now (units.js).
    planLineups(ordered);
    seen = 0;
    for (var b = 0; b < rows.length; b++) {
        var cells2 = siteCells(rows[b]);
        if (cells2.length < 5) {
            continue;
        }
        cells2[4].setAttribute(HIDE_ATTR, '1');
        takeOver(cells2[1]);
        fillScore(cells2[1], ordered ? ordered[seen] : undefined);
        seen++;
    }
    sorting(head);
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

function fillScore(cell, unit) {
    paintScore(cell, unitScore(unit));
}

// Said once per count, not once per scan: the list redraws constantly, and a
// pairing that cannot be made is a thing to read about once rather than two
// hundred times. A mismatch is not an error in itself -- the list is drawn
// before its data settles -- but one that stays is this script reading the
// site's render wrongly, and that has to be visible.
var unpairedAt = null;

function unpaired(units, rows) {
    var said = units + '/' + rows;
    if (unpairedAt !== said) {
        unpairedAt = said;
        console.log(PROBE_PREFIX + 'rows ' + rows + ' but ' + units + ' detachments');
    }
}

// One figure into one cell we have taken over, left table or preview panel.
// Shared because they draw the same badge; the lookup is not, because one is
// keyed by clan tag and the other by nickname.
