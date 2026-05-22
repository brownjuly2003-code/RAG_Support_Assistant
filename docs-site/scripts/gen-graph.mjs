// Parse agent/graph.py (regex-based, no Python runtime) and emit a Mermaid
// diagram of the LangGraph state machine into
// src/content/docs/architecture/langgraph.mdx.

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, '..', '..');
const GRAPH_FILE = join(PROJECT_ROOT, 'agent', 'graph.py');
const OUT_FILE_EN = join(__dirname, '..', 'src', 'content', 'docs', 'architecture', 'langgraph.mdx');
const OUT_FILE_RU = join(__dirname, '..', 'src', 'content', 'docs', 'ru', 'architecture', 'langgraph.mdx');

function parseGraph(src) {
  const nodes = new Set();
  const edges = [];
  const conditionalEdges = [];

  const nodeRe = /workflow\.add_node\(\s*["']([^"']+)["']/g;
  const edgeRe = /workflow\.add_edge\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']/g;
  const condRe = /workflow\.add_conditional_edges\(\s*["']([^"']+)["']/g;

  let m;
  while ((m = nodeRe.exec(src))) nodes.add(m[1]);
  while ((m = edgeRe.exec(src))) {
    edges.push([m[1], m[2]]);
    nodes.add(m[1]);
    nodes.add(m[2]);
  }
  while ((m = condRe.exec(src))) {
    conditionalEdges.push(m[1]);
    nodes.add(m[1]);
  }

  // START / END nodes used by LangGraph
  const startEdgeRe = /workflow\.add_edge\(\s*START\s*,\s*["']([^"']+)["']/g;
  while ((m = startEdgeRe.exec(src))) {
    edges.push(['START', m[1]]);
    nodes.add('START');
    nodes.add(m[1]);
  }
  const setEntryRe = /workflow\.set_entry_point\(\s*["']([^"']+)["']/g;
  while ((m = setEntryRe.exec(src))) {
    edges.push(['START', m[1]]);
    nodes.add('START');
    nodes.add(m[1]);
  }
  const endEdgeRe = /workflow\.add_edge\(\s*["']([^"']+)["']\s*,\s*END\s*\)/g;
  while ((m = endEdgeRe.exec(src))) {
    edges.push([m[1], 'END']);
    nodes.add('END');
    nodes.add(m[1]);
  }

  return { nodes: [...nodes], edges, conditionalEdges };
}

function renderMermaid({ nodes, edges, conditionalEdges }) {
  const lines = ['flowchart TD'];
  for (const n of nodes) {
    if (n === 'START') lines.push('  START([Start])');
    else if (n === 'END') lines.push('  END([End])');
    else lines.push(`  ${n}["${n.replace(/_/g, ' ')}"]`);
  }
  for (const [from, to] of edges) {
    lines.push(`  ${from} --> ${to}`);
  }
  for (const node of conditionalEdges) {
    lines.push(`  %% conditional edges from ${node}`);
  }
  return lines.join('\n');
}

function renderMdx(parsed, mermaid, totalNodes, locale) {
  const L = locale === 'ru'
    ? {
        title: 'Конечный автомат LangGraph',
        description: 'Автогенерируемая диаграмма конечного автомата для LangGraph-агента.',
        intro: `Диаграмма ниже генерируется из \`agent/graph.py\` на этапе сборки. Условные рёбра перечислены ниже — они расходятся в разные узлы в зависимости от runtime-состояния.`,
        condHeading: 'Условные роутеры',
        condEmpty: '_Условные роутеры не обнаружены._',
        countHeading: 'Количество узлов',
        totalNodes: 'Всего узлов',
        directEdges: 'Прямые рёбра',
        condRouters: 'Условных роутеров',
        sourceTitle: 'Источник',
        sourceBody: `Сгенерировано из <code>agent/graph.py</code>. Перезапустите <code>npm run dev</code> или <code>npm run build</code> для обновления.`,
      }
    : {
        title: 'LangGraph state machine',
        description: 'Auto-generated state-machine diagram for the LangGraph agent.',
        intro: `The diagram below is generated from \`agent/graph.py\` at build time. Conditional\nedges are listed underneath; they fan out to multiple downstream nodes based on\nruntime state.`,
        condHeading: 'Conditional routers',
        condEmpty: '_No conditional routers were detected._',
        countHeading: 'Node count',
        totalNodes: 'Total nodes',
        directEdges: 'Direct edges',
        condRouters: 'Conditional routers',
        sourceTitle: 'Source',
        sourceBody: `Generated from <code>agent/graph.py</code>. Re-run <code>npm run dev</code> or\n  <code>npm run build</code> to refresh.`,
      };

  return `---
title: ${L.title}
description: ${L.description}
---

import { Aside } from '@astrojs/starlight/components';

${L.intro}

\`\`\`mermaid
${mermaid}
\`\`\`

## ${L.condHeading}

${
  parsed.conditionalEdges.length === 0
    ? L.condEmpty
    : parsed.conditionalEdges.map((n) => `- \`${n}\``).join('\n')
}

## ${L.countHeading}

<div class="q-cardgrid q-cardgrid--accent">
  <article class="q-card">
    <h3 class="q-title">
      <span class="q-label">${L.totalNodes}</span>
    </h3>
    <div class="q-body"><p>${totalNodes}</p></div>
  </article>
  <article class="q-card">
    <h3 class="q-title">
      <span class="q-label">${L.directEdges}</span>
    </h3>
    <div class="q-body"><p>${parsed.edges.length}</p></div>
  </article>
  <article class="q-card">
    <h3 class="q-title">
      <span class="q-label">${L.condRouters}</span>
    </h3>
    <div class="q-body"><p>${parsed.conditionalEdges.length}</p></div>
  </article>
</div>

<Aside type="tip" title="${L.sourceTitle}">
  ${L.sourceBody}
</Aside>
`;
}

async function main() {
  const src = await readFile(GRAPH_FILE, 'utf8');
  const parsed = parseGraph(src);
  const mermaid = renderMermaid(parsed);
  const totalNodes = parsed.nodes.filter((n) => n !== 'START' && n !== 'END').length;

  for (const [out, locale] of [[OUT_FILE_EN, 'en'], [OUT_FILE_RU, 'ru']]) {
    await mkdir(dirname(out), { recursive: true });
    await writeFile(out, renderMdx(parsed, mermaid, totalNodes, locale), 'utf8');
  }
  console.log(
    `[gen-graph] wrote ${parsed.nodes.length} nodes / ${parsed.edges.length} edges / ${parsed.conditionalEdges.length} conditional routers (en + ru)`,
  );
}

main().catch((err) => {
  console.error('[gen-graph] failed:', err);
  process.exit(1);
});
