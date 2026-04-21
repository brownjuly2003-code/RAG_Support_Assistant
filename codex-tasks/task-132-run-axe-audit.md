# Task 132 — Run axe-core a11y audit (task-104 follow-up)

## Goal
Выполнить настоящий axe-core accessibility audit на всех UI-страницах и закрыть выявленные issues до severity "serious". Сейчас task-104 принят только как static CSS review — реального axe-запуска не было, нет severity-report'а.

## Context
- Repo: `D:\RAG_Support_Assistant`.
- Follow-up на task-104 (`codex-tasks/Archive/task-104-wcag-audit.md`).
- UI-страницы для аудита:
  - `/static/chat.html` — public user-facing chat
  - `/static/help.html` — help page
  - `/static/admin.html` — admin UI
  - `/static/metrics.html` — live metrics dashboard
  - `/static/agent.html` — agent copilot (task-106)
  - `/static/analytics.html` — analytics dashboard (task-117)
  - `/static/login.html` — SSO login page (task-112)
  - Jinja templates: `templates/index.html`, `ask_result.html`, `escalations.html`, `traces.html`, `trace_detail.html`
- Target: **WCAG 2.1 AA**, без "serious" / "critical" issues. "Minor" / "moderate" — можно фиксить позже отдельными task'ами, но задокументировать в отчёте.

## Deliverables
1. **Запуск audit'а**:
   - Инструмент: `@axe-core/cli` (npm, позволяет CLI прогон без Playwright), или `axe-core` через Playwright (если Playwright уже в dev-deps). Выбрать CLI — проще.
   - Установить (НЕ в основные deps): `npm install -g @axe-core/cli` или `npx @axe-core/cli`.
   - Запустить dev server: `uvicorn api.app:app --host 127.0.0.1 --port 8000` в фоне.
   - Для каждой страницы: `axe http://127.0.0.1:8000/<path>` → JSON result.
   - Jinja templates: рендерить через dev endpoint или сохранить static HTML-snapshot для аудита.
2. **Отчёт** `docs/a11y/axe-audit-YYYY-MM-DD.md`:
   ```
   # Axe audit — 2026-04-XX
   
   ## Summary
   - Pages scanned: N
   - Violations: total X (critical: 0, serious: 0, moderate: Y, minor: Z)
   - WCAG 2.1 AA status: PASS / FAIL
   
   ## Page: /static/chat.html
   ### Violations
   - [rule-id] — description — severity — elements affected
   - Fixed in commit? / TODO for follow-up task
   
   ## Page: /static/admin.html
   ...
   ```
3. **Фиксы** для критических и серьёзных issues:
   - ARIA labels где отсутствуют (`<button>` без `aria-label`, `<input>` без `<label for>`)
   - Contrast ratios (автоматически детектится axe).
   - Keyboard navigation (focus order, `tabindex` sanity).
   - Alt-text для `<img>`.
   - `<html lang="...">` атрибут.
4. **Не-критические** — список TODO в отчёте, НЕ фиксить в рамках этого таска.
5. **Manual keyboard test** (обязательно!):
   - Пройти Tab от начала до конца каждой страницы — все interactive элементы достижимы.
   - `Esc` закрывает модалки.
   - Enter/Space активируют buttons/links.
   - Зафиксировать в отчёте pass/fail.
6. **README update** — секция "Accessibility" со ссылкой на последний audit report и текущий статус.

## Acceptance
- Отчёт `docs/a11y/axe-audit-<date>.md` существует.
- Количество "critical" + "serious" violations после фиксов = **0** на каждой scanned странице.
- Manual keyboard test пройден (зафиксирован в отчёте).
- `pytest tests/test_a11y.py` — зелёный (если тесты используют axe-playwright — они должны пройти реальный axe-прогон, не mock).
- ruff clean, `pytest tests/ -q` ≥ 293 passed.
- README обновлён с a11y статусом.

## Notes
- **Axe-core в CI** — OUT of scope этого таска. Отдельный follow-up: добавить axe в `.github/workflows/ci.yml` как e2e job. Зафиксировать в отчёте как "future work".
- **Screen reader testing** (NVDA / VoiceOver) — не требуется в этом таске, только автоматический axe + keyboard.
- Если страница требует auth (admin.html, analytics.html) — использовать test JWT или axe run после login flow (Playwright).
- Для Jinja templates — можно рендерить через `fastapi.testclient` + сохранить в temp HTML, затем `axe path/to/local.html`.
- "Critical" = нарушение blocking WCAG. "Serious" = significant barrier. "Moderate" / "minor" — UX degradation, не blocker.
- НЕ рефакторить UI целиком — точечные фиксы под violations.
