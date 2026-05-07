// Walk api/app.py and api/routers/*.py and emit an MDX page listing every
// FastAPI route (path, methods, source file). Regex-based to avoid importing
// the heavy FastAPI app at build time.

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

  all.sort((a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method));

  const byFile = new Map();
  for (const r of all) {
    if (!byFile.has(r.file)) byFile.set(r.file, []);
    byFile.get(r.file).push(r);
  }

  const fileSummaryRows = [...byFile.entries()]
    .map(([file, items]) => `| \`${file}\` | ${items.length} |`)
    .join('\n');

  const tableRows = all
    .map(
      (r) =>
        `| ${methodCellHtml(r.method)} | \`${r.path}\` | <span style="font-size:0.75rem;color:var(--sl-color-gray-3)">${r.file}</span> |`,
    )
    .join('\n');

  const mdx = `---
title: API routes catalog
description: Auto-generated catalog of every FastAPI route, grouped by source file.
---

import { Aside, Card, CardGrid } from '@astrojs/starlight/components';

<CardGrid>
  <Card title="Total endpoints" icon="rocket">
    ${all.length}
  </Card>
  <Card title="Source files" icon="document">
    ${byFile.size}
  </Card>
</CardGrid>

## By file

| File | Endpoints |
| --- | ---: |
${fileSummaryRows || '| _no routes detected_ | 0 |'}

## All routes

<div class="route-table">

| Method | Path | Source |
| --- | --- | --- |
${tableRows || '| _no routes detected_ | | |'}

</div>

<Aside type="tip" title="Source">
  Generated from <code>api/app.py</code> and <code>api/routers/*.py</code> via
  regex on FastAPI route decorators. Re-run <code>npm run dev</code> or
  <code>npm run build</code> to refresh.
</Aside>
`;

  await mkdir(dirname(OUT_FILE), { recursive: true });
  await writeFile(OUT_FILE, mdx, 'utf8');
  console.log(`[gen-routes] wrote ${all.length} routes from ${byFile.size} files`);
}

main().catch((err) => {
  console.error('[gen-routes] failed:', err);
  process.exit(1);
});
