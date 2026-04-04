# Task 16 — Session history sidebar

## Goal
Добавить боковую панель со списком активных сессий — пользователь может переключаться
между разговорами без потери контекста.

## Files to change
- `api/app.py` — добавить `GET /api/sessions` (список сессий)
- `static/chat.html` — добавить sidebar

---

## 1. api/app.py

### 1a. Добавить route GET /api/sessions (рядом с существующими session-маршрутами)

```python
class SessionInfo(BaseModel):
    session_id: str
    message_count: int

@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions() -> list[SessionInfo]:
    """Вернуть список активных сессий (только те, что в памяти)."""
    result = []
    for sid, session in list(_sessions.items()):
        if hasattr(session, "_history"):
            count = len(session._history)
        elif isinstance(session, dict):
            count = len(session.get("history", []))
        else:
            count = 0
        result.append(SessionInfo(session_id=sid, message_count=count))
    return result
```

---

## 2. static/chat.html

### 2a. Обернуть существующий layout в flex-контейнер с sidebar

Найди корневой `<div>` или `<body>` — обёрни содержимое так:

```html
<div class="app-layout">
    <!-- SIDEBAR -->
    <aside class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <span>Сессии</span>
            <button class="btn-icon" id="sidebarToggle" title="Скрыть панель">‹</button>
        </div>
        <div id="sessionList" class="session-list"></div>
    </aside>
    <!-- MAIN CHAT -->
    <div class="chat-container">
        <!-- существующий chat layout -->
    </div>
</div>
```

### 2b. CSS для sidebar (добавить в `<style>`)

```css
.app-layout {
    display: flex;
    height: 100vh;
    overflow: hidden;
}
.sidebar {
    width: 220px;
    min-width: 220px;
    background: var(--bg-primary);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    transition: width 0.2s, min-width 0.2s;
    overflow: hidden;
}
.sidebar.collapsed {
    width: 0;
    min-width: 0;
}
.sidebar-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 12px;
    border-bottom: 1px solid var(--border-color);
    font-size: 13px;
    font-weight: 600;
    color: var(--text-secondary);
}
.session-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
}
.session-item {
    padding: 8px 10px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 2px;
}
.session-item:hover { background: var(--bg-secondary); }
.session-item.active { background: var(--bg-secondary); font-weight: 600; }
.chat-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}
@media (max-width: 600px) {
    .sidebar { display: none; }
}
```

### 2c. JavaScript для sidebar (добавить в `<script>`)

```javascript
// Sidebar: загрузка и переключение сессий
async function loadSessions() {
    try {
        const resp = await fetch('/api/sessions');
        if (!resp.ok) return;
        const sessions = await resp.json();
        const list = document.getElementById('sessionList');
        list.innerHTML = '';
        if (sessions.length === 0) {
            list.innerHTML = '<div style="padding:10px;font-size:12px;color:var(--text-secondary)">Нет сессий</div>';
            return;
        }
        sessions.forEach(s => {
            const item = document.createElement('div');
            item.className = 'session-item' + (s.session_id === sessionId ? ' active' : '');
            item.textContent = s.session_id.slice(0, 8) + '… (' + s.message_count + ')';
            item.title = s.session_id;
            item.addEventListener('click', () => switchSession(s.session_id));
            list.appendChild(item);
        });
    } catch (_) {}
}

async function switchSession(newSessionId) {
    if (newSessionId === sessionId) return;
    sessionId = newSessionId;
    // Очистить чат и загрузить историю
    const chatMessages = document.getElementById('chatMessages'); // подставь реальный id
    if (chatMessages) chatMessages.innerHTML = '';
    try {
        const resp = await fetch('/api/sessions/' + sessionId + '/history');
        if (resp.ok) {
            const history = await resp.json();
            // history — массив {role, content}; отобразить каждое сообщение
            (history.messages || history || []).forEach(msg => {
                if (msg.role === 'user') appendUserMessage(msg.content);
                else if (msg.role === 'assistant') appendBotMessage({answer: msg.content, quality_score: null, route: null});
            });
        }
    } catch (_) {}
    loadSessions(); // обновить active-класс
}

// Обновлять список после каждого ответа
// Найди место, где завершается обработка ответа, и добавь: loadSessions();

// Sidebar toggle
document.getElementById('sidebarToggle')?.addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('collapsed');
});

// Загрузить список при старте
loadSessions();
```

Замени `chatMessages` и `appendUserMessage`/`appendBotMessage` на реальные имена из файла.

---

## CONSTRAINTS
- Изменить только `api/app.py` и `static/chat.html`
- Sidebar не ломает существующий chat layout на мобильных (display:none < 600px)
- `GET /api/sessions` возвращает только сессии из памяти (`_sessions` dict) — не БД
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `GET /api/sessions` возвращает список `[{session_id, message_count}]`
- [ ] Sidebar отображается слева от чата
- [ ] Клик по сессии загружает её историю через `/api/sessions/{id}/history`
- [ ] Кнопка `‹` сворачивает sidebar
- [ ] После каждого ответа список сессий обновляется
- [ ] `pytest tests/ -v` — 19 passed
