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
const OUT_FILE_EN = join(__dirname, '..', 'src', 'content', 'docs', 'architecture', 'routes.mdx');
const OUT_FILE_RU = join(__dirname, '..', 'src', 'content', 'docs', 'ru', 'architecture', 'routes.mdx');

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
  // fullPath() may have prepended "/api"; strip it for path-fallback tests
  // so /api/admin/providers still matches the /admin/* rule below.
  const p = path.replace(/^\/api(?=\/)/, '');
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
  // misc.py mixes /admin/* with /channels/*; pick the group from the (unprefixed) path.
  if (p.startsWith('/admin')) return 'Admin';
  if (p.startsWith('/channels')) return 'Ask/Chat';
  if (p.startsWith('/auth') || p.startsWith('/sessions')) return 'Auth';
  if (p.startsWith('/analytics')) return 'Analytics';
  if (p.startsWith('/ask') || p.startsWith('/chat') || p.startsWith('/agent') || p === '/feedback' || p === '/escalate') return 'Ask/Chat';
  if (p.startsWith('/upload') || p.startsWith('/tasks')) return 'KB';
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

  const groupCount = [...byGroup.values()].filter((items) => items.length > 0).length;

  function renderMdx(locale) {
    const L = locale === 'ru'
      ? {
          title: 'Каталог маршрутов API',
          description: 'Автогенерируемый каталог всех FastAPI-маршрутов, сгруппированный по продуктовым областям.',
          totalCard: 'Всего эндпоинтов',
          filesCard: 'Файлов-источников',
          groupsCard: 'Групп',
          byGroupHeading: 'По группе',
          byGroupHeader: '| Группа | Эндпоинтов |',
          byFileHeading: 'По файлу',
          byFileHeader: '| Файл | Эндпоинтов |',
          routesHeading: 'Маршруты по группе',
          tableHeader: '| Метод | Путь | Источник |',
          empty: '_маршрутов не обнаружено_',
          emptyRow: '| _маршрутов не обнаружено_ | 0 |',
          sourceTitle: 'Источник',
          sourceBody: `Сгенерировано из <code>api/app.py</code> и <code>api/routers/*.py</code> через\n  regex по декораторам маршрутов FastAPI в <code>docs-site/scripts/gen-routes.mjs</code>.\n  Правки в этом файле перезаписываются каждым <code>npm run build</code> — меняйте генератор, если нужен другой layout.`,
        }
      : {
          title: 'API routes catalog',
          description: 'Auto-generated catalog of every FastAPI route, grouped by product area.',
          totalCard: 'Total endpoints',
          filesCard: 'Source files',
          groupsCard: 'Groups',
          byGroupHeading: 'By group',
          byGroupHeader: '| Group | Endpoints |',
          byFileHeading: 'By file',
          byFileHeader: '| File | Endpoints |',
          routesHeading: 'Routes by group',
          tableHeader: '| Method | Path | Source |',
          empty: '_no routes detected_',
          emptyRow: '| _no routes detected_ | 0 |',
          sourceTitle: 'Source',
          sourceBody: `Generated from <code>api/app.py</code> and <code>api/routers/*.py</code> via\n  regex on FastAPI route decorators by <code>docs-site/scripts/gen-routes.mjs</code>.\n  Edits to this file are overwritten on every <code>npm run build</code> — change\n  the generator script if you need a different layout.`,
        };

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

${L.tableHeader}
| --- | --- | --- |
${rows}

</div>
`;
    }

    const groupSections = [...byGroup.entries()]
      .filter(([, items]) => items.length > 0)
      .map(([group, items]) => renderGroupSection(group, items))
      .join('\n');

    return `---
title: ${L.title}
description: ${L.description}
---

import { Aside } from '@astrojs/starlight/components';

<div class="q-cardgrid q-cardgrid--accent" data-route-summary>
  <article class="q-card">
    <h3 class="q-title">
      <span class="q-label">${L.totalCard}</span>
    </h3>
    <div class="q-body"><p>${all.length}</p></div>
  </article>
  <article class="q-card">
    <h3 class="q-title">
      <span class="q-label">${L.filesCard}</span>
    </h3>
    <div class="q-body"><p>${byFile.size}</p></div>
  </article>
  <article class="q-card">
    <h3 class="q-title">
      <span class="q-label">${L.groupsCard}</span>
    </h3>
    <div class="q-body"><p>${groupCount}</p></div>
  </article>
</div>

## ${L.byGroupHeading}

${L.byGroupHeader}
| --- | ---: |
${groupSummaryRows || L.emptyRow}

## ${L.byFileHeading}

${L.byFileHeader}
| --- | ---: |
${fileSummaryRows || L.emptyRow}

## ${L.routesHeading}

${groupSections || L.empty}

<Aside type="tip" title="${L.sourceTitle}">
  ${L.sourceBody}
</Aside>
`;
  }

  for (const [out, locale] of [[OUT_FILE_EN, 'en'], [OUT_FILE_RU, 'ru']]) {
    await mkdir(dirname(out), { recursive: true });
    await writeFile(out, renderMdx(locale), 'utf8');
  }
  console.log(`[gen-routes] wrote ${all.length} routes from ${byFile.size} files across ${groupCount} groups (en + ru)`);
}

main().catch((err) => {
  console.error('[gen-routes] failed:', err);
  process.exit(1);
});
