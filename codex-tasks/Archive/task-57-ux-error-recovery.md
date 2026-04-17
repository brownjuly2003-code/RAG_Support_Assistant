# Task 57 — UX-6: Контекстные error messages + error recovery

## Goal
Сейчас ошибки показываются как generic "Ошибка: [text]" без guidance.
Silent `catch (_) {}` глотает ошибки. Нужно:
1. Контекстные сообщения с action buttons
2. Убрать все silent catches
3. Перевести английские строки на русский

## Files to change
- `static/chat.html` — error handling в JS

---

## 1. Error message helper

Добавить в JS:

```javascript
function getErrorMessage(error, context) {
    if (error && error.message && error.message.includes('Failed to fetch')) {
        return {
            text: 'Сервер недоступен. Проверьте подключение к интернету.',
            actions: ['retry', 'escalate']
        };
    }
    if (error && error.status === 429) {
        return {
            text: 'Слишком много запросов. Подождите минуту и попробуйте снова.',
            actions: ['retry']
        };
    }
    if (error && error.status === 503) {
        return {
            text: 'Сервис временно недоступен. Ollama может быть перезагружается.',
            actions: ['retry', 'escalate']
        };
    }
    if (context === 'stream') {
        return {
            text: 'Потоковая передача прервана. Попробуйте отправить вопрос заново.',
            actions: ['retry']
        };
    }
    return {
        text: 'Произошла ошибка: ' + (error.message || error || 'неизвестная ошибка'),
        actions: ['retry', 'escalate']
    };
}
```

---

## 2. Обновить sendMessage error handling

было:
```javascript
} catch (e) {
    addMessage('assistant', 'Ошибка: ' + e.message, {});
}
```

стало:
```javascript
} catch (e) {
    const errInfo = getErrorMessage(e, 'send');
    addMessage('assistant', errInfo.text, { error: true, actions: errInfo.actions, originalQuestion: question });
}
```

---

## 3. Обновить streaming error handling

Все `catch (_) {}` в streaming → логировать:

было:
```javascript
} catch (_) {}
```

стало:
```javascript
} catch (err) {
    console.warn('Operation failed:', err);
}
```

---

## 4. Перевести английские строки

Найти и заменить:
- `"No sessions"` → `"Нет сессий"`
- `"Streaming error"` → `"Ошибка потоковой передачи"`
- `"New session"` → `"Новая сессия"` (title атрибуты)
- `"Toggle dark mode"` → `"Переключить тему"`
- `"Upload document"` → `"Загрузить документ"`

---

## CONSTRAINTS
- Изменить только `static/chat.html`
- Все `catch (_) {}` → `catch (err) { console.warn(...) }`
- Error messages на русском
- Каждая ошибка предлагает действие (retry и/или escalate)

## DONE WHEN
- [ ] `getErrorMessage()` function определена
- [ ] Network error → "Сервер недоступен" + retry
- [ ] 429 → "Слишком много запросов"
- [ ] 503 → "Сервис недоступен" + retry + escalate
- [ ] Нет `catch (_) {}` — все с console.warn
- [ ] Все строки UI на русском
