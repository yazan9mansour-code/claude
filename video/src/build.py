"""Build the full video: timeline, captions/motion-graphics (ASS), audio mix, frames.

usage: python build.py WORKDIR [--preview t1,t2,...] [--only-audio] [--only-ass]
WORKDIR must contain: img/NNN.jpg, vo.mp3, timed.json, sfx/*.wav
"""
import json
import math
import os
import re
import subprocess
import sys
from multiprocessing import Pool

import cv2
import numpy as np
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, '..', 'assets', 'fonts')
W, H, FPS = 1920, 1080, 30
SRC_K = 1.22  # source supersampling relative to output
SW, SH = int(W * SRC_K), int(H * SRC_K)

WORK = sys.argv[1]
ARGS = sys.argv[2:]

# ---------------------------------------------------------------- data
D = json.load(open(os.path.join(WORK, 'timed.json'), encoding='utf-8'))
WORDS = D['words']
VO_DUR = float(subprocess.check_output(
    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
     os.path.join(WORK, 'vo.mp3')]).strip())
TAIL = 6.5
TOTAL = VO_DUR + TAIL
NFRAMES = int(TOTAL * FPS)


def norm(s):
    s = re.sub(r'[ً-ْٰـ]', '', s)
    s = s.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ى', 'ي').replace('ة', 'ه')
    return re.sub(r'[^ء-يﷺ]', '', s)


NW = [norm(w['text']) for w in WORDS]


def find(phrase, after=0.0):
    """Return (i, j) word index span of phrase (first match starting after time)."""
    p = [norm(x) for x in phrase.split() if norm(x)]
    for i in range(len(WORDS)):
        if WORDS[i]['start'] < after:
            continue
        k, j = 0, i
        while j < len(WORDS) and k < len(p):
            if not NW[j]:
                j += 1
                continue
            if NW[j] != p[k]:
                break
            k += 1
            j += 1
        if k == len(p):
            return i, j - 1
    raise ValueError('phrase not found: ' + phrase)


# ---------------------------------------------------------------- scenes
sfx_at = {}
for s in D['sfx']:
    sfx_at.setdefault(s['w'], []).append(s['name'])

SCENES = []
for k, sc in enumerate(D['scenes']):
    w = sc['w']
    t = 0.0 if k == 0 else WORDS[min(w, len(WORDS) - 1)]['start'] - 0.12
    names = sfx_at.get(w, [])
    if k == 0:
        tr = 'fadein'
    elif 'title' in names:
        tr = 'dip'
    elif any(n in names for n in ('boom', 'impact', 'hit')):
        tr = 'flash'
    elif 'whoosh' in names:
        tr = 'whip'
    else:
        tr = 'fade'
    SCENES.append({'img': sc['img'], 't': t, 'tr': tr})
for k, sc in enumerate(SCENES):
    sc['end'] = SCENES[k + 1]['t'] if k + 1 < len(SCENES) else TOTAL

TR_HALF = {'fade': 0.35, 'whip': 0.22, 'dip': 0.45, 'flash': 0.0, 'fadein': 0.0}

MOTIONS = ['in', 'out', 'pan_l', 'pan_r', 'in_l', 'in_r', 'up', 'out_r', 'down', 'out_l']
rng = np.random.default_rng(42)
prev = None
for sc in SCENES:
    if sc['tr'] == 'flash':
        m = 'punch'
    else:
        choices = [m for m in MOTIONS if m != prev]
        m = choices[rng.integers(len(choices))]
    sc['motion'] = m
    prev = m


def motion_params(m, p):
    """Return zoom, pan_x, pan_y (pan in [-1,1] of available margin) at eased progress p."""
    e = 0.5 - 0.5 * math.cos(math.pi * p)  # ease in-out
    if m == 'in':
        return 1.0 + 0.13 * e, 0, 0
    if m == 'out':
        return 1.14 - 0.13 * e, 0, 0
    if m == 'pan_l':
        return 1.14, 0.8 - 1.6 * e, 0
    if m == 'pan_r':
        return 1.14, -0.8 + 1.6 * e, 0
    if m == 'in_l':
        return 1.02 + 0.14 * e, 0.6 * e, -0.2 * e
    if m == 'in_r':
        return 1.02 + 0.14 * e, -0.6 * e, -0.2 * e
    if m == 'out_r':
        return 1.16 - 0.12 * e, 0.5 - 0.9 * e, 0
    if m == 'out_l':
        return 1.16 - 0.12 * e, -0.5 + 0.9 * e, 0
    if m == 'up':
        return 1.14, 0, 0.7 - 1.4 * e
    if m == 'down':
        return 1.14, 0, -0.7 + 1.4 * e
    if m == 'punch':
        q = 1 - (1 - min(p * 4, 1)) ** 3  # fast ease-out
        return 1.18 - 0.1 * q - 0.04 * e, 0, 0
    return 1.0, 0, 0


# ---------------------------------------------------------------- cards
GOLD = '&H4EC1F2&'      # #F2C14E
GOLD_D = '&H1F6FA8&'    # dark gold
WHITE = '&HFFFFFF&'
RED = '&H2A2ACC&'


def card(kind, phrase, after=0.0, **kw):
    i, j = find(phrase, after)
    c = {'kind': kind, 'i': i, 'j': j, 't0': WORDS[i]['start'] - 0.1, 't1': WORDS[j]['end']}
    c.update(kw)
    return c


CARDS = [
    card('center', 'وهنا في سِفر الخالدين', title='سِفر الخالدين', sub='حمزة ووحشي · حكاية حربة',
         font='Aref Ruqaa', size=150, hold=5.6, keepcap=True, sfx='page'),
    card('loc', 'بلاد الشام', title='حِمص · بلاد الشام', sub='بعد غزوة أُحد بسنوات', hold=5.0),
    card('lower', 'عبيد الله بن عدي بن الخيار', title='عبيد الله بن عدي بن الخيار', sub='ومعه جعفر بن عمرو الضمري', hold=6.5),
    card('center', 'وحشي بن حرب', after=150, title='وحشي بن حرب', sub='الرجل الذي قتل حمزة', hold=4.2),
    card('loc', 'إلى مكة', after=155, title='مكة المكرمة', sub='قبل الهجرة', hold=4.5),
    card('lower', 'جبير بن مطعم', title='جبير بن مطعم', sub='من سادة قريش · سيّد وحشي', hold=5.5),
    card('loc', 'ثم جاءت بدر', title='غزوة بدر الكبرى', sub='رمضان · ٢ هـ', hold=4.5),
    card('quote', 'إن قتلت حمزة بعمّي فأنت حر', attr='جبير بن مطعم لعبده وحشي'),
    card('center', 'حمزة بن عبد المطلب', after=200, title='حمزة بن عبد المطلب', sub='أسد الله وأسد رسوله', hold=4.6),
    card('lower', 'أن أبا جهل', title='أبو جهل', sub='عمرو بن هشام المخزومي', hold=5.0),
    card('quote', 'أتشتمه وأنا على دينه؟ أقول ما يقول', attr='حمزة بن عبد المطلب'),
    card('quran', 'هَٰذَانِ خَصْمَانِ اخْتَصَمُوا فِي رَبِّهِمْ', attr='سورة الحج · الآية ١٩'),
    card('loc', 'السنة الثالثة للهجرة', title='غزوة أُحد', sub='شوّال · ٣ هـ', hold=5.0),
    card('quote', 'فكان ذاك العهد به', attr='وحشي بن حرب'),
    card('quote', 'لولا أن تجد صفية في نفسها لتركته حتى تأكله العافية', attr='رسول الله صلى الله عليه وسلم'),
    card('lower', 'وجاءت صفية فعلًا', title='صفية بنت عبد المطلب', sub='أخت حمزة وعمّة رسول الله', hold=5.5),
    card('lower', 'ابنها الزبير', title='الزبير بن العوّام', sub='ابن صفية', hold=4.5),
    card('quote', 'هذان ثوبان جئت بهما لأخي حمزة', attr='صفية بنت عبد المطلب'),
    card('center', 'سيد الشهداء حمزة بن عبد المطلب', after=540, title='سيّد الشهداء', sub='حمزة بن عبد المطلب', hold=5.0),
    card('loc', 'إلى الطائف', after=560, title='الطائف', sub='', hold=4.0),
    card('quote', 'فهل تستطيع أن تغيّب وجهك عني؟', attr='رسول الله صلى الله عليه وسلم لوحشي'),
    card('center', 'كيف يُمحى دمٌ كهذا؟', title='كيف يُمحى دمٌ كهذا؟', sub='', size=104, hold=3.6),
    card('subscribe', 'فاشتراكك', hold=8.0),
    card('lower', 'وخرج مسيلمة الكذاب', title='مسيلمة الكذّاب', sub='مدّعي النبوّة في اليمامة', hold=5.0),
    card('loc', 'خرج مع جيش المسلمين إلى اليمامة', title='معركة اليمامة', sub='١١ هـ', hold=4.5),
    card('quote', 'إن كنت قتلت خير الناس، فقد قتلت شر الناس', attr='وحشي بن حرب'),
    card('loc', 'ونعود إلى حمص', title='حِمص', sub='', hold=4.0),
    card('center', 'سيد الشهداء، رضي الله عنه', after=740, title='سيّد الشهداء', sub='رضي الله عنه', hold=4.0),
    card('center', 'جناحان', after=760, title='جناحان', sub='', size=170, hold=2.4),
]
for c in CARDS:
    if c['kind'] in ('quote', 'quran'):
        c['end'] = c['t1'] + 1.6
    else:
        c['end'] = c['t0'] + c.get('hold', 4.0)
END_SLATE = (max(VO_DUR + 0.6, CARDS[-1]['end'] + 0.1), TOTAL)

# caption suppression and background focus windows
SUPPRESS = [(c['i'], c['j']) for c in CARDS
            if c['kind'] in ('quote', 'quran') or (c['kind'] == 'center' and not c.get('keepcap'))]
FOCUS = [(c['t0'], c['end']) for c in CARDS if c['kind'] in ('quote', 'quran', 'center')]
FOCUS.append(END_SLATE)


# ---------------------------------------------------------------- ASS
def at(t):
    t = max(t, 0)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f'{h}:{m:02d}:{s:05.2f}'


def pbuh(text, base):
    """Render ﷺ with Amiri. libass lays out override runs left-to-right, so runs are
    emitted in reverse (visual) order for right-to-left text."""
    if 'ﷺ' not in text:
        return text
    runs = []
    for k, part in enumerate(text.split('ﷺ')):
        if k:
            runs.append('{\\fnAmiri}ﷺ')
        if part.strip():
            runs.append('{\\fn' + base + '}' + part.strip())
    return ' '.join(reversed(runs))


HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Cairo Black,60,&H00FFFFFF,&H00FFFFFF,&H30000000,&H90000000,0,0,0,0,100,100,0,0,1,3.4,2.2,2,120,120,58,1
Style: Card,Reem Kufi,120,&H00FFFFFF,&H00FFFFFF,&H40000000,&H80000000,0,0,0,0,100,100,0,0,1,2,3,5,0,0,0,1
Style: Quote,Amiri,80,&H00FFFFFF,&H00FFFFFF,&H50000000,&H90000000,1,0,0,0,100,100,0,0,1,2,3,5,230,230,0,1
Style: Small,Tajawal ExtraBold,40,&H00FFFFFF,&H00FFFFFF,&H50000000,&H90000000,0,0,0,0,100,100,0,0,1,2,2,5,0,0,0,1
Style: Shape,Cairo,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ev(layer, t0, t1, style, text):
    return f'Dialogue: {layer},{at(t0)},{at(t1)},{style},,0,0,0,,{text}'


def hline(cx, y, half, t0, t1, delay=0, grow=700, color=GOLD, thick=3, layer=2):
    return ev(layer, t0, t1, 'Shape',
              f'{{\\an5\\pos({cx},{y})\\p1\\bord0\\shad0\\c{color}\\fscx0\\t({delay},{delay + grow},0.5,\\fscx100)'
              f'\\fad(0,400)}}m {-half} 0 l {half} 0 l {half} {thick} l {-half} {thick}{{\\p0}}')


def diamond(cx, y, t0, t1, delay=0, r=9, color=GOLD, layer=2):
    return ev(layer, t0, t1, 'Shape',
              f'{{\\an5\\pos({cx},{y})\\p1\\bord0\\shad0\\c{color}\\fscx0\\fscy0\\frz0'
              f'\\t({delay},{delay + 500},0.6,\\fscx100\\fscy100\\frz360)\\fad(0,400)}}'
              f'm 0 {-r} l {r} 0 l 0 {r} l {-r} 0{{\\p0}}')


def ass_center(c):
    t0, t1 = c['t0'], c['end']
    font = c.get('font', 'Reem Kufi')
    size = c.get('size', 124)
    y = 470 if c.get('sub') else 520
    title = c['title']
    out = []
    base = (f'\\an5\\pos(960,{y})\\fn{font}\\fs{size}\\fad(350,500)\\fscx118\\fscy118'
            f'\\t(0,900,0.4,\\fscx100\\fscy100)')
    # glow layer
    out.append(ev(1, t0, t1, 'Card', f'{{{base}\\c{GOLD}\\3c{GOLD_D}\\bord6\\blur18\\alpha&H70&\\shad0}}' + pbuh(title, font)))
    out.append(ev(2, t0, t1, 'Card', f'{{{base}\\c{GOLD}\\3c&H101010&\\bord2.5\\shad3\\blur12\\t(0,700,\\blur0.6)}}' + pbuh(title, font)))
    ly = y + size // 2 + 30
    out.append(hline(960, ly, 330, t0, t1, delay=250, grow=800))
    out.append(diamond(960, ly + 1, t0, t1, delay=500))
    if c.get('sub'):
        out.append(ev(2, t0, t1, 'Small',
                      f'{{\\an5\\pos(960,{ly + 52})\\fs44\\c{WHITE}\\alpha&HFF&\\t(550,1000,\\alpha&H10&)\\fad(0,450)\\blur0.6}}'
                      + pbuh(c['sub'], 'Tajawal ExtraBold')))
    return out


def ass_loc(c):
    t0, t1 = c['t0'], c['end']
    out = [diamond(960, 78, t0, t1, delay=0, r=7)]
    out.append(hline(960 - 250, 79, 120, t0, t1, delay=150, grow=600, thick=2))
    out.append(hline(960 + 250, 79, 120, t0, t1, delay=150, grow=600, thick=2))
    out.append(ev(2, t0, t1, 'Small',
                  f'{{\\an5\\pos(960,128)\\fs50\\c{WHITE}\\fad(450,500)\\blur10\\t(0,500,\\blur0.6)'
                  f'\\move(960,146,960,128,0,600)}}' + c['title']))
    if c.get('sub'):
        out.append(ev(2, t0, t1, 'Small',
                      f'{{\\an5\\pos(960,182)\\fs32\\c{GOLD}\\alpha&HFF&\\t(400,900,\\alpha&H00&)\\fad(0,500)}}' + c['sub']))
    return out


def ass_lower(c):
    t0, t1 = c['t0'], c['end']
    x, y = 1830, 96
    tw = max(len(c['title']) * 34, len(c['sub']) * 20) + 80
    out = []
    # soft dark backdrop
    out.append(ev(0, t0, t1, 'Shape',
                  f'{{\\an7\\pos({x - tw},{y - 22})\\p1\\bord0\\shad0\\c&H000000&\\alpha&H70&\\blur28\\fad(400,500)}}'
                  f'm 0 0 l {tw + 60} 0 l {tw + 60} 160 l 0 160{{\\p0}}'))
    out.append(ev(2, t0, t1, 'Shape',
                  f'{{\\an7\\pos({x + 22},{y - 6})\\p1\\bord0\\shad0\\c{GOLD}\\fscy0\\t(0,400,0.5,\\fscy100)\\fad(0,400)}}'
                  f'm 0 0 l 7 0 l 7 128 l 0 128{{\\p0}}'))
    clip0 = f'\\clip({x - 5},0,{x + 15},1080)\\t(120,800,0.6,\\clip({x - tw - 40},0,{x + 15},1080))'
    out.append(ev(2, t0, t1, 'Card',
                  f'{{\\an9\\pos({x},{y})\\fnReem Kufi\\fs62\\c{GOLD}\\bord2\\shad2{clip0}\\fad(0,450)}}' + c['title']))
    out.append(ev(2, t0, t1, 'Small',
                  f'{{\\an9\\pos({x},{y + 80})\\fs34\\c{WHITE}\\alpha&HFF&\\t(450,900,\\alpha&H10&)\\fad(0,450)}}'
                  + pbuh(c['sub'], 'Tajawal ExtraBold')))
    return out


def ass_quote(c, quran=False):
    t0, t1 = c['t0'], c['end']
    words = WORDS[c['i']: c['j'] + 1]
    parts = []
    for w in words:
        txt = w['text'].replace('*', '').replace('﴿', '').replace('﴾', '')
        txt = txt.rstrip('.')
        ws = int((w['start'] - t0) * 1000)
        parts.append(f'{{\\alpha&HE0&\\t({max(ws - 60, 0)},{ws + 260},\\alpha&H00&)}}' + txt)
    parts.reverse()  # visual order for libass
    if quran:
        body = (f'{{\\c{GOLD}\\alpha&H00&}}\uFD3E{{\\c{WHITE}}} ' + ' '.join(parts)
                + f' {{\\c{GOLD}\\alpha&H00&}}\uFD3F')
        style_tag = f'\\fnAmiri\\fs165\\c{WHITE}'
    else:
        body = ' '.join(parts)
        style_tag = f'\\fs150\\c{WHITE}'
    half = 70
    out = [ev(2, t0, t1, 'Quote', f'{{{style_tag}\\fad(250,500)\\blur0.6}}' + body)]
    ytop, ybot = 540 - half - 50, 540 + half + 40
    out.append(diamond(960, ytop, t0, t1, delay=0, r=8))
    out.append(hline(960 - 200, ytop + 1, 150, t0, t1, delay=100, grow=700, thick=2))
    out.append(hline(960 + 200, ytop + 1, 150, t0, t1, delay=100, grow=700, thick=2))
    out.append(ev(2, t0, t1, 'Small',
                  f'{{\\an5\\pos(960,{ybot + 30})\\fs40\\c{GOLD}\\alpha&HFF&\\t(500,1000,\\alpha&H00&)\\fad(0,500)}}— '
                  + pbuh(c['attr'], 'Tajawal ExtraBold') + ' —'))
    return out


def ass_subscribe(c):
    t0 = c['t0']
    t1 = t0 + c.get('hold', 8.0)
    click = 2.6
    cx, cy = 960, 800
    out = []
    pill = 'm 46 0 l 414 0 b 439.4 0 460 20.6 460 46 b 460 71.4 439.4 92 414 92 l 46 92 b 20.6 92 0 71.4 0 46 b 0 20.6 20.6 0 46 0'
    pop = '\\fscx0\\fscy0\\t(0,280,\\fscx112\\fscy112)\\t(280,420,\\fscx100\\fscy100)'
    press = f'\\t({int(click * 1000)},{int(click * 1000) + 90},\\fscx92\\fscy92)\\t({int(click * 1000) + 90},{int(click * 1000) + 220},\\fscx100\\fscy100)'
    out.append(ev(1, t0, t1, 'Shape',
                  f'{{\\an5\\pos({cx},{cy})\\p1\\bord0\\shad0\\c{RED}{pop}{press}'
                  f'\\t({int(click * 1000)},{int(click * 1000) + 150},\\c&H3A3A3A&)\\fad(0,400)}}{pill}{{\\p0}}'))
    out.append(ev(0, t0, t1, 'Shape',
                  f'{{\\an5\\pos({cx},{cy + 6})\\p1\\bord0\\shad0\\c&H000000&\\alpha&H60&\\blur16{pop}\\fad(0,400)}}{pill}{{\\p0}}'))
    t_click = t0 + click
    out.append(ev(2, t0, t_click + 0.05, 'Card',
                  f'{{\\an5\\pos({cx},{cy - 4})\\fnCairo Black\\fs64\\bord0\\shad0\\c{WHITE}{pop}{press}}}اشترك الآن'))
    out.append(ev(2, t_click + 0.05, t1, 'Card',
                  f'{{\\an5\\pos({cx},{cy - 4})\\fnCairo Black\\fs58\\bord0\\shad0\\c&HDDDDDD&\\fad(80,400)}}✓ تم الاشتراك'
                  .replace('✓ ', '')))
    # ripple at click
    out.append(ev(3, t_click, t_click + 0.7, 'Shape',
                  f'{{\\an5\\pos({cx + 120},{cy + 10})\\p1\\bord3\\3c{WHITE}\\c{WHITE}\\1a&HFF&\\shad0\\fscx20\\fscy20'
                  f'\\t(0,600,\\fscx260\\fscy260\\3a&HFF&)}}m 0 -20 b 27 -20 27 20 0 20 b -27 20 -27 -20 0 -20{{\\p0}}'))
    # cursor
    cursor = 'm 0 0 l 0 44 l 11 33 l 19 52 l 26 49 l 18 31 l 33 31'
    out.append(ev(4, t0 + 0.9, t1, 'Shape',
                  f'{{\\an7\\move({cx + 420},{cy + 200},{cx + 110},{cy + 2},0,{int((click - 0.9) * 1000) - 150})'
                  f'\\p1\\c{WHITE}\\bord2\\3c&H000000&\\shad2\\fad(200,400)'
                  f'\\t({int((click - 0.9) * 1000)},{int((click - 0.9) * 1000) + 100},\\fscx85\\fscy85)'
                  f'\\t({int((click - 0.9) * 1000) + 100},{int((click - 0.9) * 1000) + 220},\\fscx100\\fscy100)}}{cursor}{{\\p0}}'))
    out.append(ev(2, t0 + 0.3, t1, 'Small',
                  f'{{\\an5\\pos({cx},{cy - 92})\\fs44\\c{GOLD}\\alpha&HFF&\\t(0,400,\\alpha&H00&)\\fad(0,400)}}'
                  f'اشترك في سِفر الخالدين وفعّل الجرس'))
    c['click_t'] = t_click
    return out


def ass_end_slate():
    t0, t1 = END_SLATE
    c = {'t0': t0, 'end': t1, 'title': 'سِفر الخالدين', 'sub': 'الحكاية القادمة: جعفر بن أبي طالب · ذو الجناحين',
         'font': 'Aref Ruqaa', 'size': 150}
    return ass_center(c)


def caption_chunks():
    sup = set()
    for i, j in SUPPRESS:
        sup.update(range(i, j + 1))
    chunks, cur = [], []
    for k, w in enumerate(WORDS):
        if k in sup or not norm(w['text']):
            if cur and k in sup:
                chunks.append(cur)
                cur = []
            continue
        if cur:
            prev = WORDS[cur[-1]]
            chars = sum(len(WORDS[x]['text']) + 1 for x in cur)
            if (len(cur) >= 6 or chars + len(w['text']) > 36 or w['start'] - prev['end'] > 0.55):
                chunks.append(cur)
                cur = []
        cur.append(k)
        if re.search(r'[.؟?!]$', w['text']) or (re.search(r'[،:؛]$', w['text']) and len(cur) >= 3):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def ass_captions():
    out = []
    chunks = caption_chunks()
    for n, ch in enumerate(chunks):
        cs = WORDS[ch[0]]['start'] - 0.1
        ce = WORDS[ch[-1]]['end'] + 0.4
        if n + 1 < len(chunks):
            ce = min(ce, WORDS[chunks[n + 1][0]]['start'] - 0.12)
        ce = max(ce, WORDS[ch[-1]]['end'] + 0.05)
        parts = []
        for k in ch:
            w = WORDS[k]
            ws = int((w['start'] - cs) * 1000)
            we = int((w['end'] - cs) * 1000)
            txt = pbuh(w['text'], 'Cairo Black')
            if w['emph']:
                parts.append(f'{{\\c{GOLD}\\fs66\\alpha&H40&\\t({ws},{ws + 70},\\alpha&H00&\\3c{GOLD_D})'
                             f'\\t({we},{we + 150},\\3c&H000000&)}}' + txt)
            else:
                parts.append(f'{{\\c{WHITE}\\fs60\\alpha&H50&\\t({ws},{ws + 70},\\alpha&H00&\\c{GOLD})'
                             f'\\t({we},{we + 150},\\c{WHITE})}}' + txt)
        text = ' '.join(reversed(parts))
        out.append(ev(5, cs, ce, 'Cap', '{\\q2\\fad(120,120)\\move(960,1036,960,1022,0,200)\\an2}' + text))
    return out


def build_ass(path):
    lines = [HEADER]
    for c in CARDS:
        k = c['kind']
        if k == 'center':
            lines += ass_center(c)
        elif k == 'loc':
            lines += ass_loc(c)
        elif k == 'lower':
            lines += ass_lower(c)
        elif k == 'quote':
            lines += ass_quote(c)
        elif k == 'quran':
            lines += ass_quote(c, quran=True)
        elif k == 'subscribe':
            lines += ass_subscribe(c)
    lines += ass_end_slate()
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')


# ---------------------------------------------------------------- audio
def read_wav(p):
    sr, x = wavfile.read(p)
    x = x.astype(np.float32) / 32768.0
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    return x


def db(v):
    return 10 ** (v / 20)


def build_audio(path):
    SR = 48000
    vo_wav = os.path.join(WORK, 'vo48.wav')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', os.path.join(WORK, 'vo.mp3'), '-af',
                    'highpass=f=70,lowpass=f=15000,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120:makeup=2',
                    '-ar', str(SR), '-ac', '2', vo_wav], check=True)
    vo = read_wav(vo_wav)
    # gentle gate between words (removes breaths / throat clears)
    g = np.full(len(vo), db(-11), np.float32)
    for w in WORDS:
        a = int(max(w['start'] - 0.09, 0) * SR)
        b = int((w['end'] + 0.16) * SR)
        g[a:b] = 1.0
    k = int(0.06 * SR)
    g = np.convolve(g, np.ones(k) / k, mode='same').astype(np.float32)
    vo *= g[:, None]

    n = int(TOTAL * SR)
    mix = np.zeros((n, 2), np.float32)
    mix[: len(vo)] += vo[:n]
    fx = {nm: read_wav(os.path.join(WORK, 'sfx', nm + '.wav'))
          for nm in ['whoosh', 'boom', 'impact', 'hit', 'riser', 'rumble', 'chain', 'heartbeat',
                     'battle', 'ding', 'click', 'page']}
    level = {'whoosh': -13, 'boom': -9, 'impact': -10, 'hit': -11, 'riser': -20, 'rumble': -12,
             'chain': -15, 'heartbeat': -11, 'battle': -17, 'ding': -14, 'click': -10, 'page': -12}

    def place(nm, t, gain_db=None):
        x = fx[nm] * db(level[nm] if gain_db is None else gain_db)
        i = int(max(t, 0) * SR)
        m = min(len(x), n - i)
        if m > 0:
            mix[i: i + m] += x[:m]

    scene_t = {sc_w: SCENES[k]['t'] for k, sc_w in enumerate(s['w'] for s in D['scenes'])}
    for s in D['sfx']:
        nm = s['name']
        t = scene_t.get(s['w'], WORDS[min(s['w'], len(WORDS) - 1)]['start'] - 0.05)
        if nm == 'whoosh':
            place('whoosh', t - 0.42)
        elif nm == 'boom':
            place('riser', t - 1.9)
            place('boom', t)
        elif nm in fx:
            place(nm, t)
    # whip transitions without explicit whoosh still get a soft one; fades get a light air swish
    for sc in SCENES:
        if sc['tr'] == 'fade':
            place('whoosh', sc['t'] - 0.42, -27)
    for c in CARDS:
        if c.get('sfx'):
            place(c['sfx'], c['t0'])
        if c['kind'] in ('center', 'quote', 'quran') and c['t0'] > 3:
            place('hit', c['t0'], -21)
        if c['kind'] == 'subscribe':
            place('click', c['click_t'])
            place('ding', c['click_t'] + 0.05)
    place('boom', END_SLATE[0], -14)

    wind = read_wav(os.path.join(WORK, 'sfx', 'wind.wav'))[:n]
    env = np.ones(len(wind), np.float32)
    fi = int(3 * SR)
    env[:fi] = np.linspace(0, 1, fi)
    env[-fi:] = np.linspace(1, 0, fi)
    mix[: len(wind)] += wind * env[:, None] * db(-31)
    fo = int(2.5 * SR)
    mix[-fo:] *= np.linspace(1, 0, fo)[:, None]
    tmp = os.path.join(WORK, 'mix_raw.wav')
    wavfile.write(tmp, SR, (np.clip(mix, -1, 1) * 32767).astype(np.int16))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', tmp, '-af',
                    'loudnorm=I=-14:TP=-1.2:LRA=11', '-ar', str(SR), path], check=True)


# ---------------------------------------------------------------- captions (python, exact RTL layout)
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CAP_FONT = os.path.join(FONTS, 'cairo-arabic-900-normal.ttf')
PBUH_FONT = os.path.join(FONTS, 'amiri-arabic-700-normal.ttf')
CAP_SIZE = 62
CAP_BASE_Y = 1012
CAP_STATES = {'dim': (255, 255, 255), 'on': (255, 255, 255), 'act': (78, 193, 242), 'emph': (78, 193, 242)}
CAPS = None


def _word_sprite(text, color_bgr, font):
    pad = 18
    asc, desc = font.getmetrics()
    w = int(font.getlength(text)) + 2 * pad
    h = asc + desc + 2 * pad
    shadow = Image.new('L', (w, h), 0)
    ImageDraw.Draw(shadow).text((pad + 3, pad + asc + 4), text, font=font, fill=200, anchor='ls',
                                stroke_width=5, stroke_fill=200)
    shadow = shadow.filter(ImageFilter.GaussianBlur(5))
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    img.putalpha(shadow)
    d = ImageDraw.Draw(img)
    rgb = (color_bgr[2], color_bgr[1], color_bgr[0])
    d.text((pad, pad + asc), text, font=font, fill=rgb + (255,), anchor='ls',
           stroke_width=4, stroke_fill=(10, 8, 6, 235))
    a = np.array(img).astype(np.float32)
    bgr = a[:, :, [2, 1, 0]]
    alpha = a[:, :, 3:4] / 255.0
    return bgr, alpha, pad, asc, int(font.getlength(text))


def build_captions():
    global CAPS
    from PIL import features  # noqa
    f_main = ImageFont.truetype(CAP_FONT, CAP_SIZE, layout_engine=ImageFont.Layout.RAQM)
    f_pbuh = ImageFont.truetype(PBUH_FONT, int(CAP_SIZE * 1.05), layout_engine=ImageFont.Layout.RAQM)
    space = f_main.getlength(' ')
    chunks = caption_chunks()
    CAPS = []
    for n, ch in enumerate(chunks):
        cs = WORDS[ch[0]]['start'] - 0.1
        ce = WORDS[ch[-1]]['end'] + 0.4
        if n + 1 < len(chunks):
            ce = min(ce, WORDS[chunks[n + 1][0]]['start'] - 0.12)
        ce = max(ce, WORDS[ch[-1]]['end'] + 0.05)
        items = []
        for k in ch:
            w = WORDS[k]
            font = f_pbuh if 'ﷺ' in w['text'] else f_main
            spr = {}
            for st in ('dim', 'on', 'act'):
                col = CAP_STATES['emph'] if (w['emph'] and st != 'act') else CAP_STATES[st]
                if w['emph'] and st == 'act':
                    col = (150, 230, 255)
                spr[st] = _word_sprite(w['text'], col, font)
            items.append({'w': w, 'spr': spr, 'width': spr['on'][4]})
        total = sum(it['width'] for it in items) + space * (len(items) - 1)
        x = 960 + total / 2  # right edge, words flow right-to-left
        for it in items:
            x -= it['width']
            it['x'] = x
            x -= space
        CAPS.append({'cs': cs, 'ce': ce, 'items': items})


def _blend(frame, bgr, alpha, x, y, opacity):
    h, w = alpha.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0 or opacity <= 0:
        return
    sb = bgr[y0 - y: y1 - y, x0 - x: x1 - x]
    sa = alpha[y0 - y: y1 - y, x0 - x: x1 - x] * opacity
    region = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (region * (1 - sa) + sb * sa).astype(np.uint8)


def draw_captions(frame, t):
    for c in CAPS:
        if not (c['cs'] <= t <= c['ce']):
            continue
        fin = smooth((t - c['cs']) / 0.14)
        fout = smooth((c['ce'] - t) / 0.12)
        op = min(fin, fout)
        rise = int(12 * (1 - fin))
        for it in c['items']:
            w = it['w']
            if t < w['start'] - 0.02:
                st, o = 'dim', 0.55
            elif t <= w['end'] + 0.05:
                st, o = 'act', 1.0
            else:
                st, o = 'on', 1.0
            bgr, alpha, pad, asc, _ = it['spr'][st]
            lift = 3 if st == 'act' else 0
            _blend(frame, bgr, alpha, int(it['x']) - pad, CAP_BASE_Y - asc - pad + rise - lift, op * o)


# ---------------------------------------------------------------- frames
_cache = {}


def src_image(n):
    if n in _cache:
        return _cache[n]
    if len(_cache) > 6:
        _cache.pop(next(iter(_cache)))
    im = cv2.imread(os.path.join(WORK, 'img', f'{n:03d}.jpg'))
    h, w = im.shape[:2]
    s = max(SW / w, SH / h)
    im = cv2.resize(im, (round(w * s), round(h * s)), interpolation=cv2.INTER_LANCZOS4)
    y0 = (im.shape[0] - SH) // 2
    x0 = (im.shape[1] - SW) // 2
    im = im[y0: y0 + SH, x0: x0 + SW]
    blur = cv2.GaussianBlur(im, (0, 0), 1.2)
    im = cv2.addWeighted(im, 1.35, blur, -0.35, 0)
    _cache[n] = im
    return im


def _curve():
    x = np.arange(256) / 255.0
    s = x + 0.10 * np.sin(2 * np.pi * x) * -0.5 * 0 + 0.0
    s = 0.5 + (x - 0.5) * 1.08
    s = np.clip(s, 0, 1)
    s = s + 0.06 * (s - s ** 2) * 0  # placeholder for tweaks
    b = np.clip(s * 0.97 + 0.012, 0, 1)            # cooler shadows / less blue in highlights
    g = np.clip(s, 0, 1)
    r = np.clip(s * 1.02 + 0.004, 0, 1)
    lut = np.stack([b, g, r], 1)
    return (lut * 255).astype(np.uint8).reshape(256, 1, 3)


LUT = _curve()


def _masks():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dx = (xx - W / 2) / (W / 2)
    dy = (yy - H / 2) / (H / 2)
    r = np.sqrt(dx ** 2 * 0.85 + dy ** 2)
    vig = 1 - 0.42 * np.clip((r - 0.55) / 0.85, 0, 1) ** 1.6
    bottom = 1 - 0.38 * np.clip((yy - H * 0.70) / (H * 0.30), 0, 1) ** 1.3
    top = 1 - 0.18 * np.clip((H * 0.18 - yy) / (H * 0.18), 0, 1)
    m = np.clip(vig * bottom * top, 0, 1)
    return (np.dstack([m] * 3) * 255).astype(np.uint8)


MASK = None
GRAIN = None


def init_worker():
    global MASK, GRAIN
    MASK = _masks()
    r = np.random.default_rng(3)
    GRAIN = []
    for _ in range(8):
        g = r.normal(0, 5.5, (H // 2, W // 2)).astype(np.float32)
        g = cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR)
        pos = np.clip(g, 0, 255).astype(np.uint8)
        neg = np.clip(-g, 0, 255).astype(np.uint8)
        GRAIN.append((cv2.merge([pos] * 3), cv2.merge([neg] * 3)))
    build_captions()


PR = np.random.default_rng(11)
PARTICLES = np.column_stack([
    PR.uniform(0, W, 70), PR.uniform(0, H, 70), PR.uniform(-14, 14, 70), PR.uniform(-22, -4, 70),
    PR.uniform(0.8, 2.6, 70), PR.uniform(25, 95, 70), PR.uniform(0, 6.28, 70)])

SHAKES = []
for s in D['sfx']:
    amp = {'impact': 16, 'boom': 11, 'hit': 7}.get(s['name'])
    if amp:
        w = min(s['w'], len(WORDS) - 1)
        SHAKES.append((WORDS[w]['start'] - 0.05, amp))
FLASHES = [(sc['t'], 0.85) for sc in SCENES if sc['tr'] == 'flash']


def scene_frame(k, t):
    sc = SCENES[k]
    h_in = TR_HALF[sc['tr']]
    h_out = TR_HALF[SCENES[k + 1]['tr']] if k + 1 < len(SCENES) else 0
    a, b = sc['t'] - h_in, sc['end'] + h_out
    p = min(max((t - a) / max(b - a, 1e-3), 0), 1)
    z, px, py = motion_params(sc['motion'], p)
    # handheld drift
    dx = 3.0 * math.sin(t * 0.63 + k) + 1.6 * math.sin(t * 1.37 + 2 * k)
    dy = 2.2 * math.sin(t * 0.51 + 3 * k) + 1.2 * math.sin(t * 1.11 + k)
    ang = 0.10 * math.sin(t * 0.37 + k)
    for t0, amp in SHAKES:
        if 0 <= t - t0 < 0.7:
            e = amp * math.exp(-(t - t0) / 0.16)
            dx += e * math.sin((t - t0) * 83)
            dy += e * 0.8 * math.sin((t - t0) * 71 + 1)
    scale = z / SRC_K
    half_w, half_h = W / 2 / scale, H / 2 / scale
    mx, my = max(SW / 2 - half_w, 0), max(SH / 2 - half_h, 0)
    cx, cy = SW / 2 + px * mx, SH / 2 + py * my
    M = cv2.getRotationMatrix2D((cx, cy), ang, scale)
    M[0, 2] += W / 2 - cx + dx
    M[1, 2] += H / 2 - cy + dy
    return cv2.warpAffine(src_image(sc['img']), M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def smooth(x):
    x = min(max(x, 0), 1)
    return x * x * (3 - 2 * x)


def compose(t):
    k = 0
    while k + 1 < len(SCENES) and SCENES[k + 1]['t'] <= t:
        k += 1
    frame = None
    # incoming transition into scene k+1 (before its cut) or into scene k (after its cut)
    for kk in (k, k + 1):
        if kk <= 0 or kk >= len(SCENES):
            continue
        sc = SCENES[kk]
        h = TR_HALF[sc['tr']]
        if h > 0 and sc['t'] - h <= t < sc['t'] + h:
            q = smooth((t - (sc['t'] - h)) / (2 * h))
            A = scene_frame(kk - 1, t)
            B = scene_frame(kk, t)
            if sc['tr'] == 'fade':
                frame = cv2.addWeighted(A, 1 - q, B, q, 0)
            elif sc['tr'] == 'dip':
                frame = (A if q < 0.5 else B)
                frame = cv2.convertScaleAbs(frame, alpha=abs(1 - 2 * q) ** 0.8)
            elif sc['tr'] == 'whip':
                off = int(W * 0.9 * q)
                sh = np.float32([[1, 0, -off], [0, 1, 0]])
                sh2 = np.float32([[1, 0, W * 0.9 - off], [0, 1, 0]])
                A2 = cv2.warpAffine(A, sh, (W, H), borderMode=cv2.BORDER_REFLECT)
                B2 = cv2.warpAffine(B, sh2, (W, H), borderMode=cv2.BORDER_REFLECT)
                edge = max(min(int(W * 0.9 - off + W * 0.05), W), 0)
                frame = A2.copy()
                frame[:, edge:] = B2[:, edge:]
                ksz = int(3 + 140 * math.sin(math.pi * q))
                small = cv2.resize(frame, (W // 2, H // 2))
                small = cv2.blur(small, (max(ksz // 2, 1), 1))
                frame = cv2.resize(small, (W, H))
            break
    if frame is None:
        frame = scene_frame(k, t)

    frame = cv2.LUT(frame, LUT)

    # focus: blur + darken background behind cards
    f = 0.0
    for a, b in FOCUS:
        if a - 0.4 <= t <= b + 0.5:
            f = max(f, smooth((t - (a - 0.4)) / 0.6) * smooth((b + 0.5 - t) / 0.6))
    if f > 0.01:
        small = cv2.resize(frame, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), 1 + 4 * f)
        up = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
        frame = cv2.addWeighted(frame, 1 - 0.85 * f, up, 0.85 * f, 0)
        frame = cv2.convertScaleAbs(frame, alpha=1 - 0.5 * f)

    frame = cv2.multiply(frame, MASK, scale=1 / 255.0)

    # floating dust
    ov = np.zeros((H, W, 3), np.uint8)
    P = PARTICLES
    for x0, y0, vx, vy, r, br, ph in P:
        x = (x0 + vx * t + 18 * math.sin(t * 0.3 + ph)) % W
        y = (y0 + vy * t) % H
        a = br * (0.6 + 0.4 * math.sin(t * 0.8 + ph))
        cv2.circle(ov, (int(x), int(y)), int(r), (a * 0.75, a * 0.9, a), -1, cv2.LINE_AA)
    ov = cv2.GaussianBlur(ov, (0, 0), 1.3)
    frame = cv2.add(frame, ov)

    for t0, a in FLASHES:
        if 0 <= t - t0 < 0.45:
            v = a * math.exp(-(t - t0) / 0.11)
            frame = cv2.addWeighted(frame, 1 - v * 0.6, np.full_like(frame, 255), v * 0.6, 0)

    gi = int(t * 24) % len(GRAIN)
    frame = cv2.subtract(cv2.add(frame, GRAIN[gi][0]), GRAIN[gi][1])

    draw_captions(frame, t)

    # global fades
    fade = smooth(t / 1.2) * smooth((TOTAL - t) / 1.5)
    if t > END_SLATE[0]:
        fade *= 1 - 0.6 * smooth((t - END_SLATE[0]) / 1.0)
    if fade < 0.999:
        frame = cv2.convertScaleAbs(frame, alpha=fade)
    return frame


def render_chunk(job):
    idx, f0, f1, ass = job
    out = os.path.join(WORK, 'seg', f'seg{idx:03d}.mp4')
    if os.path.exists(out) and os.path.exists(out + '.done'):
        return out
    t0 = f0 / FPS
    vf = (f"setpts=PTS+{t0:.6f}/TB,ass='{ass}':fontsdir='{FONTS}',setpts=PTS-STARTPTS,format=yuv420p")
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}',
                          '-r', str(FPS), '-i', '-', '-vf', vf, '-c:v', 'libx264', '-preset', 'medium',
                          '-crf', '18', '-threads', '2', '-g', '60', '-bf', '2', out], stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        p.stdin.write(compose(fi / FPS).tobytes())
    p.stdin.close()
    p.wait()
    open(out + '.done', 'w').write('ok')
    return out


def main():
    ass = os.path.join(WORK, 'captions.ass')
    build_ass(ass)
    print('ass ok', len(SCENES), 'scenes', len(CARDS), 'cards')
    if '--only-ass' in ARGS:
        return
    if '--preview' in ARGS:
        init_worker()
        times = [float(x) for x in ARGS[ARGS.index('--preview') + 1].split(',')]
        os.makedirs(os.path.join(WORK, 'prev'), exist_ok=True)
        for t in times:
            fr = compose(t)
            raw = os.path.join(WORK, 'prev', 'raw.png')
            cv2.imwrite(raw, fr)
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', raw, '-vf',
                            f"setpts=PTS+{t}/TB,ass='{ass}':fontsdir='{FONTS}'", '-frames:v', '1',
                            os.path.join(WORK, 'prev', f'p_{t:07.2f}.jpg')], check=True)
        return
    mix = os.path.join(WORK, 'mix.wav')
    if not os.path.exists(mix) or '--audio' in ARGS:
        build_audio(mix)
        print('audio ok')
    if '--only-audio' in ARGS:
        return
    os.makedirs(os.path.join(WORK, 'seg'), exist_ok=True)
    n = 24
    step = math.ceil(NFRAMES / n)
    jobs = [(i, i * step, min((i + 1) * step, NFRAMES), ass) for i in range(n) if i * step < NFRAMES]
    with Pool(3, initializer=init_worker) as pool:
        segs = []
        for s in pool.imap(render_chunk, jobs):
            segs.append(s)
            print('done', s, flush=True)
    lst = os.path.join(WORK, 'seg', 'list.txt')
    open(lst, 'w').write(''.join(f"file '{s}'\n" for s in segs))
    final = os.path.join(WORK, 'final.mp4')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-i', mix,
                    '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k',
                    '-movflags', '+faststart', '-t', f'{TOTAL:.3f}', final], check=True)
    print('FINAL', final)


if __name__ == '__main__':
    main()
