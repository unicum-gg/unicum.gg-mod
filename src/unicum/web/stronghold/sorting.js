// Sorting the detachment list by rating or WNX.
//
// Part of the Stronghold content script, see core.js.
//
// The site sorts by server and places but not by rating, and knows nothing of
// WNX. Both headers are made to look and act sortable: a click sorts by that
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
