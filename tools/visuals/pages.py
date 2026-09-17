"""The listing visuals' HTML pages, from sample data.

Every player below is invented but Winnie, the mod's author. Ratings take the
colours of unicum.gg's WNx bands (GET /api/ratings/scales), and the flags,
logos, vehicle contours and map art are the ones build.py gathers in assets/.
"""
import random

# (upper bound, colour) of unicum.gg's WNx bands, the last one open.
WNX_BANDS = [(200, '#000000'), (400, '#CD3333'), (800, '#D77900'), (1200, '#D7B600'), (1600, '#6D9521'),
             (1800, '#4C762E'), (2200, '#4A92B7'), (2800, '#83579D'), (None, '#5A3175')]

TANKS = [('Obj. 140', 'ussr-R97_Object_140'), ('E 100', 'germany-G56_E-100'), ('T110E4', 'usa-A83_T110E4'),
         ('Bat.-Châtillon 25 t', 'france-F18_Bat_Chatillon25t'), ('FV4202', 'uk-GB70_N_FV4202_105'),
         ('TVP T 50/51', 'czech-Cz04_T50_51'), ('Strv 103B', 'sweden-S11_Strv_103B'), ('Maus', 'germany-G42_Maus'),
         ('Obj. 268/4', 'ussr-R149_Object_268_4'), ('113', 'china-Ch22_113'), ('Leopard 1', 'germany-G89_Leopard1'),
         ('IS-7', 'ussr-R45_IS-7'), ('AMX 50 B', 'france-F10_AMX_50B'), ('60TP', 'poland-Pl15_60TP_Lewandowskiego')]

FLAG_CODES = ['FR', 'DE', 'PL', 'CZ', 'UA', 'GB', 'ES', 'IT', 'SE', 'NL', 'BE', 'HU']

TWITCH_BADGES = ['broadcaster.1', 'moderator.1', 'vip.1', 'premium.1', 'turbo.1', 'partner.1']

NAMES_LEFT = ['Kretek_PL', 'LaBaguette', 'Panzerfrosch', 'ShellShock_', 'vbd_Tomas', 'Nordlys', 'xX_Hetzer_Xx',
              'ArmoredOtter', 'RicochetRita', 'Ferdinand88', 'CzechMate', 'Ivanhoe_UK', 'Mad_Merkava', 'PiouPiou', 'Smok']
NAMES_RIGHT = ['Bamboozler', 'TigerLily', 'Rammstein_EU', 'derp_gun', 'Kaiserschmarrn', 'Vlaam', 'TundraFox',
               'HEATseeker', 'Bruno_BE', 'pixelpanzer', 'Klapka', 'SilentTrack', 'Hullbreaker', 'NoobTube', 'Zwiebel']
FLAG_SETS = [['PL'], ['FR'], ['DE'], ['GB'], ['CZ'], ['SE'], ['DE', 'PL'], ['NL'], ['ES'], ['DE'], ['CZ'], ['GB'],
             [], ['FR', 'BE'], ['UA'], ['HU'], ['IT'], ['BE', 'NL']]

PAGE = '''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="common.css">
<style>%s</style></head><body>%s</body></html>'''

CAPTION = '<div class="caption"><img src="assets/icon.svg">%s<small>%s</small></div>'


def color(value):
    for top, hex_color in WNX_BANDS:
        if top is None or value < top:
            return hex_color


def badge(value):
    # Grouped by thousands with a thin space, like the badges the client draws.
    text = '{:,}'.format(value).replace(',', ' ')
    return '<span class="b" style="background:%s">%s</span>' % (color(value), text)


def flags(codes):
    return '<span class="fl">%s</span>' % ''.join(
        '<span class="f"><img src="assets/flags/%s.svg"></span>' % code for code in codes)


def team(names, rng):
    rows = []
    for index, name in enumerate(names):
        rating = int(rng.triangular(350, 3100, 1300))
        tank = TANKS[(index * 5 + len(name)) % len(TANKS)]
        rows.append((name, rating, FLAG_SETS[(index * 3 + len(name)) % len(FLAG_SETS)], tank))
    return rows


def average(rows):
    return int(round(sum(row[1] for row in rows) / float(len(rows))))


def players_page():
    rng = random.Random(7)
    left, right = team(NAMES_LEFT, rng), team(NAMES_RIGHT, rng)
    css = '''
.dim { position:absolute; inset:0; background:rgba(8,10,12,.74); }
.head { position:absolute; top:74px; left:0; right:0; display:flex; justify-content:center; gap:210px; font-size:17px; font-weight:700; letter-spacing:.3px; }
.head .l { color:#8fd86a; } .head .r { color:#ff6a5a; }
.head span.avg { font-weight:400; color:#d9d4c6; margin-left:8px; font-size:14px; }
.teams { position:absolute; top:108px; left:50%; transform:translateX(-50%); display:flex; gap:26px; }
.t { width:420px; }
.row { display:flex; align-items:center; height:24px; border-bottom:1px solid rgba(255,255,255,.05); font-size:12.5px; }
.row:nth-child(odd) { background:rgba(255,255,255,.035); }
.name { width:118px; color:#e9e4d6; overflow:hidden; white-space:nowrap; }
.tank { flex:1; color:#c9c3b3; white-space:nowrap; overflow:hidden; }
.ic { width:58px; height:20px; display:flex; align-items:center; justify-content:center; }
.ic img { height:20px; }
.col-b { width:44px; display:flex; } .col-f { width:40px; display:flex; }
.l .name { padding-left:10px; } .l .tank { text-align:right; padding-right:6px; } .l .col-b { justify-content:flex-start; padding-left:6px; }
.r .name { text-align:right; padding-right:10px; } .r .tank { padding-left:6px; } .r .col-b { justify-content:flex-end; padding-right:6px; } .r .col-f { justify-content:flex-end; }
.r .ic img { transform:scaleX(-1); }
.l .row.me .name { color:#ffd27a; }
'''

    def left_row(row, me=False):
        name, rating, codes, (tank, contour) = row
        return ('<div class="row%s"><div class="name">%s</div><div class="tank">%s</div>'
                '<div class="ic"><img src="assets/contour/%s.png"></div>'
                '<div class="col-b">%s</div><div class="col-f">%s</div></div>') % (
            ' me' if me else '', name, tank, contour, badge(rating), flags(codes))

    def right_row(row):
        name, rating, codes, (tank, contour) = row
        return ('<div class="row"><div class="col-f">%s</div><div class="col-b">%s</div>'
                '<div class="ic"><img src="assets/contour/%s.png"></div>'
                '<div class="tank">%s</div><div class="name">%s</div></div>') % (
            flags(codes), badge(rating), contour, tank, name)

    body = '<div class="bg" style="background-image:url(assets/ruinberg.jpg)"></div><div class="dim"></div>'
    body += CAPTION % ('Players panel and Tab screen', 'rating &middot; languages &middot; team average')
    body += ('<div class="head"><div class="l">TEAM 1<span class="avg">&Oslash; %s</span></div>'
             '<div class="r">TEAM 2<span class="avg">&Oslash; %s</span></div></div>') % (
        badge(average(left)), badge(average(right)))
    body += '<div class="teams"><div class="t l">%s</div><div class="t r">%s</div></div>' % (
        ''.join(left_row(row, index == 4) for index, row in enumerate(left)), ''.join(right_row(row) for row in right))
    return PAGE % (css, body)


def markers_page():
    css = '''
.m { position:absolute; transform:translateX(-50%); text-align:center; text-shadow:0 0 3px #000, 0 0 2px #000; white-space:nowrap; }
.m .top { display:flex; align-items:center; justify-content:center; gap:4px; font-size:13px; font-weight:700; }
.m .veh { font-size:11.5px; color:#e9e4d6; margin-top:1px; }
.m .hp { width:86px; height:6px; margin:3px auto 0; background:rgba(0,0,0,.6); border:1px solid rgba(0,0,0,.8); }
.m .hp i { display:block; height:100%; }
.ally .name { color:#9df06f; } .ally .hp i { background:#6fcf3f; }
.enemy .name { color:#ff6b5b; } .enemy .hp i { background:#e3412f; }
.alt { position:absolute; right:24px; top:20px; background:rgba(10,10,10,.72); border:1px solid rgba(255,255,255,.12); border-radius:8px; padding:7px 12px; font-size:12px; color:#cfc9ba; }
.alt b { display:inline-block; border:1px solid rgba(255,255,255,.35); border-radius:4px; padding:0 5px; margin:0 3px; color:#fff; font-weight:500; }
'''
    # (x, y, side, name, rating, flags, vehicle, health %)
    marks = [(250, 250, 'ally', 'Kretek_PL', 1934, ['PL'], 'Obj. 140', 82),
             (455, 214, 'ally', 'vbd_Tomas', 2716, ['CZ'], 'TVP T 50/51', 46),
             (640, 262, 'enemy', 'TigerLily', 1203, ['DE', 'PL'], 'E 100', 91),
             (800, 205, 'enemy', 'HEATseeker', 3044, ['SE'], 'Strv 103B', 63),
             (135, 335, 'ally', 'LaBaguette', 1488, ['FR'], 'Bat.-Châtillon 25 t', 100)]
    body = '<div class="bg" style="background-image:url(assets/himmelsdorf.jpg)"></div>'
    body += CAPTION % ('Above the vehicles', 'rating and languages by each name')
    body += '<div class="alt">Always, or only while holding <b>Alt</b></div>'
    for x, y, side, name, rating, codes, vehicle, health in marks:
        body += ('<div class="m %s" style="left:%dpx;top:%dpx"><div class="top">%s%s<span class="name">%s</span></div>'
                 '<div class="veh">%s</div><div class="hp"><i style="width:%d%%"></i></div></div>') % (
            side, x, y, badge(rating), flags(codes), name, vehicle, health)
    return PAGE % (css, body)


def chat_page():
    css = '''
.dim { position:absolute; inset:0; background:linear-gradient(90deg, rgba(0,0,0,.55), rgba(0,0,0,.05) 60%); }
.chat { position:absolute; left:22px; bottom:26px; width:430px; font-size:13px; line-height:19px; text-shadow:0 0 3px #000, 0 0 2px #000; }
.ln { display:flex; align-items:center; gap:4px; white-space:nowrap; }
.ln img { width:14px; height:14px; }
.g { color:#9df06f; } .w { color:#fff; }
.input { margin-top:6px; height:26px; display:flex; align-items:center; padding:0 8px; background:rgba(0,0,0,.55); border:1px solid rgba(255,255,255,.18); font-size:13px; text-shadow:none; }
.input .rcv { color:#9146FF; font-weight:700; margin-right:6px; }
.input .caret { display:inline-block; width:1px; height:15px; background:#fff; margin-left:1px; }
.hint { position:absolute; left:22px; bottom:218px; background:rgba(10,10,10,.72); border:1px solid rgba(255,255,255,.12); border-radius:8px; padding:7px 12px; font-size:12px; color:#cfc9ba; }
.hint b { display:inline-block; border:1px solid rgba(255,255,255,.35); border-radius:4px; padding:0 5px; margin:0 2px; color:#fff; font-weight:500; }
'''

    def ally(name, vehicle, text):
        return '<span class="g">%s (%s):</span> <span class="w">%s</span>' % (name, vehicle, text)

    def twitch(badge_name, name, name_color, text):
        # One span for name and text, or the row's gap would part the colon from the name.
        return ('<img src="assets/twitch.svg"><img src="assets/tw/%s.png">'
                '<span><span style="color:%s">%s</span><span class="w">: %s</span></span>') % (
            badge_name, name_color, name, text)

    lines = [
        ally('Kretek_PL', 'Obj. 140', 'push the left flank with me'),
        twitch('premium.1', 'KappaTanker', '#1E90FF', 'the arty on the right is a 3k player, careful'),
        twitch('moderator.1', 'ModBot', '#00C853', 'mod link on the stream panel'),
        ally('vbd_Tomas', 'TVP T 50/51', 'spotted 2 at the church'),
        twitch('vip.1', 'frau_panzer', '#FF69B4', 'gl Winnie!'),
        twitch('broadcaster.1', 'Winnie', '#9146FF', 'thanks chat, going in'),
        twitch('turbo.1', 'ohmygun', '#FFB300', '1v3 incoming'),
    ]
    body = '<div class="bg" style="background-image:url(assets/himmelsdorf.jpg)"></div><div class="dim"></div>'
    body += CAPTION % ('Your Twitch chat in battle', 'read it, and write in it with TO TWITCH')
    body += '<div class="hint">Switch the chat to <b>TO TWITCH</b> with <b>Tab</b>, or start with <b>!t</b></div>'
    body += ('<div class="chat">%s<div class="input"><span class="rcv">TO TWITCH :</span>'
             '<span class="w">gg, back in two minutes</span><span class="caret"></span></div></div>') % (
        ''.join('<div class="ln">%s</div>' % line for line in lines))
    return PAGE % (css, body)


def cover_page():
    css = '''
html, body { width:600px; height:338px; }
.dim { position:absolute; inset:0; background:linear-gradient(90deg, rgba(8,8,10,.92) 0%, rgba(8,8,10,.75) 55%, rgba(8,8,10,.35) 100%); }
.wrap { position:absolute; left:40px; top:58px; }
.logo { display:flex; align-items:center; gap:14px; }
.logo img { width:58px; height:58px; }
.logo h1 { font-size:46px; font-weight:700; letter-spacing:.2px; color:#fff; }
.tag { margin-top:14px; font-size:19px; color:#e9e4d6; font-weight:500; }
.sub { margin-top:4px; font-size:14px; color:#a9a496; }
.demo { margin-top:24px; display:flex; flex-direction:column; gap:7px; font-size:14px; }
.demo .ln { display:flex; align-items:center; gap:6px; color:#e9e4d6; }
.demo .b { height:15px; line-height:15px; font-size:11.5px; padding:0 4px; }
.demo .f, .demo .f img { width:20px; height:15px; }
.demo img.tw { width:16px; height:16px; }
'''
    body = '<div class="bg" style="background-image:url(assets/garage_dim.jpg)"></div><div class="dim"></div><div class="wrap">'
    body += '<div class="logo"><img src="assets/icon.svg"><h1>unicum.gg</h1></div>'
    body += '<div class="tag">Ratings, languages and your Twitch chat in World of Tanks</div>'
    body += '<div class="sub">In battle and in the garage, straight from unicum.gg</div>'
    body += '<div class="demo"><div class="ln">%s%s<span>Kretek_PL</span></div><div class="ln">%s%s<span>vbd_Tomas</span></div>' % (
        badge(1934), flags(['PL']), badge(2716), flags(['CZ', 'DE']))
    body += ('<div class="ln"><img class="tw" src="assets/twitch.svg"><span><span style="color:#9146FF">Winnie</span>'
             '<span>: thanks chat, going in</span></span></div></div></div>')
    return PAGE % (css, body)


def garage_cards_page():
    css = '''
.dim { position:absolute; inset:0; background:rgba(0,0,0,.35); }
.shot { position:absolute; right:60px; top:10px; height:520px; border:1px solid rgba(255,255,255,.1); }
.txt { position:absolute; left:54px; top:120px; width:420px; }
.txt h2 { font-size:30px; color:#fff; font-weight:700; }
.txt p { margin-top:12px; font-size:15.5px; line-height:23px; color:#d9d4c6; }
.txt li { margin-top:8px; font-size:15px; color:#e9e4d6; list-style:none; padding-left:16px; position:relative; }
.txt li:before { content:''; position:absolute; left:0; top:8px; width:6px; height:6px; border-radius:2px; background:#F25322; }
'''
    body = '<div class="bg" style="background-image:url(assets/garage_dim.jpg)"></div><div class="dim"></div>'
    body += '<div class="txt"><h2>In the garage</h2><p>Your unicum.gg account and your Twitch chat, under the mission cards.</p><ul>'
    body += '<li>Connect in your browser with your Wargaming sign-in</li><li>Write in your chat without leaving the game</li>'
    body += '<li>Move, fold or close the panel</li></ul></div>'
    body += '<img class="shot" src="assets/garage_cards.png">'
    return PAGE % (css, body)


# name -> (page, CSS viewport width, height); captured at a device pixel ratio of 2.
PAGES = {
    'cover': (cover_page, 600, 338),
    '2-garage-cards': (garage_cards_page, 960, 540),
    '3-battle-players': (players_page, 960, 540),
    '4-battle-markers': (markers_page, 960, 540),
    '5-battle-twitch-chat': (chat_page, 960, 540),
}
