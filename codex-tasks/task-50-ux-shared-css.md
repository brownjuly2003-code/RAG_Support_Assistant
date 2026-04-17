# Task 50 — DS-1: Shared CSS design system

## Goal
Все страницы (chat.html, help.html, metrics.html) имеют свой inline CSS.
chat.html — 673 строки CSS. Нет единой палитры, spacing, typography.
Создать `static/styles/tokens.css` + `static/styles/components.css` и подключить ко всем страницам.

## Files to create
- `static/styles/tokens.css` — CSS custom properties (colors, spacing, typography, shadows)
- `static/styles/components.css` — shared компоненты (buttons, cards, badges, forms)

## Files to change
- `static/chat.html` — подключить shared CSS, убрать дублирующие переменные
- `static/help.html` — подключить shared CSS
- `static/metrics.html` — подключ��ть shared CSS

---

## 1. static/styles/tokens.css

```css
/* Design tokens — single source of truth for all pages */
:root {
    /* Colors — Light */
    --color-bg-primary: #ffffff;
    --color-bg-secondary: #f0f2f5;
    --color-bg-chat: #fafafa;
    --color-text-primary: #1a1a2e;
    --color-text-secondary: #555770;
    --color-accent: #4a90d9;
    --color-accent-hover: #3a7bc8;
    --color-border: #e0e0e0;
    --color-success: #28a745;
    --color-warning: #ffc107;
    --color-danger: #dc3545;

    /* Spacing — 4px base scale */
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-5: 20px;
    --space-6: 24px;
    --space-8: 32px;
    --space-10: 40px;
    --space-12: 48px;

    /* Typography */
    --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --font-mono: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    --font-size-xs: 12px;
    --font-size-sm: 13px;
    --font-size-base: 14px;
    --font-size-md: 15px;
    --font-size-lg: 18px;
    --font-size-xl: 20px;
    --font-size-2xl: 24px;
    --font-size-3xl: 32px;
    --line-height: 1.5;

    /* Radius */
    --radius-sm: 6px;
    --radius: 12px;
    --radius-lg: 16px;
    --radius-full: 9999px;

    /* Shadows */
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
    --shadow: 0 2px 8px rgba(0,0,0,0.08);
    --shadow-lg: 0 4px 16px rgba(0,0,0,0.12);

    /* Transitions */
    --transition: 0.2s ease;
}

/* Dark theme */
[data-theme="dark"] {
    --color-bg-primary: #1a1a2e;
    --color-bg-secondary: #16213e;
    --color-bg-chat: #0f1729;
    --color-text-primary: #e0e0e0;
    --color-text-secondary: #b0b4c8; /* Improved contrast vs #a0a4b8 */
    --color-accent: #5b9ee6;
    --color-accent-hover: #7ab3f0;
    --color-border: #2a2a4a;
}
```

---

## 2. static/styles/components.css

```css
/* Shared components */

/* Reset */
*, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: var(--font-family);
    font-size: var(--font-size-base);
    line-height: var(--line-height);
    color: var(--color-text-primary);
    background: var(--color-bg-primary);
}

/* Buttons */
.btn {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-4);
    border: none;
    border-radius: var(--radius-sm);
    font-size: var(--font-size-base);
    cursor: pointer;
    transition: background var(--transition), color var(--transition);
}

.btn-primary {
    background: var(--color-accent);
    color: white;
}

.btn-primary:hover {
    background: var(--color-accent-hover);
}

.btn-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    padding: 0;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-secondary);
    cursor: pointer;
    transition: background var(--transition), color var(--transition);
}

.btn-icon:hover {
    background: var(--color-bg-secondary);
    color: var(--color-text-primary);
}

/* Focus indicators — WCAG AA */
:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
}

/* Cards */
.card {
    background: var(--color-bg-primary);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    padding: var(--space-4);
    box-shadow: var(--shadow-sm);
}

/* Badges */
.badge {
    display: inline-flex;
    align-items: center;
    padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-full);
    font-size: var(--font-size-xs);
    font-weight: 600;
}

.badge-success { background: #e6f4ea; color: #1e7e34; }
.badge-warning { background: #fff3cd; color: #856404; }
.badge-danger  { background: #f8d7da; color: #721c24; }

[data-theme="dark"] .badge-success { background: #1e3a2a; color: #82d99e; }
[data-theme="dark"] .badge-warning { background: #3a3520; color: #f0d060; }
[data-theme="dark"] .badge-danger  { background: #3a1c20; color: #f09090; }
```

---

## 3. Подключить к страницам

В `<head>` каждого HTML-файла (chat.html, help.html, metrics.html) добавить перед `<style>`:

```html
<link rel="stylesheet" href="/static/styles/tokens.css">
<link rel="stylesheet" href="/static/styles/components.css">
```

НЕ удалять inline `<style>` блоки сейчас — они будут постепенно мигрированы.
Shared tokens автоматически переопределят дублирующие CSS variables.

---

## CONSTRAINTS
- Создать 2 CSS файла, подключить к 3 HTML-страницам
- НЕ удалять inline CSS из страниц (будет в следующих задачах)
- Dark mode токены улучшают contrast (WCAG AA): `--color-text-secondary` → `#b0b4c8`
- `:focus-visible` добавляет focus indicators
- `--space-*` и `--font-size-*` на единой шкале (4px base)

## DONE WHEN
- [ ] `static/styles/tokens.css` создан с CSS custom properties
- [ ] `static/styles/components.css` создан с shared компонентами
- [ ] Все 3 HTML-страницы подключают оба CSS
- [ ] Dark mode контраст `--color-text-secondary` ≥ 4.5:1 на `--color-bg-chat`
- [ ] `:focus-visible` стили видны при Tab-навигации
