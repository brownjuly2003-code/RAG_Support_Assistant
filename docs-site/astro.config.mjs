// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://brownjuly2003-code.github.io',
  base: '/RAG_Support_Assistant',
  integrations: [
    starlight({
      title: 'RAG Support Assistant',
      description:
        'Internal codebase docs for the RAG Support Assistant — architecture, operations, plans, and research.',
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/brownjuly2003-code/RAG_Support_Assistant',
        },
      ],
      sidebar: [
        { label: 'Home', link: '/' },
        {
          label: 'Architecture',
          items: [
            { label: 'Overview', link: '/architecture/' },
            { label: 'LangGraph state machine', link: '/architecture/langgraph/' },
            { label: 'API routes catalog', link: '/architecture/routes/' },
            { label: 'Provider routing', link: '/architecture/providers/' },
            { label: 'Module layout', slug: 'guides/deprecations' },
          ],
        },
        {
          label: 'Operations',
          items: [
            { label: 'Quickstart', slug: 'guides/quickstart' },
            { label: 'Runbook', slug: 'guides/runbook' },
            { label: 'Disaster recovery', slug: 'guides/disaster-recovery' },
            { label: 'Local gate', slug: 'guides/local-gate' },
            { label: 'Windows test workflow', slug: 'guides/windows-test-workflow' },
            { label: 'Backup encryption', slug: 'guides/operations/backup-encryption' },
            { label: 'Backup restore', slug: 'guides/operations/backup-restore' },
            { label: 'Helm lint', slug: 'guides/operations/helm-lint' },
            { label: 'GraceKelly smoke', slug: 'guides/operations/gracekelly-smoke' },
          ],
        },
        {
          label: 'Plans & history',
          items: [
            { label: '2026-04-27 next steps', slug: 'guides/plans/2026-04-27-next-steps' },
            { label: '2026-05-01 backlog', slug: 'guides/plans/2026-05-01-backlog' },
            { label: 'CHANGELOG', slug: 'guides/changelog' },
            { label: 'Audit hardening 2026-04-27', slug: 'guides/session-notes-2026-04-27-hardening' },
            { label: 'Audit notes 2026-04-26', slug: 'guides/session-notes-2026-04-26-audit' },
          ],
        },
        {
          label: 'Research',
          items: [
            { label: 'RAG landscape 2026', slug: 'guides/research/rag-landscape-2026' },
            { label: 'LLM model selection', slug: 'guides/research/llm-model-selection-2025' },
            { label: 'Eval metrics 2025', slug: 'guides/research/eval-metrics-2025' },
            { label: 'Production monitoring', slug: 'guides/research/production-monitoring-2025' },
            { label: 'UI patterns', slug: 'guides/research/ui-patterns-2025' },
            { label: 'Semantic chunking AB', slug: 'guides/research/semantic_chunking_ab' },
            { label: 'Simulated model comparison', slug: 'guides/research/simulated_model_comparison' },
            { label: 'pi noninteractive hang', slug: 'guides/research/pi-coding-agent-windows-noninteractive-hang-2026-05-04' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'Errors E10–E30', slug: 'guides/errors_e10_e30' },
            { label: 'Returns policy', slug: 'guides/returns_policy' },
            { label: 'Warranty', slug: 'guides/warranty' },
            { label: 'Production hardening spec', slug: 'guides/superpowers/specs/2026-04-03-production-hardening-design' },
            { label: 'A11y axe audit 2026-04-21', slug: 'guides/a11y/axe-audit-2026-04-21' },
          ],
        },
      ],
      customCss: ['./src/assets/custom.css'],
    }),
  ],
});
