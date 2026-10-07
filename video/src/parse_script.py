"""Parse script.txt into words with scene/sfx/emphasis markers."""
import json, re, sys

def ts(s):
    m, sec = s.split(':')
    return int(m) * 60 + float(sec)

def parse(path):
    segs, words, scenes, sfx = [], [], [], []
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#'):
            continue
        start, text = line.split('|', 1)
        segs.append({'start': ts(start), 'w0': len(words)})
        emph = False
        for tok in text.split():
            if re.fullmatch(r'@\d{3}', tok):
                scenes.append({'img': int(tok[1:]), 'w': len(words)})
                continue
            if tok.startswith('!'):
                sfx.append({'name': tok[1:], 'w': len(words)})
                continue
            open_ = '*' in tok[:2]
            if open_:
                emph = True
            close = tok.rstrip('،.:؟?!؛﴾﴿').endswith('*') or tok.endswith('*')
            clean = tok.replace('*', '')
            words.append({'text': clean, 'emph': emph, 'seg': len(segs) - 1})
            if close:
                emph = False
    return {'segs': segs, 'words': words, 'scenes': scenes, 'sfx': sfx}

if __name__ == '__main__':
    d = parse(sys.argv[1])
    json.dump(d, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    open(sys.argv[3], 'w', encoding='utf-8').write(' '.join(w['text'] for w in d['words']))
    print(len(d['words']), 'words', len(d['scenes']), 'scenes', len(d['sfx']), 'sfx')
