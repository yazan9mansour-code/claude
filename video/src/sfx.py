"""Synthesize cinematic sound effects (no music) as 48 kHz stereo WAVs."""
import os
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
rng = np.random.default_rng(7)


def t_axis(dur):
    return np.arange(int(dur * SR)) / SR


def lp(x, f, order=4):
    return sosfilt(butter(order, f, 'low', fs=SR, output='sos'), x)


def hp(x, f, order=4):
    return sosfilt(butter(order, f, 'high', fs=SR, output='sos'), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], 'band', fs=SR, output='sos'), x)


def env_ad(n, attack, decay_tau):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-np.maximum(t - attack, 0) / decay_tau)


def reverb(x, size=2.2, wet=0.35, damp=3000):
    n = int(size * SR)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / SR * (6.9 / size))
    ir = lp(ir, damp)
    ir /= np.abs(ir).sum() ** 0.5 * 8
    y = fftconvolve(x, ir)[: len(x) + n]
    out = np.zeros(len(y))
    out[: len(x)] += x * (1 - wet)
    return out + y * wet


def stereo(x, width=0.0):
    if width <= 0:
        return np.stack([x, x], 1)
    d = int(0.012 * SR)
    r = np.concatenate([np.zeros(d), x])[: len(x)]
    return np.stack([x * (1 - width) + x * width, x * (1 - width) + r * width], 1)


def norm(x, peak=0.9):
    m = np.abs(x).max()
    return x / m * peak if m > 0 else x


def whoosh(dur=0.9):
    n = int(dur * SR)
    noise = rng.standard_normal(n)
    t = np.arange(n) / n
    out = np.zeros(n)
    # time-varying band-pass via short blocks
    blk = 512
    for i in range(0, n, blk):
        c = 300 + 3500 * np.sin(np.pi * min(i / n, 1)) ** 2
        seg = noise[max(0, i - 2048): i + blk]
        y = bp(seg, c * 0.5, min(c * 1.8, SR / 2 - 100))
        out[i: i + blk] = y[-len(noise[i: i + blk]):]
    e = np.sin(np.pi * t) ** 2.5
    x = out * e
    x = reverb(x, 1.2, 0.25)
    # pan sweep
    pan = np.linspace(-0.7, 0.7, len(x))
    st = np.stack([x * (1 - pan) / 2 * 2, x * (1 + pan) / 2 * 2], 1)
    return norm(st, 0.8)


def boom(dur=4.0):
    t = t_axis(dur)
    f = 55 * np.exp(-t * 1.4) + 28
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ad(len(t), 0.005, 1.1)
    hit = lp(rng.standard_normal(len(t)), 1800) * env_ad(len(t), 0.001, 0.08)
    body = lp(rng.standard_normal(len(t)), 300) * env_ad(len(t), 0.003, 0.6)
    x = sub * 1.0 + hit * 0.5 + body * 0.6
    x = reverb(x, 3.2, 0.4, 1500)
    return norm(stereo(np.tanh(x * 1.6), 0.5), 0.95)


def impact(dur=2.0):
    t = t_axis(dur)
    f = 90 * np.exp(-t * 8) + 40
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ad(len(t), 0.001, 0.35)
    crack = hp(rng.standard_normal(len(t)), 1500) * env_ad(len(t), 0.0005, 0.03)
    thud = lp(rng.standard_normal(len(t)), 600) * env_ad(len(t), 0.001, 0.15)
    x = sub + crack * 0.6 + thud * 0.8
    x = reverb(x, 1.8, 0.3, 2500)
    return norm(stereo(np.tanh(x * 2), 0.4), 0.95)


def hit(dur=2.5):
    """Dramatic 'braam'-less cinematic hit: low thump + metallic shimmer tail."""
    t = t_axis(dur)
    sub = np.sin(2 * np.pi * 48 * t) * env_ad(len(t), 0.003, 0.5)
    metal = sum(np.sin(2 * np.pi * fr * t + rng.uniform(0, 6)) * a
                for fr, a in [(523, .3), (1187, .2), (1712, .15), (2630, .1), (3511, .06)])
    metal = metal * env_ad(len(t), 0.002, 0.7)
    x = sub + metal * 0.35 + lp(rng.standard_normal(len(t)), 900) * env_ad(len(t), 0.001, 0.05) * 0.6
    x = reverb(x, 2.8, 0.45, 4000)
    return norm(stereo(x, 0.5), 0.9)


def riser(dur=2.0):
    t = t_axis(dur)
    noise = rng.standard_normal(len(t))
    blk = 1024
    out = np.zeros(len(t))
    for i in range(0, len(t), blk):
        c = 200 + 5000 * (i / len(t)) ** 2
        seg = noise[max(0, i - 4096): i + blk]
        out[i: i + blk] = bp(seg, c * 0.6, min(c * 1.5, SR / 2 - 100))[-len(noise[i: i + blk]):]
    e = (t / dur) ** 2
    return norm(stereo(out * e, 0.6), 0.6)


def rumble(dur=6.0):
    t = t_axis(dur)
    x = lp(rng.standard_normal(len(t)), 120) * 3
    x += np.sin(2 * np.pi * 36 * t) * 0.3
    e = np.clip(t / 1.5, 0, 1) * np.clip((dur - t) / 2.5, 0, 1)
    return norm(stereo(x * e, 0.6), 0.7)


def chain(dur=2.0):
    x = np.zeros(int(dur * SR))
    for k, tt in enumerate([0.05, 0.22, 0.31, 0.55, 0.62]):
        n = int(0.4 * SR)
        tl = np.arange(n) / SR
        partials = sum(np.sin(2 * np.pi * f * (1 + 0.02 * k) * tl + rng.uniform(0, 6)) * a
                       for f, a in [(2100, .4), (3370, .3), (4890, .2), (6250, .15)])
        click = hp(rng.standard_normal(n), 3000) * np.exp(-tl / 0.004)
        s = (partials * np.exp(-tl / 0.09) + click) * (0.9 - 0.12 * k)
        i = int(tt * SR)
        x[i: i + n] += s[: len(x) - i]
    x = reverb(x, 1.0, 0.25, 7000)
    return norm(stereo(x, 0.5), 0.6)


def heartbeat(dur=6.0, bpm=62):
    t = t_axis(dur)
    x = np.zeros(len(t))
    period = 60 / bpm
    tl = np.arange(int(0.25 * SR)) / SR
    thump = np.sin(2 * np.pi * (60 * np.exp(-tl * 10) + 38) * tl) * np.exp(-tl / 0.07)
    for b in np.arange(0, dur - 0.4, period):
        for off, amp in [(0, 1.0), (0.18, 0.7)]:
            i = int((b + off) * SR)
            x[i: i + len(thump)] += thump[: len(x) - i] * amp
    return norm(stereo(lp(x, 200), 0.0), 0.9)


def war_drums(dur=8.0, bpm=80):
    t = t_axis(dur)
    x = np.zeros(len(t))
    tl = np.arange(int(0.8 * SR)) / SR
    tom = np.sin(2 * np.pi * (85 * np.exp(-tl * 6) + 52) * tl) * np.exp(-tl / 0.22)
    tom += lp(rng.standard_normal(len(tl)), 700) * np.exp(-tl / 0.03) * 0.5
    beat = 60 / bpm
    pattern = [0, 0.5, 1, 1.75, 2, 2.5, 3, 3.25, 3.5]
    for bar in np.arange(0, dur, 4 * beat):
        for p in pattern:
            i = int((bar + p * beat) * SR)
            if i < len(x):
                a = 1.0 if p in (0, 2) else 0.6
                x[i: i + len(tom)] += tom[: len(x) - i] * a
    x = reverb(x, 2.5, 0.35, 1800)[: len(t)]
    e = np.clip(t / 1.0, 0, 1) * np.clip((dur - t) / 2.0, 0, 1)
    return norm(stereo(x * e, 0.5), 0.85)


def battle(dur=10.0):
    """Distant battle ambience: rumble, clashes of metal, cloth/air movement."""
    t = t_axis(dur)
    bed = lp(rng.standard_normal(len(t)), 250) * 2 + bp(rng.standard_normal(len(t)), 300, 1200) * 0.4
    x = bed
    tl = np.arange(int(0.5 * SR)) / SR
    for _ in range(int(dur * 2.2)):
        f0 = rng.uniform(1800, 3200)
        clash = sum(np.sin(2 * np.pi * f0 * r * tl + rng.uniform(0, 6)) * a
                    for r, a in [(1, .4), (1.47, .3), (2.09, .2), (2.76, .12)])
        clash = clash * np.exp(-tl / rng.uniform(0.05, 0.15)) + hp(rng.standard_normal(len(tl)), 2500) * np.exp(-tl / 0.01)
        i = int(rng.uniform(0, dur - 0.5) * SR)
        x[i: i + len(tl)] += clash * rng.uniform(0.15, 0.5)
    x = reverb(x, 2.0, 0.5, 3500)[: len(t)]
    e = np.clip(t / 1.5, 0, 1) * np.clip((dur - t) / 3.0, 0, 1)
    return norm(stereo(x * e, 0.8), 0.7)


def ding(dur=2.0):
    t = t_axis(dur)
    x = sum(np.sin(2 * np.pi * f * t) * a for f, a in [(1318, .5), (2637, .2), (3951, .08)])
    x = x * env_ad(len(t), 0.002, 0.5)
    pop = lp(rng.standard_normal(len(t)), 2500) * env_ad(len(t), 0.001, 0.02)
    return norm(stereo(reverb(x + pop * 0.5, 1.5, 0.3), 0.4), 0.6)


def click(dur=0.3):
    t = t_axis(dur)
    x = hp(rng.standard_normal(len(t)), 2000) * env_ad(len(t), 0.0005, 0.006)
    x += np.sin(2 * np.pi * 900 * t) * env_ad(len(t), 0.0005, 0.02) * 0.5
    return norm(stereo(x), 0.6)


def page(dur=1.2):
    t = t_axis(dur)
    x = bp(rng.standard_normal(len(t)), 1500, 7000) * (np.sin(np.pi * np.clip(t / 0.6, 0, 1)) ** 2)
    x *= 1 + 0.6 * np.sin(2 * np.pi * 23 * t)
    return norm(stereo(reverb(x, 0.8, 0.2), 0.4), 0.45)


def wind_bed(dur):
    """Long desert wind ambience with slow gusts."""
    n = int(dur * SR)
    out = np.zeros((n, 2))
    chunk = SR * 20
    for c in range(2):
        noise = rng.standard_normal(n)
        x = bp(noise, 150, 900, 2) + 0.3 * bp(noise, 900, 2500, 2)
        tt = np.arange(n) / SR
        g = 0.55 + 0.25 * np.sin(2 * np.pi * tt / 11 + c) + 0.2 * np.sin(2 * np.pi * tt / 4.3 + 2 * c)
        out[:, c] = x * g
    return norm(out, 0.5)


EFFECTS = {
    'whoosh': whoosh, 'boom': boom, 'impact': impact, 'hit': hit, 'riser': riser,
    'rumble': rumble, 'chain': chain, 'heartbeat': heartbeat, 'drums': war_drums,
    'battle': battle, 'ding': ding, 'click': click, 'page': page,
}


def save(path, x):
    wavfile.write(path, SR, (np.clip(x, -1, 1) * 32767).astype(np.int16))


if __name__ == '__main__':
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for name, fn in EFFECTS.items():
        save(os.path.join(out, name + '.wav'), fn())
    save(os.path.join(out, 'wind.wav'), wind_bed(float(sys.argv[2]) if len(sys.argv) > 2 else 780))
    print('ok')
