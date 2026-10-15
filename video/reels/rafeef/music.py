"""Soft music-box lullaby (original, royalty-free) used as the reel's soundtrack.
usage: python music.py OUT.wav [SECONDS]"""
import sys
import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve

SR = 44100
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 39.0
BPM = 84
BEAT = 60 / BPM
BAR = 3 * BEAT
rng = np.random.default_rng(7)

def hz(m):
    return 440 * 2 ** ((m - 69) / 12)

out = np.zeros((int(SR * (DUR + 4)), 2))

def bell(t0, midi, vel, pan=0.0, decay=1.6):
    n = int(SR * (decay * 3))
    t = np.arange(n) / SR
    f = hz(midi)
    s = (np.sin(2 * np.pi * f * t) * np.exp(-t / decay)
         + .35 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t / (decay * .45))
         + .12 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t / (decay * .25))
         + .05 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t / .08))
    s *= np.minimum(1, t / .004) * vel
    i = int(t0 * SR)
    if i >= len(out):
        return
    s = s[:len(out) - i]
    out[i:i + len(s), 0] += s * (1 - pan) * .5
    out[i:i + len(s), 1] += s * (1 + pan) * .5

def pad(t0, dur, midis, vel):
    n = int(SR * (dur + 1.5))
    t = np.arange(n) / SR
    env = np.minimum(1, t / .9) * np.where(t < dur, 1, np.exp(-(t - dur) / .5))
    s = sum(np.sin(2 * np.pi * hz(m) * t + rng.uniform(0, 6)) + .2 * np.sin(2 * np.pi * hz(m) * 2.003 * t)
            for m in midis) * env * vel / len(midis)
    i = int(t0 * SR)
    s = s[:len(out) - i]
    out[i:i + len(s), 0] += s
    out[i:i + len(s), 1] += s

# F major — chords as midi roots + triad
CH = {'F': [53, 57, 60], 'C': [48, 52, 55], 'Dm': [50, 53, 57], 'Bb': [46, 50, 53], 'Am': [45, 48, 52], 'Gm': [43, 46, 50]}
PROG = ['F', 'C', 'Dm', 'Bb', 'F', 'Am', 'Bb', 'C',
        'Dm', 'Bb', 'F', 'C', 'Gm', 'Bb', 'C', 'F',
        'F']
# melody per bar: (beat offset, midi) — simple, stepwise, singable
MEL = [
    [(0, 77), (1, 76), (2, 72)], [(0, 76), (1.5, 74), (2, 72)], [(0, 74), (1, 77), (2, 81)], [(0, 79), (2, 77)],
    [(0, 77), (1, 81), (2, 84)], [(0, 84), (1, 81), (2, 79)], [(0, 77), (1, 79), (2, 81)], [(0, 79)],
    [(0, 81), (1, 77), (2, 74)], [(0, 77), (1, 74), (2, 70)], [(0, 72), (1, 77), (2, 81)], [(0, 79), (1.5, 77), (2, 76)],
    [(0, 74), (1, 79), (2, 82)], [(0, 81), (1, 77), (2, 74)], [(0, 76), (1, 79), (2, 84)], [(0, 81)],
    [(0, 77), (1, 76), (2, 72)], [(0, 76), (1.5, 74), (2, 72)], [(0, 74), (1, 77), (2, 82)], [(0, 81), (1, 84)],
]
start = .25
for b, name in enumerate(PROG):
    t = start + b * BAR
    if t > DUR:
        break
    c = CH[name]
    arp = [c[0] + 12, c[1] + 12, c[2] + 12, c[1] + 12 + 12, c[2] + 12, c[1] + 12]
    for k, m in enumerate(arp):
        bell(t + k * BEAT / 2 + rng.normal(0, .004), m, .16 if k else .2, pan=-.35, decay=1.1)
    bell(t, c[0] - 12 + 12, .22, pan=0, decay=2.4)
    pad(t, BAR, [c[0] + 12, c[1] + 12, c[2] + 12], .05)
    if b >= 1:  # melody enters on bar 2
        for off, m in MEL[b % len(MEL)]:
            bell(t + off * BEAT + rng.normal(0, .006), m, .32, pan=.3, decay=1.9)
# final chord
tend = start + len(PROG) * BAR
for m in [65, 69, 72, 77]:
    bell(min(tend, DUR - 2.4), m, .2, decay=2.6)

# reverb: exponentially decaying stereo noise
ir_n = int(SR * 2.6)
ti = np.arange(ir_n) / SR
ir = rng.normal(0, 1, (ir_n, 2)) * np.exp(-ti / .55)[:, None]
ir[0] = 0
ir /= np.sqrt((ir ** 2).sum(0))
wet = np.stack([fftconvolve(out[:, c], ir[:, c])[:len(out)] for c in range(2)], 1)
mix = out * .8 + wet * .55
mix = mix[:int(SR * DUR)]
fi, fo = int(SR * .4), int(SR * 2.5)
mix[:fi] *= np.linspace(0, 1, fi)[:, None]
mix[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
mix /= np.abs(mix).max() / .89
wavfile.write(sys.argv[1], SR, (mix * 32767).astype(np.int16))
