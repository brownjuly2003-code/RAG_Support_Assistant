// Read config/providers.yml (using the `yaml` package) and emit the routing
// matrix as an MDX page.

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, '..', '..');
const PROVIDERS_FILE = join(PROJECT_ROOT, 'config', 'providers.yml');
const OUT_FILE = join(__dirname, '..', 'src', 'content', 'docs', 'architecture', 'providers.mdx');

function tierCell(tier) {
  if (!tier) return '—';
  const provider = tier.provider || '?';
  const model = tier.model || tier.alias || '?';
  return `\`${provider}/${model}\``;
}

async function main() {
  if (!existsSync(PROVIDERS_FILE)) {
    console.warn(`[gen-providers] ${PROVIDERS_FILE} not found, skipping`);
    return;
  }
  const text = await readFile(PROVIDERS_FILE, 'utf8');
  const cfg = parse(text);

  const providers = Array.isArray(cfg.providers) ? cfg.providers : [];
  const routingProfiles = cfg.routing_profiles || {};
  const defaultProfile = cfg.default_profile || cfg.default_routing_profile;

  const providerRows = providers.map((p) => {
    const id = p.id || p.name || '?';
    const label = p.label || id;
    const kind = p.kind || '—';
    const enabled = p.enabled === false ? '⛔' : '✅';
    const auth = p.api_key_env ? `\`${p.api_key_env}\`` : '—';
    const modelCount = Array.isArray(p.models) ? p.models.length : 0;
    return `| \`${id}\` | ${label} | ${kind} | ${enabled} | ${auth} | ${modelCount} |`;
  });

  const modelRows = providers.flatMap((p) =>
    (Array.isArray(p.models) ? p.models : []).map((m) => {
      const aliases = Array.isArray(m.aliases) && m.aliases.length > 0
        ? m.aliases.map((a) => `\`${a}\``).join(', ')
        : '—';
      const inPrice = m.input_price_per_1m_tokens ?? 0;
      const outPrice = m.output_price_per_1m_tokens ?? 0;
      return `| \`${p.id}\` | \`${m.name}\` | ${aliases} | $${inPrice.toFixed(2)} | $${outPrice.toFixed(2)} |`;
    }),
  );

  const profileRows = Object.entries(routingProfiles).map(([name, prof]) => {
    const isDefault = name === defaultProfile;
    return `| \`${name}\`${isDefault ? ' ✨' : ''} | ${tierCell(prof.fast)} | ${tierCell(prof.strong)} | ${tierCell(prof.fallback)} | ${prof.description ? prof.description.replace(/\|/g, '\\|') : '—'} |`;
  });

  const mdx = `---
title: Provider routing matrix
description: Auto-generated routing matrix from config/providers.yml.
---

import { Aside, Card, CardGrid } from '@astrojs/starlight/components';

<CardGrid>
  <Card title="Providers" icon="rocket">
    ${providers.length}
  </Card>
  <Card title="Routing profiles" icon="random">
    ${Object.keys(routingProfiles).length}
  </Card>
  <Card title="Default profile" icon="star">
    \`${defaultProfile || 'none'}\`
  </Card>
</CardGrid>

## Providers

| ID | Label | Kind | Enabled | Auth env var | Models |
| --- | --- | --- | :---: | --- | ---: |
${providerRows.join('\n') || '| _none_ | | | | | |'}

## Models

Prices are USD per 1M tokens.

| Provider | Model | Aliases | Input | Output |
| --- | --- | --- | ---: | ---: |
${modelRows.join('\n') || '| _none_ | | | | |'}

## Routing profiles

The default profile is highlighted with ✨.

| Profile | Fast tier | Strong tier | Fallback | Description |
| --- | --- | --- | --- | --- |
${profileRows.join('\n') || '| _none_ | | | | |'}

<Aside type="tip" title="Source">
  Generated from <code>config/providers.yml</code>. Re-run
  <code>npm run dev</code> or <code>npm run build</code> to refresh.
</Aside>
`;

  await mkdir(dirname(OUT_FILE), { recursive: true });
  await writeFile(OUT_FILE, mdx, 'utf8');
  console.log(
    `[gen-providers] wrote ${providers.length} providers, ${modelRows.length} models, ${Object.keys(routingProfiles).length} profiles`,
  );
}

main().catch((err) => {
  console.error('[gen-providers] failed:', err);
  process.exit(1);
});
