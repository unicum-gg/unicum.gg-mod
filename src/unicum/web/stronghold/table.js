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
        // Five cells, or six: a detachment the player cannot join carries a
        // trailing icon cell (crossed swords) after places.
        if (rowCells.length < 5) {
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
