# Task 105 — UX polish: upload progress, error recovery, onboarding

## Context
Три небольших UX-гэпа которые вместе делают ощутимую разницу:
1. **Upload progress** — сейчас показывается только финальный статус;
   при 10MB PDF пользователь видит "висящий" UI 5-30 сек
2. **Error recovery** — failed messages показываются как `"Ошибка: ..."`
   без retry-кнопки. Silent `catch (_) {}` в нескольких местах
3. **Onboarding** — новый пользователь попадает сразу в пустой чат без
   указаний что бот умеет и какие вопросы задавать

## Goal
Закрыть три пункта за одну таску — каждый небольшой, но вместе это
заметный commercial-feel апгрейд.

## Files to change
- `static/chat.html` — UI для трёх фич
- `static/styles/components.css` — стили progress-bar, retry-button,
  onboarding-panel
- Опционально `api/app.py` — если upload endpoint ещё не стримит
  progress через SSE/chunked (скорее всего нет — progress будет считаться
  на клиенте по `xhr.upload.progress`)

## Implementation sketch

### 1. Upload progress (chat.html)
Заменить fetch на XMLHttpRequest для upload:
```javascript
function uploadFile(file) {
  const xhr = new XMLHttpRequest();
  xhr.upload.addEventListener('progress', (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      updateProgressBar(pct);
    }
  });
  xhr.addEventListener('load', () => {
    if (xhr.status === 200) onUploadDone(JSON.parse(xhr.responseText));
    else onUploadError(xhr.statusText);
  });
  xhr.addEventListener('error', () => onUploadError('Network error'));
  xhr.open('POST', '/api/upload');
  xhr.setRequestHeader('Authorization', 'Bearer ' + token);
  const fd = new FormData();
  fd.append('file', file);
  xhr.send(fd);
}
```

Progress bar — `<progress>` element или custom div с `aria-valuenow`.

### 2. Error recovery
Failed message (POST /api/ask fail, stream error, timeout):
- Показать message-bubble с классом `.msg-error`
- Внутри: `<button class="btn-retry" aria-label="Повторить запрос">↻ Повторить</button>`
- Click → resend last user question с тем же session_id
- Показывать контекстный текст: 503 → "Сервис перегружен", network fail →
  "Нет соединения", timeout → "Запрос занимает слишком много времени"

Убрать все `catch (_) {}` — минимум `console.warn('feedback failed:', e)`
+ user-facing toast "Не удалось отправить отзыв" (только для user-visible
actions).

### 3. Onboarding
При первом визите (нет `localStorage['onboarding_done']`):
- Показать welcome panel поверх чата с:
  - Приветствием
  - Списком capabilities ("Отвечу на вопросы по ...", "Покажу источники", "Эскалирую на оператора")
  - 3 sample questions — кнопки, клик отправляет вопрос
  - "Закрыть" → localStorage flag
- При click на sample question → close panel + auto-submit

## CONSTRAINTS
- Upload progress должен работать даже если сервер не поддерживает
  streaming response — progress на client-side считаем по xhr.upload.progress
- Retry button должен дедуплицировать: если запрос уже в flight, не
  запускать повторно
- Onboarding — только для **анонимных** пользователей или first-login.
  Для вернувшихся юзеров — не показывать.

## DONE WHEN
- [ ] Upload 5MB файла показывает прогресс 0-100% визуально плавно
- [ ] Отключить backend → сообщение "Сервис временно недоступен" + retry button работает
- [ ] Новый localStorage-чистый пользователь видит onboarding, повторный визит — нет
- [ ] 3 sample questions clickable → отправляются как обычные user messages
- [ ] 225+ passed (JS-unit тесты или playwright для trigger/close onboarding)
- [ ] Screenshots: progress bar mid-upload, error with retry, onboarding panel
- [ ] Commit: "UX polish: upload progress, error recovery, onboarding (task-105)"
