# Task 67 — MC-3: Embeddable chat widget

## Goal
`<script>` snippet для встраивания чат-виджета на любой сайт.
iframe + postMessage API для изоляции.

## Files to create
- `static/widget.js` — embed script (клиент подключает на свой сайт)
- `static/widget.html` — iframe-содержимое (минимальный чат)

---

## 1. static/widget.js

```javascript
/**
 * RAG Support Assistant — Embeddable Chat Widget
 *
 * Usage:
 *   <script src="https://your-domain.com/static/widget.js"
 *           data-api="https://your-domain.com"
 *           data-position="bottom-right"
 *           data-title="Поддержка">
 *   </script>
 */
(function() {
    'use strict';

    var script = document.currentScript;
    var apiBase = script.getAttribute('data-api') || '';
    var position = script.getAttribute('data-position') || 'bottom-right';
    var title = script.getAttribute('data-title') || 'Поддержка';

    // Create toggle button
    var btn = document.createElement('button');
    btn.id = 'rag-widget-toggle';
    btn.setAttribute('aria-label', title);
    btn.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="white"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
    btn.style.cssText = 'position:fixed;' + (position === 'bottom-left' ? 'left:20px;' : 'right:20px;') + 'bottom:20px;width:56px;height:56px;border-radius:28px;background:#4a90d9;border:none;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,0.2);z-index:99999;display:flex;align-items:center;justify-content:center;';

    // Create iframe container
    var container = document.createElement('div');
    container.id = 'rag-widget-container';
    container.style.cssText = 'position:fixed;' + (position === 'bottom-left' ? 'left:20px;' : 'right:20px;') + 'bottom:86px;width:380px;height:520px;max-height:80vh;border-radius:12px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,0.2);z-index:99998;display:none;';

    var iframe = document.createElement('iframe');
    iframe.src = apiBase + '/static/widget.html';
    iframe.style.cssText = 'width:100%;height:100%;border:none;';
    iframe.setAttribute('title', title);
    container.appendChild(iframe);

    document.body.appendChild(btn);
    document.body.appendChild(container);

    // Toggle
    var isOpen = false;
    btn.addEventListener('click', function() {
        isOpen = !isOpen;
        container.style.display = isOpen ? 'block' : 'none';
        btn.innerHTML = isOpen
            ? '<svg viewBox="0 0 24 24" width="24" height="24" fill="white"><line x1="18" y1="6" x2="6" y2="18" stroke="white" stroke-width="2"/><line x1="6" y1="6" x2="18" y2="18" stroke="white" stroke-width="2"/></svg>'
            : '<svg viewBox="0 0 24 24" width="24" height="24" fill="white"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
    });

    // Listen for messages from iframe
    window.addEventListener('message', function(e) {
        if (e.data && e.data.type === 'rag-widget-close') {
            isOpen = false;
            container.style.display = 'none';
        }
        if (e.data && e.data.type === 'rag-widget-resize') {
            container.style.height = Math.min(e.data.height || 520, window.innerHeight * 0.8) + 'px';
        }
    });
})();
```

---

## 2. static/widget.html

Минимальный чат-виджет (standalone HTML):

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Поддержка</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; height: 100vh; display: flex; flex-direction: column; background: #fff; color: #333; }
        .widget-header { padding: 12px 16px; background: #4a90d9; color: #fff; font-weight: 600; display: flex; justify-content: space-between; align-items: center; }
        .widget-messages { flex: 1; overflow-y: auto; padding: 12px; }
        .widget-msg { margin-bottom: 8px; padding: 8px 12px; border-radius: 12px; max-width: 85%; font-size: 13px; line-height: 1.4; }
        .widget-msg.user { background: #4a90d9; color: #fff; margin-left: auto; }
        .widget-msg.assistant { background: #f0f2f5; }
        .widget-input { display: flex; border-top: 1px solid #e0e0e0; padding: 8px; gap: 8px; }
        .widget-input input { flex: 1; border: 1px solid #e0e0e0; border-radius: 8px; padding: 8px 12px; font-size: 14px; outline: none; }
        .widget-input input:focus { border-color: #4a90d9; }
        .widget-input button { padding: 8px 16px; background: #4a90d9; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
        .typing { color: #999; font-style: italic; padding: 4px 12px; }
    </style>
</head>
<body>
    <div class="widget-header">
        <span>Поддержка</span>
    </div>
    <div class="widget-messages" id="messages">
        <div class="widget-msg assistant">Здравствуйте! Задайте ваш вопрос.</div>
    </div>
    <div class="widget-input">
        <input type="text" id="input" placeholder="Напишите вопрос..." aria-label="Ваш вопрос">
        <button id="sendBtn" aria-label="Отправить">→</button>
    </div>

    <script>
        var API_BASE = (window.location !== window.parent.location)
            ? new URL(document.referrer).origin
            : window.location.origin;

        // Override from parent script data-api attribute
        try {
            var parentScript = window.parent.document.querySelector('script[data-api]');
            if (parentScript) API_BASE = parentScript.getAttribute('data-api');
        } catch (e) {}

        // Use same origin as fallback
        if (!API_BASE) API_BASE = window.location.origin;

        var messages = document.getElementById('messages');
        var input = document.getElementById('input');
        var sendBtn = document.getElementById('sendBtn');

        function addMsg(role, text) {
            var div = document.createElement('div');
            div.className = 'widget-msg ' + role;
            div.textContent = text;
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        }

        async function send() {
            var q = input.value.trim();
            if (!q) return;
            input.value = '';
            addMsg('user', q);

            var typing = document.createElement('div');
            typing.className = 'typing';
            typing.textContent = 'Печатает...';
            messages.appendChild(typing);

            try {
                var resp = await fetch(API_BASE + '/api/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question: q }),
                });
                var data = await resp.json();
                typing.remove();
                addMsg('assistant', data.answer || 'Нет ответа');
            } catch (err) {
                typing.remove();
                addMsg('assistant', 'Ошибка подключения. Попробуйте позже.');
            }
        }

        sendBtn.addEventListener('click', send);
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') send();
        });
    </script>
</body>
</html>
```

---

## CONSTRAINTS
- Только 2 статических файла: widget.js + widget.html
- Widget изолирован в iframe (безопасность)
- `data-api` атрибут на script tag задаёт API URL
- Работает с CORS (нужен task-39)
- Не ломать существующий chat.html

## DONE WHEN
- [ ] `static/widget.js` — embed script с toggle button
- [ ] `static/widget.html` — standalone мини-чат в iframe
- [ ] `<script src="/static/widget.js" data-api="http://localhost:8000">` — работает
- [ ] Кнопка в правом нижнем углу → открывает чат
- [ ] Вопрос → POST /api/ask → ответ в виджете
