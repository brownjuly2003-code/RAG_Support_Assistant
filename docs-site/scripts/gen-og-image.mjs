// docs-site/scripts/gen-og-image.mjs
//
// Generates docs-site/public/og-image.png (1200x630) from inline SVG.
// Editorial layout, custom SVG only (no Iconify / emoji / stock icons).
// Run: node scripts/gen-og-image.mjs

import sharp from 'sharp';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(__dirname, '..', 'public');
const OUT_PNG = join(OUT_DIR, 'og-image.png');
const OUT_SVG = join(OUT_DIR, 'og-image.svg');

const BRAND = '#0A6CB4';
const ACCENT = '#3DDC97';
const INK = '#0F1729';
const MUTED = '#475569';
const RULE = '#E2E8F0';
const PAPER = '#FBFCFE';

const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${PAPER}"/>
      <stop offset="100%" stop-color="#F1F5F9"/>
    </linearGradient>
  </defs>

  <rect width="1200" height="630" fill="url(#bg)"/>

  <!-- Left accent rail -->
  <rect x="0" y="0" width="14" height="630" fill="${BRAND}"/>

  <!-- Eyebrow rule + label -->
  <line x1="80" y1="118" x2="160" y2="118" stroke="${BRAND}" stroke-width="2"/>
  <text x="172" y="124"
        font-family="Inter, system-ui, sans-serif"
        font-size="20" font-weight="600"
        letter-spacing="3.5"
        fill="${BRAND}">DOCS HUB</text>

  <!-- Title -->
  <text x="80" y="220"
        font-family="Inter, system-ui, sans-serif"
        font-size="84" font-weight="800"
        fill="${INK}"
        letter-spacing="-2">RAG Support Assistant</text>

  <!-- Subtitle -->
  <text x="80" y="278"
        font-family="Inter, system-ui, sans-serif"
        font-size="30" font-weight="500"
        fill="${MUTED}">LangGraph retrieval · observability · offline evaluation</text>

  <!-- Stats row -->
  <line x1="80" y1="358" x2="1120" y2="358" stroke="${RULE}" stroke-width="1"/>
  <line x1="80" y1="488" x2="1120" y2="488" stroke="${RULE}" stroke-width="1"/>

  <g font-family="Inter, system-ui, sans-serif">
    <!-- Stat 1 -->
    <text x="80" y="412" font-size="56" font-weight="800" fill="${INK}" letter-spacing="-1">9</text>
    <text x="80" y="448" font-size="16" font-weight="600" fill="${MUTED}" letter-spacing="1.5">SIDEBAR PAGES · BILINGUAL</text>

    <!-- Stat 2 -->
    <text x="430" y="412" font-size="56" font-weight="800" fill="${INK}" letter-spacing="-1">E20</text>
    <text x="430" y="448" font-size="16" font-weight="600" fill="${MUTED}" letter-spacing="1.5">REPRODUCIBLE TRACE</text>

    <!-- Stat 3 -->
    <text x="780" y="412" font-size="56" font-weight="800" fill="${INK}" letter-spacing="-1">12</text>
    <text x="780" y="448" font-size="16" font-weight="600" fill="${MUTED}" letter-spacing="1.5">OFFLINE BENCHMARK CASES</text>
  </g>

  <!-- Author + custom inline SVG graph motif -->
  <g transform="translate(80, 540)">
    <text x="0" y="0"
          font-family="Inter, system-ui, sans-serif"
          font-size="20" font-weight="600"
          fill="${INK}">Julia Edomskikh</text>
    <text x="0" y="28"
          font-family="Inter, system-ui, sans-serif"
          font-size="16" font-weight="400"
          fill="${MUTED}">Senior Data Analyst · Data Engineer</text>
  </g>

  <!-- Graph nodes motif (custom inline SVG, no icons) -->
  <g transform="translate(960, 540)" fill="none" stroke-linecap="round">
    <line x1="14" y1="14" x2="74" y2="-26" stroke="${BRAND}" stroke-width="2"/>
    <line x1="14" y1="14" x2="74" y2="54" stroke="${BRAND}" stroke-width="2"/>
    <line x1="74" y1="-26" x2="134" y2="14" stroke="${BRAND}" stroke-width="2"/>
    <line x1="74" y1="54" x2="134" y2="14" stroke="${BRAND}" stroke-width="2"/>
    <circle cx="14"  cy="14"  r="10" fill="#FFFFFF" stroke="${BRAND}" stroke-width="3"/>
    <circle cx="74"  cy="-26" r="10" fill="#FFFFFF" stroke="${BRAND}" stroke-width="3"/>
    <circle cx="74"  cy="54"  r="10" fill="#FFFFFF" stroke="${BRAND}" stroke-width="3"/>
    <circle cx="134" cy="14"  r="14" fill="${ACCENT}" stroke="${BRAND}" stroke-width="3"/>
  </g>
</svg>`;

mkdirSync(OUT_DIR, { recursive: true });
writeFileSync(OUT_SVG, svg, 'utf8');

await sharp(Buffer.from(svg))
  .png({ compressionLevel: 9 })
  .toFile(OUT_PNG);

console.log(`wrote ${OUT_SVG}`);
console.log(`wrote ${OUT_PNG}`);
