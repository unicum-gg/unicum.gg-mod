// Content script for the Stronghold pages of the embedded browser.
//
// One script split across this folder. src/unicum/browser.py joins the files
// in the order of its _CONTENT_SCRIPT_FILES (core, table, sorting, flags,
// lifecycle), wraps the result in
//   (function(GENERATION, RATING_TITLE, SHOW_RATING){ <the files> })(...);
// and runs that as javascript:eval(atob('<base64>')), where RATING_TITLE and
// SHOW_RATING carry the mod's settings: the rating column's title, and
// whether there is one. So the files share one scope, may use any syntax and
// comments, and `return` at the top level, but must stay ASCII (atob decodes
// to Latin-1). They are read again at every injection: reopening the
// Stronghold window picks up an edit without a client restart.
//
// Talks back through console.log, which the client forwards to Python:
//   [unicum] need TAG1,TAG2   tags this page has no answer for yet
// Python answers by calling window.__unicum.set({TAG: clan}), where clan is
//   {flags: [dataUri, ...], score: {value: 1792, color: '#6D9521'} or null}
//
// GENERATION changes with every reload of the mod and every settings change.
// Either injects the new version, which finds the old one by its other
// generation and stops it first, so the page never runs two observers or
// holds two sets of flags.

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
var clans = {};    // tag -> {flags, score}
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
