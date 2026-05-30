// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import rehypeMermaid from 'rehype-mermaid';

const SITE_URL = 'https://brownjuly2003-code.github.io/RAG_Support_Assistant';
const OG_IMAGE = `${SITE_URL}/og-image.png`;
const REPO_URL = 'https://github.com/brownjuly2003-code/RAG_Support_Assistant';

const personLd = {
  '@context': 'https://schema.org',
  '@type': 'Person',
  '@id': `${SITE_URL}/#julia-edomskikh`,
  name: 'Julia Edomskikh',
  email: 'uedomskikh@gmail.com',
  jobTitle: 'Senior Data Analyst / Data Engineer',
  url: 'https://github.com/brownjuly2003-code',
  sameAs: ['https://github.com/brownjuly2003-code'],
};

const projectLd = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareSourceCode',
  '@id': `${SITE_URL}/#project`,
  name: 'RAG Support Assistant',
  description:
    'LangGraph-based RAG service with offline evaluation, observability, and a reproducible E20 walkthrough.',
  url: SITE_URL,
  codeRepository: REPO_URL,
  programmingLanguage: 'Python',
  applicationCategory: 'BusinessApplication',
  license: 'https://opensource.org/licenses/MIT',
  author: { '@id': `${SITE_URL}/#julia-edomskikh` },
  image: OG_IMAGE,
};

/** @type {Array<{ tag: 'meta' | 'script'; attrs?: Record<string, string>; content?: string }>} */
const headTags = [
  { tag: 'meta', attrs: { property: 'og:type', content: 'website' } },
  { tag: 'meta', attrs: { property: 'og:site_name', content: 'RAG Support Assistant' } },
  { tag: 'meta', attrs: { property: 'og:image', content: OG_IMAGE } },
  { tag: 'meta', attrs: { property: 'og:image:width', content: '1200' } },
  { tag: 'meta', attrs: { property: 'og:image:height', content: '630' } },
  { tag: 'meta', attrs: { property: 'og:image:type', content: 'image/png' } },
  {
    tag: 'meta',
    attrs: {
      property: 'og:image:alt',
      content: 'RAG Support Assistant — LangGraph retrieval, observability, offline evaluation.',
    },
  },
  { tag: 'meta', attrs: { name: 'twitter:card', content: 'summary_large_image' } },
  { tag: 'meta', attrs: { name: 'twitter:image', content: OG_IMAGE } },
  { tag: 'meta', attrs: { name: 'twitter:image:alt', content: 'RAG Support Assistant — LangGraph retrieval, observability, offline evaluation.' } },
  { tag: 'meta', attrs: { name: 'author', content: 'Julia Edomskikh' } },
  {
    tag: 'script',
    attrs: { type: 'application/ld+json' },
    content: JSON.stringify(personLd),
  },
  {
    tag: 'script',
    attrs: { type: 'application/ld+json' },
    content: JSON.stringify(projectLd),
  },
];

export default defineConfig({
  site: 'https://brownjuly2003-code.github.io',
  base: '/RAG_Support_Assistant',
  markdown: {
    syntaxHighlight: { type: 'shiki', excludeLangs: ['mermaid'] },
    rehypePlugins: [[rehypeMermaid, { strategy: 'inline-svg' }]],
  },
  integrations: [
    starlight({
      title: {
        en: 'RAG Support Assistant',
        ru: 'RAG Support Assistant',
      },
      description:
        'Public docs for RAG Support Assistant: product examples, architecture, local setup, and API routes.',
      head: headTags,
      components: {
        Head: './src/components/Head.astro',
      },
      defaultLocale: 'root',
      locales: {
        root: { label: 'English', lang: 'en' },
        ru: { label: 'Русский', lang: 'ru' },
      },
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/brownjuly2003-code/RAG_Support_Assistant',
        },
      ],
      sidebar: [
        { label: 'Home', translations: { ru: 'Главная' }, slug: 'index' },
        { label: 'What it does', translations: { ru: 'Что делает' }, slug: 'examples' },
        // Все верхнеуровневые пункты сайдбара имеют RU-зеркала:
        // Architecture/* — через генераторы scripts/gen-*.mjs, остальные —
        // как hand-written MDX под src/content/docs/ru/.
        { label: 'Reproduce E20', translations: { ru: 'Воспроизвести E20' }, slug: 'reproduce-e20' },
        { label: 'Architecture', translations: { ru: 'Архитектура' }, slug: 'architecture' },
        { label: 'Evaluation', translations: { ru: 'Оценка' }, slug: 'evaluation' },
        { label: 'Try locally', translations: { ru: 'Запустить локально' }, slug: 'guides/quickstart' },
        { label: 'API', translations: { ru: 'API' }, slug: 'architecture/routes' },
      ],
      customCss: ['./src/assets/custom.css'],
    }),
  ],
});
