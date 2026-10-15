# Rafeef birth-announcement reel

Vertical reel (1080×1920, 30 fps, ~39 s) announcing the birth of رَفِيف:
pastel floral frame, the text revealed line by line, and the رفيف calligraphy
from the reference card (`reference.png`) written in from right to left.

- `reel.html` – the animation (`window.render(t)` draws the frame at time `t`)
- `name_mask.png` – the رفيف calligraphy extracted from the card, upscaled and smoothed
- `render.js` – renders every frame with Chromium and encodes with ffmpeg
- `music.py` – original soft music-box lullaby used as the default soundtrack

```sh
export NODE_PATH=$(npm root -g)
python3 music.py out/music.wav 39
node render.js out/rafeef_reel.mp4 out/music.wav
# use a different song instead:
node render.js out/rafeef_reel.mp4 path/to/song.mp3
# preview stills:
node render.js --preview out/prev 5,11,18,23,33
```
