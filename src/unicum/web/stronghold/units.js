// The detachments behind the list's rows, and what their line-ups are worth.
//
// Part of the Stronghold content script, see core.js.
//
// The column used to carry the clan's rating, which is the same number on
// every detachment that clan has out: seven rows, one figure, nothing to
// choose between them. What is wanted is what the seven people in THIS
// detachment are worth, in the rating the mod is set to.
//
// The page does not carry that. A detachment, as the page holds it, is a
// clan, a commander's nickname, a periphery and a set of counts:
//
//   {average_rating, clan:{id,tag,name,emblem,color}, periphery:{id,name},
//    id, server_id, type, max_vehicle_level, in_battle, is_open,
//    members_number, max_members_number, legionaries_number, ...}
//
// Its members arrive only for the one you select, from
//   <WGSH_API_URL>/game_api/units/<server_id>/<periphery id>/participants
// which is the request the page makes itself -- `requestUnitParticipants` in
// its own bundle. So this makes the same request, one detachment at a time
// and never twice for the same roster, and hands the nicknames to Python,
// which already knows how to turn a nickname into a rating.
//
// `average_rating` is the site's own answer to the same question, in
// Wargaming's personal rating. It is per detachment, not per clan, which is
// what the column held before the mod took it over.

// What came back about a detachment, by its id:
//   undefined  not asked yet, or still being asked -- the column draws a
//              placeholder, because waiting and not knowing are different
//              things and a dash said both
//   null       asked and answered with nobody this mod can rate
//   a score    the badge Python drew for the line-up's average
//
// Kept across re-renders and across list refreshes: a detachment keeps its
// id, so a roster already fetched is not fetched again when the list updates
// around it.
var unitScores = {};
var askedUnits = {};    // "<id>:<members>" -> 1, one fetch per roster
var tries = {};         // the same key -> how many times it has been tried
var pending = [];       // detachments waiting their turn, in display order
var fetching = false;

// One request at a time, spaced. A dozen rows is a dozen requests, and a
// burst of those every time the list moves is not a thing to do to somebody
// else's server. Short enough that the rows you read first are filled in
// about a second.
var FETCH_GAP = 150;

// A roster that did not come back is asked for again, twice more and well
// apart: the first answer a session gets may be a refusal the site itself
// recovers from by signing in again. Three failures is not a bad moment.
var RETRY_GAP = 20000;
var MAX_TRIES = 3;

function unitKey(unit) {
    return unit.id + ':' + unit.members_number;
}

// The props the list was rendered from, found by walking up from a row.
//
// React hangs a fiber off each DOM node and each fiber up from there is one
// component with what it was given. The list's own component is about a
// dozen levels above a row, past the row's table and the scroll area, and it
// is the one holding `units`.
function listProps() {
    var row = document.querySelector('[class*="UnitsList_tbody"] > *');
    if (!row) {
        return null;
    }
    var fiber = null;
    for (var key in row) {
        if (key.indexOf('__reactFiber') === 0 || key.indexOf('__reactInternalInstance') === 0) {
            fiber = row[key];
            break;
        }
    }
    for (var up = 0; up < 20 && fiber; up++) {
        var props = fiber.memoizedProps;
        if (props && props.units && typeof props.units.length === 'number' &&
                props.availablePeripheries) {
            return props;
        }
        fiber = fiber['return'];
    }
    return null;
}

// The detachments in the order their rows are drawn in.
//
// The site's own render, repeated: the units it was given, kept to the
// peripheries on offer, its own clan's first and every other clan's after.
// Repeated rather than guessed at -- it is four lines of its bundle -- and
// checked against the rows by the caller, which is what makes repeating it
// safe: when the two disagree, nothing is painted.
function orderedUnits() {
    var props = listProps();
    if (!props) {
        return null;
    }
    var peripheries = props.availablePeripheries || [];
    var mine = [];
    var others = [];
    for (var i = 0; i < props.units.length; i++) {
        var unit = props.units[i];
        if (!unit || !unit.clan || !unit.periphery) {
            return null;
        }
        var offered = false;
        for (var p = 0; p < peripheries.length; p++) {
            if (peripheries[p] === unit.periphery.id) {
                offered = true;
                break;
            }
        }
        if (!offered) {
            continue;
        }
        (unit.clan.id === props.clanId ? mine : others).push(unit);
    }
    return mine.concat(others);
}

// What a detachment's line-up averages: a score, null when nobody in it can
// be rated, undefined while that is still being found out.
//
// No detachment at all is undefined too, not null: a row the pairing has not
// reached yet is still working, and a dash there would be this script
// claiming an answer it has not got.
function unitScore(unit) {
    return unit ? unitScores[unit.id] : undefined;
}

// What is worth asking for, which is only what is on screen now.
//
// Rebuilt on every scan rather than appended to: switching tabs replaces the
// whole list, and a queue that remembers the old one spends its first
// seconds fetching detachments nobody is looking at any more. Only the
// request already in flight belongs to the tab you left, and it is one.
//
// A roster is marked as asked when its request STARTS, not when it is
// queued, so a detachment that scrolls out of the list and back in is not
// lost for the rest of the session.
function planLineups(units) {
    pending = [];
    if (units) {
        for (var i = 0; i < units.length; i++) {
            var unit = units[i];
            if (unitScores[unit.id] === undefined && !askedUnits[unitKey(unit)]) {
                pending.push(unit);
            }
        }
    }
    pump();
}

function pump() {
    if (fetching || !pending.length || !alive) {
        return;
    }
    var unit = pending.shift();
    askedUnits[unitKey(unit)] = 1;
    fetching = true;
    fetchLineup(unit, function () {
        setTimeout(function () {
            fetching = false;
            pump();
        }, FETCH_GAP);
    });
}

// Where the page's own API lives, and the request it makes to it.
//
// Both read out of the site's own `httpRequest`, because neither is
// guessable and the first attempt guessed both wrong: a `/game_api` path is
// prefixed with `window.config.WGSH_API_URL`, and without that prefix the
// request goes to the host the PAGE is served from, which is a static CDN
// and answers with something that is not a line-up. The request carries the
// session's cookies and the CSRF token the site keeps in `wgsh_csrf_token`.
function participantsUrl(unit) {
    var root = (window.config && window.config.WGSH_API_URL) || '';
    return root + '/game_api/units/' + unit.server_id + '/' +
           unit.periphery.id + '/participants';
}

function apiOptions() {
    var options = {
        method: 'GET',
        credentials: 'include',
        headers: {'Accept': 'application/json', 'Content-Type': 'application/json'}
    };
    var token = cookie('wgsh_csrf_token');
    if (token) {
        options.headers['X-CSRF-Token'] = token;
    }
    return options;
}

function cookie(name) {
    var parts = String(document.cookie || '').split(';');
    for (var i = 0; i < parts.length; i++) {
        var pair = parts[i].split('=');
        if (pair[0].replace(/^\s+|\s+$/g, '') === name) {
            return (pair[1] || '').replace(/^\s+|\s+$/g, '');
        }
    }
    return null;
}

// One detachment's members, from the page's own endpoint, handed to Python.
//
// Nicknames are checked here as well as there: Wargaming's own rule is
// letters, digits and underscores, and anything else is a row we misread,
// which has no business being sent anywhere.
function fetchLineup(unit, done) {
    var finish = function () {
        done();
        done = function () {};
    };
    var status = 0;
    try {
        fetch(participantsUrl(unit), apiOptions()).then(function (answer) {
            status = answer.status;
            return answer.text();
        }).then(function (text) {
            var body = null;
            try {
                body = JSON.parse(text);
            } catch (bad) {
                body = null;
            }
            var list = body && typeof body.length === 'number' ? body
                     : (body && body.participants) || null;
            var names = [];
            for (var i = 0; list && i < list.length; i++) {
                var who = list[i] || {};
                var name = who.account_nickname || who.nickname || who.name;
                if (name && /^[A-Za-z0-9_]{1,24}$/.test(name)) {
                    names.push(name);
                }
            }
            if (names.length) {
                console.log(UNIT_PREFIX + unit.id + ',' + names.join(','));
            } else if (list) {
                // Answered, with nobody in it this mod can name. That is an
                // answer: the column stops waiting and says so.
                unitScores[unit.id] = null;
            } else {
                // The status and the first of the answer, because "nobody
                // came back" and "the request was refused" are the same
                // silence otherwise, and the first attempt at this spent a
                // whole round guessing between them.
                console.log(PROBE_PREFIX + 'detachment ' + unit.id + ': ' + status +
                            ' ' + String(text).substring(0, 200));
                retryLineup(unit);
            }
            finish();
        })['catch'](function (trouble) {
            console.log(PROBE_PREFIX + 'detachment ' + unit.id + ' not read: ' + trouble);
            retryLineup(unit);
            finish();
        });
    } catch (e) {
        retryLineup(unit);
        finish();
    }
}

// Let it be asked for again later, or give up and say so.
//
// Giving up is what turns the placeholder into a dash: while there are
// tries left the row is still waiting, and that is what the placeholder
// means.
function retryLineup(unit) {
    var key = unitKey(unit);
    tries[key] = (tries[key] || 0) + 1;
    if (tries[key] >= MAX_TRIES) {
        unitScores[unit.id] = null;
        return;
    }
    setTimeout(function () {
        if (alive) {
            delete askedUnits[key];
            scan();
        }
    }, RETRY_GAP);
}
