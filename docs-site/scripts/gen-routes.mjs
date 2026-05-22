// Walk api/app.py and api/routers/*.py and emit an MDX page listing every
// FastAPI route (path, methods, source file), grouped by product area.
// Regex-based to avoid importing the heavy FastAPI app at build time.

import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, '..', '..');
const ROUTERS_DIR = join(PROJECT_ROOT, 'api', 'routers');
const APP_FILE = join(PROJECT_ROOT, 'api', 'app.py');
const OUT_FILE = join(__dirname, '..', 'src', 'content', 'docs', 'architecture', 'routes.mdx');

const METHOD_RE = /@(?:app|router)\.(get|post|put|patch|delete|head|options)\(\s*["']([^"']+)["']/gi;

// Stable group order surfaced on the page.
const GROUP_ORDER = ['Ask/Chat', 'KB', 'Experiments', 'Analytics', 'Auth', 'Admin', 'System'];

// api/app.py mounts a single APIRouter(prefix="/api") that includes every
// router under api/routers/ EXCEPT root_pages.py, which is mounted on the
// app directly without a prefix (serves /agent dashboard, /metrics, and the
// /admin/traces/{trace_id} HTML redirect at root level).
function fullPath(file, path) {
  if (path.startsWith('/api/')) return path;
  if (file.endsWith('api/app.py') || file.endsWith('api/routers/root_pages.py')) return path;
  return `/api${path}`;
}

// Map a source file (or, as a fallback, a route path) to a product group.
function groupFor(file, path) {
  const f = file.toLowerCase();
  // Admin routers split by responsibility, so the experiments/evaluations
  // ones land in their own product groups instead of the generic Admin pile.
  if (f.includes('admin_experiments')) return 'Experiments';
  if (f.includes('admin_evaluations')) return 'Analytics';
  if (f.includes('admin_review') || f.includes('admin_kb') || f.includes('admin_ops')) return 'Admin';
  if (f.includes('conversation') || f.includes('agent.py') || f.includes('feedback')) return 'Ask/Chat';
  if (f.includes('upload')) return 'KB';
  if (f.includes('analytics')) return 'Analytics';
  if (f.includes('auth_sso') || f.includes('session_auth')) return 'Auth';
  if (f.includes('system.py') || f.includes('root_pages') || f.endsWith('api/app.py')) return 'System';
  // misc.py mixes /admin/* with /channels/*; pick the group from the path.
  if (path.startsWith('/admin')) return 'Admin';
  if (path.startsWith('/auth') || path.startsWith('/sessions')) return 'Auth';
  if (path.startsWith('/analytics')) return 'Analytics';
  if (path.startsWith('/ask') || path.startsWith('/chat') || path.startsWith('/agent') || path === '/feedback' || path === '/escalate') return 'Ask/Chat';
  if (path.startsWith('/upload') || path.startsWith('/tasks')) return 'KB';
  return 'System';
}

async function listRoutesInFile(file) {
  const content = await readFile(file, 'utf8');
  const found = [];
  let m;
  while ((m = METHOD_RE.exec(content))) {
    found.push({ method: m[1].toUpperCase(), path: m[2], file: relative(PROJECT_ROOT, file).replace(/\\/g, '/') });
  }
  return found;
}

function methodCellHtml(method) {
  const cls = `route-method route-method-${method.toLowerCase()}`;
  return `<span class="${cls}">${method}</span>`;
}

// Match Starlight's heading-id generator: it strips non-word punctuation
// rather than replacing it with a hyphen, so "Ask/Chat" → "askchat" (not
// "ask-chat"). Aligning slugFor keeps cross-anchors live.
function slugFor(group) {
  return group.toLowerCase().replace(/[^a-z0-9]+/g, '').trim();
}

async function main() {
  const all = [];

  if (existsSync(APP_FILE)) {
    all.push(...(await listRoutesInFile(APP_FILE)));
  }

  if (existsSync(ROUTERS_DIR)) {
    const entries = await readdir(ROUTERS_DIR, { withFileTypes: true });
    for (const e of entries) {
      if (!e.isFile() || extname(e.name) !== '.py') continue;
      all.push(...(await listRoutesInFile(join(ROUTERS_DIR, e.name))));
    }
  }

  for (const r of all) {
    r.path = fullPath(r.file, r.path);
    r.group = groupFor(r.file, r.path);
  }

  all.sort((a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method));

  const byFile = new Map();
  for (const r of all) {
    if (!byFile.has(r.file)) byFile.set(r.file, []);
    byFile.get(r.file).push(r);
  }

  const byGroup = new Map();
  for (const g of GROUP_ORDER) byGroup.set(g, []);
  for (const r of all) {
    if (!byGroup.has(r.group)) byGroup.set(r.group, []);
    byGroup.get(r.group).push(r);
  }

  const fileSummaryRows = [...byFile.entries()]
    .map(([file, items]) => `| \`${file}\` | ${items.length} |`)
    .join('\n');

  const groupSummaryRows = [...byGroup.entries()]
    .filter(([, items]) => items.length > 0)
    .map(([group, items]) => `| [${group}](#${slugFor(group)}) | ${items.length} |`)
    .join('\n');

  function renderGroupSection(group, items) {
    if (!items.length) return '';
    const rows = items
      .map(
        (r) =>
          `| ${methodCellHtml(r.method)} | \`${r.path}\` | <span style="font-size:0.75rem;color:var(--sl-color-gray-3)">${r.file}</span> |`,
      )
      .join('\n');
    return `### ${group}

<div class="route-table">

| Method | Path | Source |
| --- | --- | --- |
${rows}

</div>
`;
  }

  const groupSections = [...byGroup.entries()]
    .filter(([, items]) => items.length > 0)
    .map(([group, items]) => renderGroupSection(group, items))
    .join('\n');

  const groupCount = [...byGroup.values()].filter((items) => items.length > 0).length;

  const mdx = `---
title: API routes catalog
description: Auto-generated catalog of every FastAPI route, grouped by product area.
---

import { Aside } from '@astrojs/starlight/components';

<div class="q-cardgrid q-cardgrid--accent" data-route-summary>
  <article class="q-card">
    <p class="q-title">
      <span class="q-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M5 7l7 5 7-5" />
          <path d="M5 7v10h14V7" />
          <path d="M5 7l7-3 7 3" />
        </svg>
      </span>
      <span class="q-label">Total endpoints</span>
    </p>
    <div class="q-body"><p>${all.length}</p></div>
  </article>
  <article class="q-card">
    <p class="q-title">
      <span class="q-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M5 4v16" />
          <path d="M5 8h4" />
          <path d="M5 14h4" />
          <path d="M9 6h10v4H9z" />
          <path d="M9 14h10v4H9z" />
        </svg>
      </span>
      <span class="q-label">Source files</span>
    </p>
    <div class="q-body"><p>${byFile.size}</p></div>
  </article>
  <article class="q-card">
    <p class="q-title">
      <span class="q-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <circle cx="6" cy="6" r="2.5" />
          <circle cx="18" cy="6" r="2.5" />
          <circle cx="12" cy="18" r="2.5" />
          <path d="M8.2 7.5l3 7.5" />
          <path d="M15.8 7.5l-3 7.5" />
          <path d="M8.5 6h7" />
        </svg>
      </span>
      <span class="q-label">Groups</span>
    </p>
    <div class="q-body"><p>${groupCount}</p></div>
  </article>
</div>

## By group

| Group | Endpoints |
| --- | ---: |
${groupSummaryRows || '| _no routes detected_ | 0 |'}

## By file

| File | Endpoints |
| --- | ---: |
${fileSummaryRows || '| _no routes detected_ | 0 |'}

## Routes by group

${groupSections || '_no routes detected_'}

<Aside type="tip" title="Source">
  Generated from <code>api/app.py</code> and <code>api/routers/*.py</code> via
  regex on FastAPI route decorators by <code>docs-site/scripts/gen-routes.mjs</code>.
  Edits to this file are overwritten on every <code>npm run build</code> — change
  the generator script if you need a different layout.
</Aside>
`;

  await mkdir(dirname(OUT_FILE), { recursive: true });
  await writeFile(OUT_FILE, mdx, 'utf8');
  console.log(`[gen-routes] wrote ${all.length} routes from ${byFile.size} files across ${[...byGroup.values()].filter((items) => items.length > 0).length} groups`);
}

main().catch((err) => {
  console.error('[gen-routes] failed:', err);
  process.exit(1);
});
