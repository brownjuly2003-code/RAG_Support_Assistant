# Task 103 — Mobile responsiveness (breakpoints + tap targets)

## Context
Сейчас `chat.html`, `help.html`, `metrics.html`, `admin.html` имеют по
одному breakpoint ~600-640px — sidebar скрывается и всё. Нет tablet
breakpoint, tap targets часто <44px, viewport meta местами отсутствует
(особенно в legacy `templates/*.html`). Lighthouse mobile ~40.

## Goal
Mobile-first responsive для всех страниц. Три breakpoints: **480**
(phone), **768** (tablet portrait), **1024** (tablet landscape / small
desktop). Tap targets ≥44px. Viewport meta на всех страницах.
Lighthouse mobile ≥80.

## Files to change
- `static/styles/tokens.css` — добавить breakpoint custom properties
  (опционально — CSS media queries всё равно нужны в components.css)
- `static/styles/components.css` — responsive правила для кнопок (min-height
  44px mobile), формы, navigation
- `static/chat.html` — 3 breakpoints вместо 1; sidebar drawer на mobile с
  overlay; input area sticky bottom с safe-area-inset-bottom
- `static/help.html`, `static/metrics.html`, `static/admin.html` — те же
  3 breakpoints, tap targets
- `templates/*.html` — добавить `<meta name="viewport" content="width=device-width, initial-scale=1">` везде где нет
- Новый `tests/test_mobile_responsive.py` — smoke test через
  playwright/selenium headless: открыть chat.html в 375px viewport →
  основные элементы видны, textarea доступна, sidebar drawer работает.
  Если playwright не установлен — пропустить тест с `pytest.importorskip`.

## Implementation sketch

### CSS structure (components.css)
```css
/* mobile-first base (≤480px phone) */
.btn { min-height: 44px; padding: 12px 16px; }
.chat-sidebar { position: fixed; transform: translateX(-100%); }
.chat-sidebar.open { transform: translateX(0); }

@media (min-width: 768px) {
  .chat-layout { grid-template-columns: 260px 1fr; }
  .chat-sidebar { position: static; transform: none; }
}

@media (min-width: 1024px) {
  .chat-layout { grid-template-columns: 280px 1fr 320px; } /* + source panel */
}
```

### Safe area для notch (chat.html)
```css
.chat-input-area {
  padding-bottom: max(12px, env(safe-area-inset-bottom));
}
```

### Drawer на mobile (chat.html)
Sidebar toggle button (hamburger) — показывать только <768px. Клик
открывает drawer + dim backdrop. Esc / backdrop click — закрывает.

## CONSTRAINTS
- Не ломать существующий desktop layout — desktop ≥1024px должен быть
  пиксель-в-пиксель как сейчас
- Tap target 44×44 — проверить ВСЕ clickable элементы (особенно feedback
  👍👎 кнопки, copy, retry, close)
- Source panel из task-102 на mobile = full-screen overlay (не сайдпанель)

## Verification
1. Chrome DevTools mobile emulator: iPhone SE (375), iPad (768), laptop (1280)
2. Lighthouse mobile audit на `chat.html`: score ≥80
3. Keyboard nav работает на всех брейкпойнтах (Tab через все controls)

## DONE WHEN
- [ ] 3 breakpoints (480/768/1024) во всех 4 static-страницах
- [ ] viewport meta во всех `templates/*.html`
- [ ] Все tap targets ≥44×44
- [ ] Lighthouse mobile ≥80 на chat.html
- [ ] 223+ passed (1 новый mobile test или skip если без playwright)
- [ ] Screenshots: 375px, 768px, 1024px в PR
- [ ] Commit: "Mobile-first responsive with 3 breakpoints (task-103)"
