# Task 51 — DS-2: WCAG AA accessibility fixes

## Goal
10+ critical WCAG violations: нет labels, нет keyboard navigation, нет ARIA.
Исправить критичные проблемы в chat.html, help.html, metrics.html и templates.

## Dependencies
- task-50 (shared CSS с focus indicators)

## Files to change
- `static/chat.html`
- `static/help.html`
- `static/metrics.html`
- `templates/index.html`

---

## 1. static/chat.html

### 1.1 Textarea label (строка ~749)

было:
```html
            <textarea
                id="questionInput"
                placeholder="Напишите ваш вопрос..."
                rows="1"
                autofocus
            ></textarea>
```

стало:
```html
            <label for="questionInput" class="sr-only">Введите ваш вопрос</label>
            <textarea
                id="questionInput"
                placeholder="��апишите ваш вопрос..."
                rows="1"
                autofocus
                aria-label="Введите ваш вопрос"
            ></textarea>
```

### 1.2 SVG-кнопки — aria-label (строки ~707-716)

Добавить `aria-label` на все SVG-only кнопки:

```html
<button class="btn-icon" id="themeToggle" title="Переключить тему" aria-label="Переключить тему">
```

```html
<button class="btn-icon" id="newSessionBtn" title="Новая сессия" aria-label="Новая сессия">
```

```html
<button class="btn-upload" id="uploadBtn" title="Загрузить документ" aria-label="Загрузить документ">
```

```html
<button class="btn-send" id="sendBtn" title="Отправить" aria-label="Отправить">
```

### 1.3 sr-only class

Добавить в CSS (inline `<style>` или в components.css):

```css
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
}
```

### 1.4 Wrap chat input в form

было:
```html
    <div class="input-area">
        <div class="input-wrapper">
            <div class="input-group">
```

стало:
```html
    <form class="input-area" id="chatForm" role="search" aria-label="Зад��ть вопрос">
        <div class="input-wrapper">
            <div class="input-group">
```

И закрывающий `</div>` → `</form>`.

Обновить JS: заменить `sendBtn.addEventListener('click', ...)` на:
```javascript
chatForm.addEventListener('submit', function(e) {
    e.preventDefault();
    sendMessage();
});
```

### 1.5 Keyboard shortcut — Enter to send

Уже работает? Проверить. Если нет — добавить:
```javascript
questionInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});
```

---

## 2. static/help.html, metrics.html

Добавить `lang="ru"` на `<html>` тег:
```html
<html lang="ru">
```

---

## 3. templates/index.html

Добавить viewport meta:
```html
<meta name="viewport" content="width=device-width, initial-scale=1">
```

Добавить `lang="ru"` на `<html>`.

---

## CONSTRAINTS
- Изменить 4 файла
- Все кнопки с SVG-only — должны иметь `aria-label`
- Все form inputs — должны иметь `<label>` (видимый или sr-only)
- `lang="ru"` на всех `<html>` тегах
- viewport meta на всех страницах
- Не ломать существующую функциональнос��ь

## DONE WHEN
- [ ] Все SVG-кнопки в chat.html имеют `aria-label`
- [ ] Textarea имеет `<label for="">` (sr-only)
- [ ] Chat input обёрнут в `<form>`
- [ ] `.sr-only` class определён
- [ ] `lang="ru"` на всех страницах
- [ ] viewport meta на templates/index.html
- [ ] Tab-навигация работает: focus виден на всех интерактивных элементах
