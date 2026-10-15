// Render reel.html frame by frame with Chromium and encode with ffmpeg.
// usage: node render.js OUT.mp4 [AUDIO]          full video (30 fps, 1080x1920)
//        node render.js --preview DIR t1,t2,...  still frames as PNG
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { chromium } = require('playwright');

const FPS = 30;
const args = process.argv.slice(2);

(async () => {
  const browser = await chromium.launch({ args: ['--allow-file-access-from-files', '--font-render-hinting=none'] });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  await page.goto('file://' + path.join(__dirname, 'reel.html'));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  const stage = await page.$('#stage');

  if (args[0] === '--preview') {
    fs.mkdirSync(args[1], { recursive: true });
    for (const t of args[2].split(',').map(Number)) {
      await page.evaluate(t => window.render(t), t);
      await stage.screenshot({ path: path.join(args[1], `t${String(t).padStart(5, '0')}.png`) });
    }
    await browser.close();
    return;
  }

  const out = args[0], audio = args[1];
  const total = await page.evaluate(() => window.TOTAL);
  const n = Math.round(total * FPS);
  const ff = ['-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-'];
  if (audio) ff.push('-i', audio, '-map', '0:v', '-map', '1:a', '-af', `afade=t=out:st=${(total - .8).toFixed(2)}:d=0.8`,
    '-c:a', 'aac', '-b:a', '192k', '-shortest');
  ff.push('-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p',
    '-profile:v', 'high', '-movflags', '+faststart', out);
  const enc = spawn('ffmpeg', ff, { stdio: ['pipe', 'ignore', 'inherit'] });

  for (let i = 0; i < n; i++) {
    await page.evaluate(t => window.render(t), i / FPS);
    const buf = await stage.screenshot({ type: 'jpeg', quality: 97 });
    if (!enc.stdin.write(buf)) await new Promise(r => enc.stdin.once('drain', r));
    if (i % 90 === 0) process.stderr.write(`frame ${i}/${n}\n`);
  }
  enc.stdin.end();
  await new Promise(r => enc.on('close', r));
  await browser.close();
})();
