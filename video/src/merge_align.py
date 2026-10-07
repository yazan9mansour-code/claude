"""Attach echogarden word timings to parsed script words."""
import json, re, sys

def norm(s):
    return re.sub(r'[^ء-يﷺ0-9]', '', re.sub(r'[ً-ْٰ]', '', s))

parsed = json.load(open(sys.argv[1], encoding='utf-8'))
tl = json.load(open(sys.argv[2], encoding='utf-8'))
ew = []
def walk(n):
    for x in n:
        if x['type'] == 'word':
            ew.append(x)
        elif x.get('timeline'):
            walk(x['timeline'])
walk(tl)
ew = [x for x in ew if norm(x['text'])]
words = [w for w in parsed['words']]
j = 0
for w in words:
    if not norm(w['text']):
        w['start'] = w['end'] = None
        continue
    # find matching echogarden word near j
    k = j
    while k < min(j + 4, len(ew)) and norm(ew[k]['text']) != norm(w['text']):
        k += 1
    if k < len(ew) and norm(ew[k]['text']) == norm(w['text']):
        j = k
    w['start'], w['end'] = ew[j]['startTime'], ew[j]['endTime']
    j += 1
# fill punctuation-only tokens from neighbours
for i, w in enumerate(words):
    if w['start'] is None:
        p = words[i - 1]
        w['start'] = w['end'] = p['end']
print('echogarden words', len(ew), 'script words', len(words))
for s in parsed['segs']:
    w = words[s['w0']] if s['w0'] < len(words) else None
    if w:
        d = w['start'] - s['start']
        flag = ' <<<' if abs(d) > 1.5 else ''
        print(f"{s['start']:7.1f} {w['start']:7.2f} {d:+5.2f} {w['text']}{flag}")
json.dump(parsed, open(sys.argv[3], 'w', encoding='utf-8'), ensure_ascii=False)
