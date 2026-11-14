// Writing one figure into one cell the site owns.
//
// Part of the Stronghold content script, see core.js.
//
// Shared by the detachment list on the left (table.js) and the detachment
// preview on the right (squad.js): the two are different components, keyed
// differently and found by different selectors, but a figure goes into a
// cell of either the same way. The rule that makes any of it safe is in
// `setText`, and it is the whole reason this is written the way it is.

// Text into an element the site owns, without taking anything out of it.
//
// `el.textContent = x` does not edit the text node that is already there: it
// throws that node away and makes a new one. The site's React still holds
// the old one, and at its next update of that row it calls removeChild on a
// node whose parent is now null -- a NotFoundError, a DOMException, thrown
// from inside React's own commit. The site catches it where it catches its
// request, logs ">> WGSH cannot request available units [object
// DOMException]", and the React root comes down with it.
//
// That is the window going black. The log has that line nine times today and
// not once on either of the two days before, and the first of the nine is 90
// seconds after this script first wrote into a cell of the site's own.
//
// So the node is edited in place and keeps the identity React knows it by.
// React may write the site's own value back into it at any render; the next
// scan writes ours again, which is the loop every other write here already
// lives in. A second text node, should the site ever render one, is emptied
// rather than left holding a stale half of the text.
function setText(el, text) {
    var written = false;
    for (var i = 0; i < el.childNodes.length; i++) {
        var node = el.childNodes[i];
        if (node.nodeType !== 3) {
            continue;
        }
        var want = written ? '' : text;
        if (node.nodeValue !== want) {
            node.nodeValue = want;
        }
        written = true;
    }
    if (!written && text !== '') {
        el.appendChild(document.createTextNode(text));
    }
}

// The site's own content in a cell we took over, put out of the way without
// taking any of it out of the page: text emptied in place, elements hidden
// with the attribute the teardown already lifts. Nothing React made leaves
// the tree, which is the whole of the point -- see setText.
function clearSite(cell) {
    setText(cell, '');
    for (var i = 0; i < cell.children.length; i++) {
        if (!cell.children[i].hasAttribute(ADDED_ATTR)) {
            cell.children[i].setAttribute(HIDE_ATTR, '1');
        }
    }
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

// Grouped the way the site writes ratings, "3 323", with a narrow no-break
// space. Built from its code point: the script has to stay ASCII.
var THOUSANDS = String.fromCharCode(0x202F);

function formatRating(value) {
    return String(Math.round(value)).replace(/\B(?=(\d{3})+(?!\d))/g, THOUSANDS);
}

// The site's rating badge: the scale's colour as the background, white text.
var BADGE_CSS = 'display:inline-block;padding:1px 5px;border-radius:3px;' +
                'color:#FFFFFF;line-height:16px;text-shadow:none';

// The badge's place while its figure is still being worked out: a bar the
// size of the badge that will stand there, breathing.
//
// Keyframes cannot live in an inline style, so the animation is named here
// and asked for below. The table's own stylesheet carries it (table.js).
var SKELETON_KEYFRAMES =
    '@keyframes unicum-wait { 0%, 100% { opacity: 0.25 } 50% { opacity: 0.5 } }';

var SKELETON_CSS = 'display:inline-block;border-radius:3px;' +
                   'background-color:#FFFFFF;opacity:0.35;vertical-align:middle;' +
                   'animation:unicum-wait 1.2s ease-in-out infinite';

// How big that bar is, which is the one thing it must not get wrong: a bar
// wider than the badge reads as a long dash and says nothing.
//
// Taken from the badge itself, the last one this column drew, because that
// is exactly what it stands in for. Before the first badge of the session
// exists, from the site's own figure still sitting in the cell: the same
// four digits in the same type. Measured on both counts, never written
// down -- a width in this file would be right on one machine and on one
// build of the site.
var badgeBox = null;
var waitWidth = null;

function placeholderStyle(span) {
    if (badgeBox) {
        return SKELETON_CSS + ';width:' + badgeBox.width + 'px' +
               ';height:' + badgeBox.height + 'px';
    }
    if (waitWidth === null) {
        var box = span.getBoundingClientRect();
        if (box && box.width > 1) {
            waitWidth = Math.round(box.width);
        }
    }
    // Nothing to measure yet, so nothing drawn: an empty cell for a frame,
    // rather than a bar of a size invented here.
    return waitWidth === null ? ''
         : SKELETON_CSS + ';width:' + waitWidth + 'px;height:1em';
}

// The badge when it arrives as the mod's own image. Its own size in pixels,
// which is the whole point: the client draws it at twelve pixels tall and so
// does this, in both panels, whatever type either of them sets.
var IMAGE_CSS = 'display:inline-block;background-repeat:no-repeat;' +
                'background-size:100% 100%;vertical-align:middle';

// The column's name, in the shape the mod names a figure everywhere else:
// the small dark chip it stamps into a badge's corner, shouted and short.
// Same band as the chip's (badge_png.TAG_BAND), so the two read as one
// naming and not as two.
var CHIP_CSS = 'display:inline-block;padding:0 4px;border-radius:2px;' +
               'background-color:#1F1F1F;color:#FFFFFF;font-size:10px;' +
               'line-height:14px;letter-spacing:0.04em;text-transform:uppercase;' +
               'white-space:nowrap;text-shadow:none';

function paintScore(cell, score) {
    var span = scoreSpan(cell);
    if (!span) {
        return false;
    }
    if (!span.hasAttribute(LABEL_ATTR)) {
        span.setAttribute(LABEL_ATTR, span.textContent);
    }
    // The badge as an image where one came: the same PNG the client draws
    // in the skirmish room and over the tanks, so the two are the same
    // badge rather than two drawings of one. A shape built here in CSS
    // inherits whichever panel it lands in and comes out a different size
    // on each, which is what it did.
    //
    // The text and the band stay the fallback, for a badge the client could
    // not draw at all.
    var style;
    if (score === undefined) {
        // Still being found out. A placeholder rather than a dash, because a
        // dash is an answer -- "nobody here can be rated" -- and a row that
        // is simply still working has not said that.
        style = placeholderStyle(span);
        setText(span, '');
    } else if (score && score.image) {
        setText(span, '');
        badgeBox = {width: score.width, height: score.height};
        style = IMAGE_CSS + ';width:' + score.width + 'px;height:' + score.height +
                'px;background-image:url(' + score.image + ')';
    } else {
        setText(span, score ? formatRating(score.value) : '-');
        style = score && score.color ? BADGE_CSS + ';background-color:' + score.color : '';
    }
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
    // Ours first, then the site's. Ours is a span too, so looking for a span
    // at all would find it and the rest of this would never run again.
    var span = cell.querySelector('[' + COL_ATTR + '="value"]');
    if (span) {
        // The site goes on rendering its own figure into the cell around our
        // span, so it is put back out of sight on every pass rather than
        // once when the span was made.
        clearSite(cell);
        if (!span.className) {
            // Born before the list had drawn anything, so it was born bare.
            // The donor exists now, and the classes are the whole of what
            // makes the two badges one badge.
            var donor = donorSpan();
            if (donor.className) {
                span.className = donor.className;
            }
        }
        return span;
    }
    span = cell.querySelector('span');
    if (span) {
        return span;
    }
    if (!cell.hasAttribute(LABEL_ATTR)) {
        cell.setAttribute(LABEL_ATTR, cell.textContent);
    }
    span = donorSpan();
    span.setAttribute(ADDED_ATTR, '1');
    span.setAttribute(COL_ATTR, 'value');
    clearSite(cell);
    cell.appendChild(span);
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
