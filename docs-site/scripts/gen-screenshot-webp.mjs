// docs-site/scripts/gen-screenshot-webp.mjs
//
// Generates WebP variants alongside every PNG under public/screenshots/.
// Source PNGs are kept as-is — the `<picture>` source switches modern
// browsers to WebP (~40% smaller) while PNG stays the fallback.
// Idempotent: skips WebP files whose mtime is newer than the source PNG.
// Run: node scripts/gen-screenshot-webp.mjs

import sharp from 'sharp';
import { readdir, stat } from 'node:fs/promises';
import { join, dirname, basename, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DIR = join(__dirname, '..', 'public', 'screenshots');

const entries = await readdir(DIR);
const pngs = entries.filter((f) => f.endsWith('.png'));

for (const png of pngs) {
  const src = join(DIR, png);
  const webp = join(DIR, basename(png, extname(png)) + '.webp');

  const srcStat = await stat(src);
  let webpStat = null;
  try { webpStat = await stat(webp); } catch { /* missing -> regenerate */ }
  if (webpStat && webpStat.mtimeMs >= srcStat.mtimeMs) {
    console.log(`skip (up to date): ${png}`);
    continue;
  }

  await sharp(src)
    .webp({ quality: 82, effort: 6 })
    .toFile(webp);

  console.log(`wrote ${webp}`);
}

console.log('done.');
