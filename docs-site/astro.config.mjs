// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import rehypeMermaid from 'rehype-mermaid';

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
