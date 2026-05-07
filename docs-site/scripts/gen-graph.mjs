// Parse agent/graph.py (regex-based, no Python runtime) and emit a Mermaid
// diagram of the LangGraph state machine into
// src/content/docs/architecture/langgraph.mdx.

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, '..', '..');
const GRAPH_FILE = join(PROJECT_ROOT, 'agent', 'graph.py');
const OUT_FILE = join(__dirname, '..', 'src', 'content', 'docs', 'architecture', 'langgraph.mdx');

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

async function main() {
  const src = await readFile(GRAPH_FILE, 'utf8');
  const parsed = parseGraph(src);
  const mermaid = renderMermaid(parsed);

  const mdx = `---
title: LangGraph state machine
description: Auto-generated state-machine diagram for the LangGraph agent.
---

import { Aside, Card, CardGrid } from '@astrojs/starlight/components';

The diagram below is generated from \`agent/graph.py\` at build time. Conditional
edges are listed underneath; they fan out to multiple downstream nodes based on
runtime state.

\`\`\`mermaid
${mermaid}
\`\`\`

## Conditional routers

${
  parsed.conditionalEdges.length === 0
    ? '_No conditional routers were detected._'
    : parsed.conditionalEdges.map((n) => `- \`${n}\``).join('\n')
}

## Node count

<CardGrid>
  <Card title="Total nodes" icon="puzzle">
    ${parsed.nodes.filter((n) => n !== 'START' && n !== 'END').length}
  </Card>
  <Card title="Direct edges" icon="random">
    ${parsed.edges.length}
  </Card>
  <Card title="Conditional routers" icon="approve-check">
    ${parsed.conditionalEdges.length}
  </Card>
</CardGrid>

<Aside type="tip" title="Source">
  Generated from <code>agent/graph.py</code>. Re-run <code>npm run dev</code> or
  <code>npm run build</code> to refresh.
</Aside>
`;

  await mkdir(dirname(OUT_FILE), { recursive: true });
  await writeFile(OUT_FILE, mdx, 'utf8');
  console.log(
    `[gen-graph] wrote ${parsed.nodes.length} nodes / ${parsed.edges.length} edges / ${parsed.conditionalEdges.length} conditional routers`,
  );
}

main().catch((err) => {
  console.error('[gen-graph] failed:', err);
  process.exit(1);
});
