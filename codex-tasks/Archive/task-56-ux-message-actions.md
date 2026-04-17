# Task 56 — UX-4: Message actions — copy, retry, timestamps

## Goal
Добавить три UX-улучшения на сообщения в чате:
1. Copy-to-clipboard на ответах бота
2. Retry для упавших сообщений
3. Timestamps на каждом сообщении

## Files to change
- `static/chat.html` — JS + CSS

---

## 1. Timestamps

В функции `addMessage()`, добавить timestamp после avatar/content:

```javascript
const timestamp = document.createElement('div');
timestamp.className = 'msg-timestamp';
timestamp.textContent = new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
content.appendChild(timestamp);
```

CSS:
```css
.msg-timestamp {
    font-size: 11px;
    color: var(--text-secondary, #999);
    margin-top: 4px;
    text-align: right;
}
```

---

## 2. Copy-to-clipboard

Добавить кнопку copy на ответы бота (`role === 'assistant'`):

В `addMessage()`, после формирования `content`:

```javascript
if (role === 'assistant' && text) {
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'msg-actions';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn-action';
    copyBtn.title = 'Копировать';
    copyBtn.setAttribute('aria-label', 'Копировать ответ');
    copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
    copyBtn.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(text);
            copyBtn.innerHTML = '✓';
            setTimeout(() => {
                copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
            }, 2000);
        } catch (err) {
            console.warn('Copy failed:', err);
        }
    });
    actionsDiv.appendChild(copyBtn);
    content.appendChild(actionsDiv);
}
```

CSS:
```css
.msg-actions {
    display: flex;
    gap: 4px;
    margin-top: 4px;
    opacity: 0;
    transition: opacity 0.2s;
}
.message:hover .msg-actions { opacity: 1; }

.btn-action {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-secondary, #999);
    cursor: pointer;
    padding: 0;
}
.btn-action:hover {
    background: var(--bg-secondary, #f0f2f5);
    color: var(--text-primary, #333);
}
```

---

## 3. Retry для ошибок

В `sendMessage()`, при ошибке — добавить retry кнопку:

В catch-блоке, после отображения ошибки:

```javascript
// При ошибке добавить кнопку retry
const lastMsg = chatMessages.lastElementChild;
if (lastMsg) {
    const retryBtn = document.createElement('button');
    retryBtn.className = 'btn-action btn-retry';
    retryBtn.textContent = 'Повторить';
    retryBtn.setAttribute('aria-label', 'Повторить отправку');
    retryBtn.addEventListener('click', () => {
        lastMsg.remove();  // убрать сообщение об ошибке
        questionInput.value = originalQuestion;
        sendMessage();
    });
    const actions = lastMsg.querySelector('.msg-actions') || document.createElement('div');
    actions.className = 'msg-actions';
    actions.style.opacity = '1';
    actions.appendChild(retryBtn);
    lastMsg.querySelector('.message-content')?.appendChild(actions);
}
```

CSS:
```css
.btn-retry {
    width: auto;
    padding: 4px 12px;
    font-size: 12px;
    border: 1px solid var(--border, #e0e0e0);
    border-radius: 4px;
    color: var(--accent, #4a90d9);
}
```

---

## CONSTRAINTS
- Изменить только `static/chat.html`
- Copy использует `navigator.clipboard.writeText` (HTTPS или localhost)
- Timestamps в формате HH:MM (ru-RU locale)
- Retry сохраняет оригинальный вопрос
- Actions видны только при hover (кроме retry — always visible)

## DONE WHEN
- [ ] Каждое сообщение показывает timestamp (HH:MM)
- [ ] Hover на ответ бота → кнопка copy
- [ ] Click copy → текст в clipboard, иконка меняется на ✓
- [ ] Ошибка → кнопка "Повторить" (always visible)
- [ ] Click retry → повторная отправка оригинального вопроса
