# Task 104 — WCAG AA audit via axe-core + fix criticals

## Context
По аудиту `rec.md` у проекта 10+ HIGH accessibility проблем: labels
отсутствуют, SVG-buttons без aria-label, focus indicators invisible,
viewport meta не везде. Коммерческие SaaS-продукты обязательно пасуют
WCAG AA. axe-core в тестах отсутствует.

Частично уже сделано в production-hardening: chat.html имеет `aria-label`
на escalate/theme/sidebar, `role="dialog"` на модалках. Но систематической
проверки не было.

## Goal
Добавить axe-core smoke-тест в suite. Зафиксить все **critical** и
**serious** violations. `moderate/minor` — опционально (не блокер).

## Files to change
- `requirements.txt` — добавить `axe-core-python` или использовать
  playwright + `@axe-core/playwright` (JS-нативный). Предпочтительно
  playwright — он уже может потребоваться для task-103.
- `tests/test_a11y.py` — новый файл: прогнать axe на каждой static-странице
  (chat, help, metrics, admin, widget, index) + templates/*.html
- Фиксы в `static/*.html`, `templates/*.html` — см. список ниже
- `static/styles/components.css` — `:focus-visible` стили для всех
  interactive элементов

## Known violations to fix (из rec.md §4.1)

| Problem | File | Fix |
|---------|------|-----|
| No `<label for>` у form inputs | index.html:72-76 | Add `<label for="entity-id">ID:</label>` |
| Textarea без label | chat.html | Wrap in `<form>`, add `<label class="sr-only" for="chat-input">Сообщение</label>` |
| Dropzone не keyboard-accessible | chat.html upload | `tabindex="0"`, `role="button"`, `aria-label="Загрузить документы"`, Enter/Space handler |
| Нет focus indicators | все | Global `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` |
| Нет viewport meta | templates/*.html | `<meta name="viewport" content="width=device-width, initial-scale=1">` (совместно с task-103) |
| SVG-buttons без aria | chat.html некоторые | Audit → добавить `aria-label` к каждому |
| Table без `scope` | templates/*.html | `<th scope="col">` / `<th scope="row">` |
| Focus trap в upload modal | chat.html:1231 | On open: save activeElement, focus first input. On close: restore. Tab-cycle внутри modal. |

## Implementation sketch

### tests/test_a11y.py
```python
import subprocess, json
from pathlib import Path
import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

PAGES = ["chat.html", "help.html", "metrics.html", "admin.html"]

@pytest.mark.parametrize("page", PAGES)
def test_axe_no_critical_violations(page, tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        pg = ctx.new_page()
        pg.goto(f"file://{Path('static').resolve() / page}")
        # inject axe
        pg.add_script_tag(path="node_modules/axe-core/axe.min.js")
        results = pg.evaluate("async () => await axe.run()")
        criticals = [v for v in results["violations"] if v["impact"] in ("critical", "serious")]
        assert not criticals, f"A11y violations: {json.dumps(criticals, indent=2)}"
        browser.close()
```

Если Node/axe не установлены в dev-окружении — тест пропускается
(skip с "axe-core not installed").

## CONSTRAINTS
- Не менять визуальный дизайн — только a11y attributes + focus styles
- Focus indicator должен быть visible И не ломать дизайн (use `:focus-visible`
  а не `:focus` — не активируется при mouse click)
- `sr-only` class для visually-hidden labels: стандартный паттерн

## DONE WHEN
- [ ] axe-core runs в CI (или локальный opt-in через playwright)
- [ ] 0 critical + 0 serious violations на всех 4 основных страницах
- [ ] `:focus-visible` стили применены глобально
- [ ] Keyboard nav: Tab проходит все controls без мёртвых зон
- [ ] Manual screen reader test (NVDA/VoiceOver) — ответ читается, citations
      анонсируются как "button, цитата 1"
- [ ] 225+ passed (1 новый parametrized test × 4 pages = 4 test cases)
- [ ] Commit: "WCAG AA compliance: axe-core audit + fix criticals (task-104)"
