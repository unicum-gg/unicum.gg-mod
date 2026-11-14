// The detachment preview, on the right of the Stronghold window.
//
// Part of the Stronghold content script, see core.js.
//
// The table on the left lists detachments and is addressed by clan tag. This
// one lists the members of the selected detachment and prints a nickname and
// nothing else: no account id, no tag. That is why it carried no ratings
// until `/resolve` learned to take a name, and the reason was never this
// script.
//
// Its own component, `Squad_*`, nothing to do with the `UnitsList_*` of the
// left table (table.js), so the two share the painting and no selectors:
//
//   Squad_tr          a row, header row included
//   Squad_name        the name cell, holding a Member_base
//   Member_base       the member; Member_clanTag their tag, when they wear one
//   Squad_rating      that member's rating cell, one per row
//   Squad_ratingIcon  the icon heading that column
//
// `Squad_ratingIcon` is the trap: it starts with `Squad_rating`, so the
// obvious selector matches seven things where six were wanted, and the
// seventh is the header.
//
// The member's rating cell is taken over the way the left table takes over
// its own: the site's number is replaced by ours, its text kept in LABEL_ATTR
// for the teardown, and TAKEN_ATTR marking what else to undo. Wargaming's
// personal rating is what that column held, which is the same trade the left
// table makes and the same one that was asked for.

function squadRows() {
    return document.querySelectorAll('[class*="Squad_tr"]');
}

// The rating cell of a row, never the icon heading the column.
function squadRating(row) {
    var cells = row.querySelectorAll('[class*="Squad_rating"]');
    for (var i = 0; i < cells.length; i++) {
        if (String(cells[i].getAttribute('class') || '').indexOf('ratingIcon') === -1) {
            return cells[i];
        }
    }
    return null;
}

// The nickname in a row, without the clan tag the member wears beside it.
//
// Read by taking the member's whole text and removing the tag's, rather than
// by reaching for a nickname element: the tag is its own node and the name is
// not, it is the text around it.
function squadName(row) {
    var cell = row.querySelector('[class*="Squad_name"]');
    if (!cell) {
        return null;
    }
    var member = cell.querySelector('[class*="Member_base"]') || cell;
    var text = member.textContent || '';
    var tag = member.querySelector('[class*="Member_clanTag"]');
    if (tag && tag.textContent) {
        text = text.split(tag.textContent).join('');
    }
    text = text.replace(/\[\s*\]/g, '').trim();
    // Wargaming's own rule, which is also what the bridge accepts: letters,
    // digits and underscores. Anything else is a row we misread, and asking
    // about it would send the page's text somewhere it has no business going.
    return /^[A-Za-z0-9_]{1,24}$/.test(text) ? text : null;
}

// The column's header: the site's icon hidden, our name in its place as the
// chip the mod stamps into a badge's corner. `headerLabel` is the left
// table's, and it does both.
function squadHeader() {
    var icon = document.querySelector('[class*="Squad_ratingIcon"]');
    if (!icon) {
        return;
    }
    var cell = icon.closest ? icon.closest('[class*="Squad_th"]') : null;
    headerLabel(cell || icon.parentNode || icon, RATING_TITLE);
}

function squad() {
    if (!SHOW_RATING) {
        return;
    }
    var rows = squadRows();
    var need = [];
    var painted = 0;
    for (var r = 0; r < rows.length; r++) {
        var name = squadName(rows[r]);
        var cell = squadRating(rows[r]);
        if (!name || !cell) {
            continue;
        }
        if (!(name in players)) {
            if (!askedPlayers[name]) {
                askedPlayers[name] = 1;
                need.push(name);
            }
            continue;
        }
        takeOver(cell);
        // Counted on what was DRAWN, never on what was attempted: the header
        // is renamed off this, and a column called 30d WNX over a panel still
        // showing Wargaming's own numbers is worse than an unnamed one.
        if (paintScore(cell, players[name].score)) {
            painted++;
        }
    }
    // Only once a row has been painted, so the column is not renamed over a
    // panel that is still showing the site's own numbers.
    if (painted) {
        squadHeader();
    }
    if (need.length) {
        console.log(PLAYER_PREFIX + need.join(','));
    }
}
