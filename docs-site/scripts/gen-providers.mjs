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
const OUT_FILE_EN = join(__dirname, '..', 'src', 'content', 'docs', 'architecture', 'providers.mdx');
const OUT_FILE_RU = join(__dirname, '..', 'src', 'content', 'docs', 'ru', 'architecture', 'providers.mdx');

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

  function buildRows(locale) {
    const disabledLabel = locale === 'ru' ? 'выключен' : 'disabled';
    const enabledLabel = locale === 'ru' ? 'включён' : 'enabled';

    const providerRows = providers.map((p) => {
      const id = p.id || p.name || '?';
      const label = p.label || id;
      const kind = p.kind || '—';
      const enabled = p.enabled === false ? disabledLabel : enabledLabel;
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

    const defaultMarker = locale === 'ru' ? ' _(по умолчанию)_' : ' _(default)_';
    const profileRows = Object.entries(routingProfiles).map(([name, prof]) => {
      const marker = name === defaultProfile ? defaultMarker : '';
      return `| \`${name}\`${marker} | ${tierCell(prof.fast)} | ${tierCell(prof.strong)} | ${tierCell(prof.fallback)} | ${prof.description ? prof.description.replace(/\|/g, '\\|') : '—'} |`;
    });

    return { providerRows, modelRows, profileRows };
  }

  function renderMdx(locale) {
    const { providerRows, modelRows, profileRows } = buildRows(locale);
    const L = locale === 'ru'
      ? {
          title: 'Матрица маршрутизации провайдеров',
          description: 'Автогенерируемая матрица маршрутизации из config/providers.yml.',
          providersCard: 'Провайдеров',
          profilesCard: 'Профилей маршрутизации',
          defaultCard: 'Профиль по умолчанию',
          providersHeading: 'Провайдеры',
          providersHeader: '| ID | Метка | Тип | Включён | Auth env var | Моделей |',
          providersEmpty: '| _нет_ | | | | | |',
          modelsHeading: 'Модели',
          modelsIntro: 'Цены в USD за 1M токенов.',
          modelsHeader: '| Провайдер | Модель | Алиасы | Вход | Выход |',
          modelsEmpty: '| _нет_ | | | | |',
          profilesHeading: 'Профили маршрутизации',
          profilesIntro: 'Профиль по умолчанию помечен _(по умолчанию)_.',
          profilesHeader: '| Профиль | Быстрый тир | Сильный тир | Запасной | Описание |',
          profilesEmpty: '| _нет_ | | | | |',
          sourceTitle: 'Источник',
          sourceBody: `Сгенерировано из <code>config/providers.yml</code>. Перезапустите\n  <code>npm run dev</code> или <code>npm run build</code> для обновления.`,
          noneLabel: 'нет',
        }
      : {
          title: 'Provider routing matrix',
          description: 'Auto-generated routing matrix from config/providers.yml.',
          providersCard: 'Providers',
          profilesCard: 'Routing profiles',
          defaultCard: 'Default profile',
          providersHeading: 'Providers',
          providersHeader: '| ID | Label | Kind | Enabled | Auth env var | Models |',
          providersEmpty: '| _none_ | | | | | |',
          modelsHeading: 'Models',
          modelsIntro: 'Prices are USD per 1M tokens.',
          modelsHeader: '| Provider | Model | Aliases | Input | Output |',
          modelsEmpty: '| _none_ | | | | |',
          profilesHeading: 'Routing profiles',
          profilesIntro: 'The default profile is marked _(default)_.',
          profilesHeader: '| Profile | Fast tier | Strong tier | Fallback | Description |',
          profilesEmpty: '| _none_ | | | | |',
          sourceTitle: 'Source',
          sourceBody: `Generated from <code>config/providers.yml</code>. Re-run\n  <code>npm run dev</code> or <code>npm run build</code> to refresh.`,
          noneLabel: 'none',
        };

    return `---
title: ${L.title}
description: ${L.description}
---

import { Aside } from '@astrojs/starlight/components';

<div class="q-cardgrid q-cardgrid--accent">
  <article class="q-card">
    <h3 class="q-title">
      <span class="q-label">${L.providersCard}</span>
    </h3>
    <div class="q-body"><p>${providers.length}</p></div>
  </article>
  <article class="q-card">
    <h3 class="q-title">
      <span class="q-label">${L.profilesCard}</span>
    </h3>
    <div class="q-body"><p>${Object.keys(routingProfiles).length}</p></div>
  </article>
  <article class="q-card">
    <h3 class="q-title">
      <span class="q-label">${L.defaultCard}</span>
    </h3>
    <div class="q-body"><p><code>${defaultProfile || L.noneLabel}</code></p></div>
  </article>
</div>

## ${L.providersHeading}

${L.providersHeader}
| --- | --- | --- | :---: | --- | ---: |
${providerRows.join('\n') || L.providersEmpty}

## ${L.modelsHeading}

${L.modelsIntro}

${L.modelsHeader}
| --- | --- | --- | ---: | ---: |
${modelRows.join('\n') || L.modelsEmpty}

## ${L.profilesHeading}

${L.profilesIntro}

${L.profilesHeader}
| --- | --- | --- | --- | --- |
${profileRows.join('\n') || L.profilesEmpty}

<Aside type="tip" title="${L.sourceTitle}">
  ${L.sourceBody}
</Aside>
`;
  }

  for (const [out, locale] of [[OUT_FILE_EN, 'en'], [OUT_FILE_RU, 'ru']]) {
    await mkdir(dirname(out), { recursive: true });
    await writeFile(out, renderMdx(locale), 'utf8');
  }
  const enModelsCount = buildRows('en').modelRows.length;
  console.log(
    `[gen-providers] wrote ${providers.length} providers, ${enModelsCount} models, ${Object.keys(routingProfiles).length} profiles (en + ru)`,
  );
}

main().catch((err) => {
  console.error('[gen-providers] failed:', err);
  process.exit(1);
});
