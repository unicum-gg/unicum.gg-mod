// Scanning, stopping, and the handle Python talks to.
//
// Part of the Stronghold content script, see core.js. Last, because it runs
// the first scan.
//
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
