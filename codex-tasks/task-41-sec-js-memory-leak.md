# Task 41 — SEC-6: JS memory leak — event delegation в chat.html

## Goal
Каждый `addMessage()` вешает новые `addEventListener` на кнопки feedback.
За 100+ сообщений — 200+ listeners, never cleaned up.
Заменить на event delegation на контейнере `chatMessages`.

## Files to change
- `static/chat.html` — JS-секция: feedback listeners

---

## static/chat.html

### Шаг 1: Убрать per-button listeners (строки ~1163-1179)

было:
```javascript
                    fbDiv.querySelectorAll('.btn-feedback').forEach(btn => {
                        btn.addEventListener('click', async () => {
                            const rating = btn.dataset.rating;
                            fbDiv.querySelectorAll('.btn-feedback').forEach(b => b.classList.add('voted'));
                            try {
                                await fetch(API_BASE + '/feedback', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({
                                        trace_id: meta.trace_id || '',
                                        session_id: meta.session_id || sessionId || '',
                                        rating: rating,
                                    }),
                                });
                            } catch (_) {}
                        });
                    });
```

стало:
```javascript
                    fbDiv.dataset.traceId = meta.trace_id || '';
                    fbDiv.dataset.sessionId = meta.session_id || sessionId || '';
```

### Шаг 2: Добавить один delegated listener

После инициализации `chatMessages` (где-то в начале JS-секции, рядом с другими `addEventListener`), добавить:

```javascript
        // Delegated feedback handler — один listener на весь контейнер
        chatMessages.addEventListener('click', async function(e) {
            const btn = e.target.closest('.btn-feedback');
            if (!btn) return;

            const fbDiv = btn.closest('.msg-feedback');
            if (!fbDiv) return;

            const rating = btn.dataset.rating;
            const traceId = fbDiv.dataset.traceId || '';
            const feedbackSessionId = fbDiv.dataset.sessionId || '';

            // Отметить как проголосованное
            fbDiv.querySelectorAll('.btn-feedback').forEach(b => b.classList.add('voted'));

            try {
                await fetch(API_BASE + '/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        trace_id: traceId,
                        session_id: feedbackSessionId,
                        rating: rating,
                    }),
                });
            } catch (err) {
                console.warn('Feedback submission failed:', err);
            }
        });
```

### Шаг 3: Убрать silent catch

В шаге 2 уже заменён `catch (_) {}` на `catch (err) { console.warn(...) }`.

---

## CONSTRAINTS
- Изменить только `static/chat.html`
- Один addEventListener на chatMessages вместо N на каждое сообщение
- Feedback функциональность не должна сломаться: 👍👎 → POST /api/feedback
- Кнопки после клика получают class `voted`
- Не менять HTML-разметку кнопок feedback

## DONE WHEN
- [ ] Нет `addEventListener` внутри `addMessage()` для feedback-кнопок
- [ ] `data-trace-id` и `data-session-id` хранятся на `fbDiv` через dataset
- [ ] Один delegated listener на `chatMessages` обрабатывает все feedback-клики
- [ ] `catch (_) {}` заменён на `catch (err) { console.warn(...) }`
- [ ] 100 сообщений не увеличивают количество event listeners сверх baseline
