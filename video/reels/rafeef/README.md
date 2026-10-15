# Rafeef birth-announcement reel

Vertical reel (1080×1920, 30 fps, 24.3 s) announcing the birth of رَفِيف, modelled on
the reference reel the family sent: a watercolor bouquet scene, then a flower meadow
scene where the رفيف calligraphy from `reference.png` is written in, followed by the dua.
All flowers, butterflies and backgrounds are drawn in code; the soundtrack is `music.m4a`.

- `reel.html` – the animation (`window.render(t)` draws the frame at time `t`)
- `name_mask.png` – the رفيف calligraphy extracted from the card, upscaled and smoothed
- `render.js` – renders every frame with Chromium and encodes with ffmpeg
- `music.m4a` – soundtrack taken from the reference reel
- `music.py` – optional original music-box lullaby (fallback soundtrack)

```sh
export NODE_PATH=$(npm root -g)
node render.js out/rafeef_reel.mp4 music.m4a
# use a different song instead:
node render.js out/rafeef_reel.mp4 path/to/song.mp3
# preview stills:
node render.js --preview out/prev 5,11,18,23,33
```
