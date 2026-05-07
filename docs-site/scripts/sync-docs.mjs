// Copy markdown content from the project's docs/ tree (and a few root .md
// files) into Starlight's content collection at src/content/docs/guides/.
// Adds front-matter when missing so Starlight can index the page.

import { readdir, readFile, writeFile, mkdir, rm, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, extname, join, relative, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, '..', '..');
const SRC_DOCS = join(PROJECT_ROOT, 'docs');
const OUT_DIR = join(__dirname, '..', 'src', 'content', 'docs', 'guides');

const ROOT_FILES = [
  { src: 'README.md', dest: 'overview.md', title: 'Project overview' },
  { src: 'AGENT_STATE.md', dest: 'agent-state.md', title: 'Agent state snapshot' },
  { src: 'BACKLOG.md', dest: 'backlog.md', title: 'Backlog' },
  { src: 'AUTOPILOT.md', dest: 'autopilot.md', title: 'Autopilot guardrails' },
  { src: 'DEPRECATIONS.md', dest: 'deprecations.md', title: 'Module layout & deprecations' },
];

async function walkMarkdown(dir, prefix = '') {
  const entries = await readdir(dir, { withFileTypes: true });
  const out = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    const rel = prefix ? join(prefix, entry.name) : entry.name;
    if (entry.isDirectory()) {
      out.push(...(await walkMarkdown(full, rel)));
    } else if (extname(entry.name) === '.md') {
      out.push({ full, rel });
    }
  }
  return out;
}

function deriveTitle(content, fallbackName) {
  const h1 = content.match(/^#\s+(.+)$/m);
  if (h1) return h1[1].trim();
  return fallbackName.replace(/[-_]/g, ' ').replace(/\.md$/, '');
}

function ensureFrontMatter(content, title, sourcePath) {
  const trimmed = content.replace(/^﻿/, '');
  if (trimmed.startsWith('---')) {
    // Starlight requires `title` — patch it in if absent.
    const fm = trimmed.match(/^---\n([\s\S]*?)\n---/);
    if (fm && !/^title:/m.test(fm[1])) {
      return `---\n${fm[1]}\ntitle: ${JSON.stringify(title)}\n---${trimmed.slice(fm[0].length)}`;
    }
    return trimmed;
  }
  const safeTitle = title.replace(/"/g, '\\"');
  const editUrl = `https://github.com/brownjuly2003-code/RAG_Support_Assistant/blob/master/${sourcePath.replace(/\\/g, '/')}`;
  return `---\ntitle: "${safeTitle}"\neditUrl: ${editUrl}\n---\n\n${trimmed}`;
}

function slugifyPath(rel) {
  // Starlight requires lowercase slug-safe filenames; preserve directory names
  // but lowercase + remove spaces.
  return rel
    .split(/[\\/]/)
    .map((p) => p.toLowerCase().replace(/\s+/g, '-'))
    .join('/');
}

async function copyOne(srcAbs, destAbs, title, sourcePath) {
  const raw = await readFile(srcAbs, 'utf8');
  const patched = ensureFrontMatter(raw, title, sourcePath);
  await mkdir(dirname(destAbs), { recursive: true });
  await writeFile(destAbs, patched, 'utf8');
}

async function main() {
  // Clean old generated guides so removed source files do not linger.
  if (existsSync(OUT_DIR)) {
    await rm(OUT_DIR, { recursive: true, force: true });
  }
  await mkdir(OUT_DIR, { recursive: true });

  let count = 0;

  // 1) docs/ tree
  if (existsSync(SRC_DOCS)) {
    const all = await walkMarkdown(SRC_DOCS);
    for (const { full, rel } of all) {
      const raw = await readFile(full, 'utf8');
      const title = deriveTitle(raw, basename(rel));
      const destRel = slugifyPath(rel);
      const destAbs = join(OUT_DIR, destRel);
      const sourcePath = `docs/${rel.replace(/\\/g, '/')}`;
      await copyOne(full, destAbs, title, sourcePath);
      count++;
    }
  }

  // 2) Selected root-level .md files
  for (const file of ROOT_FILES) {
    const srcAbs = join(PROJECT_ROOT, file.src);
    if (!existsSync(srcAbs)) continue;
    const destAbs = join(OUT_DIR, file.dest);
    await copyOne(srcAbs, destAbs, file.title, file.src);
    count++;
  }

  console.log(`[sync-docs] copied ${count} markdown files into ${relative(PROJECT_ROOT, OUT_DIR)}`);
}

main().catch((err) => {
  console.error('[sync-docs] failed:', err);
  process.exit(1);
});
