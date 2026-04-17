# Task 52 ��� DS-3: Mobile-first responsive

## Goal
Текущие страницы: 1 breakpoint (600px), desktop-first.
Добавить полноценную мобильную адаптацию: 3 breakpoints, touch-friendly targets.

## Dependencies
- task-50 (shared CSS tokens)

## Files to change
- `static/styles/components.css` — responsive utilities
- `static/chat.html` — mobile layout
- `static/help.html` — mobile layout
- `static/metrics.html` — mobile grid

---

## 1. static/styles/components.css — добавить

```css
/* Responsive breakpoints */
/* Phone: <480px, Tablet: 480-768px, Desktop: >768px */

/* Touch-friendly minimum */
@media (pointer: coarse) {
    button, a, [role="button"] {
        min-height: 44px;
        min-width: 44px;
    }
}

/* Viewport meta reminder — add to all HTML files:
   <meta name="viewport" content="width=device-width, initial-scale=1"> */
```

---

## 2. static/chat.html

Добавить viewport meta в `<head>` (если ещё нет):
```html
<meta name="viewport" content="width=device-width, initial-scale=1">
```

Добавить media queries в `<style>`:

```css
/* Tablet */
@media (max-width: 768px) {
    .sidebar {
        position: fixed;
        left: -280px;
        top: 0;
        height: 100vh;
        z-index: 100;
        transition: left var(--transition, 0.2s ease);
    }
    .sidebar.open {
        left: 0;
    }
    .sidebar-overlay {
        display: none;
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.5);
        z-index: 99;
    }
    .sidebar-overlay.active {
        display: block;
    }
}

/* Phone */
@media (max-width: 480px) {
    .header h1 { font-size: 16px; }
    .header-actions .btn-icon { width: 40px; height: 40px; }
    .input-wrapper { padding: 8px; }
    .message-content { max-width: 90%; }
    .msg-feedback .btn-feedback { min-width: 44px; min-height: 44px; }
}
```

Добавить кнопку-гамбургер для sidebar (видна только на mobile):
```html
<button class="btn-icon sidebar-toggle" id="sidebarToggle" aria-label="Открыть меню"
        style="display:none;">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="3" y1="6" x2="21" y2="6"/>
        <line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="18" x2="21" y2="18"/>
    </svg>
</button>
```

JS для toggle:
```javascript
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar = document.querySelector('.sidebar');
if (sidebarToggle && sidebar) {
    // Show toggle on mobile
    const mq = window.matchMedia('(max-width: 768px)');
    function handleMQ(e) {
        sidebarToggle.style.display = e.matches ? 'flex' : 'none';
        if (!e.matches) sidebar.classList.remove('open');
    }
    mq.addEventListener('change', handleMQ);
    handleMQ(mq);

    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
    });
}
```

---

## 3. static/metrics.html

Обновить grid для mobile:
```css
@media (max-width: 640px) {
    .metrics-grid {
        grid-template-columns: 1fr;
    }
}
@media (min-width: 641px) and (max-width: 1024px) {
    .metrics-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}
```

---

## CONSTRAINTS
- Mobile-first: базовые стили для phone, media queries для tablet/desktop
- Минимальный tap target: 44x44px на touch devices
- Sidebar toggle на ≤768px
- Не ломать desktop layout
- viewport meta на всех страницах

## DONE WHEN
- [ ] viewport meta на chat.html, help.html, metrics.html
- [ ] Sidebar скрывается на ≤768px, открывается по гамбургеру
- [ ] Кнопки ≥44px на touch-устройствах
- [ ] metrics grid → 1 column на phone, 2 на tablet
- [ ] Desktop layout не изменился
