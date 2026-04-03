# Task 10 — User help page: technologies & UI explanation

## Goal
Users see "Качество: 73" and "Маршрут: human" but don't know what it means.
Create a help modal in the existing chat UI that explains the system.

## Create one new file: static/help.html

Standalone HTML page (открывается в новой вкладке по кнопке "?" в шапке чата).
Используй тот же CSS-стиль что и chat.html: тёмная тема, те же переменные цвета.

Структура страницы:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>О системе — RAG Support Assistant</title>
  <style>
    /* скопируй CSS-переменные и базовые стили из chat.html: --bg, --surface, --text, --accent */
    /* body: font-family, background, color, max-width 800px, margin auto, padding 2rem */
    /* h1, h2: accent color */
    /* table: border-collapse, полная ширина, td/th padding 0.5rem 1rem */
    /* .badge: inline-block, border-radius 4px, padding 2px 8px, font-size 0.8rem */
    /* .badge-quality: background #10b981 */
    /* .badge-human: background #ef4444 */
  </style>
</head>
<body>
  <h1>RAG Support Assistant</h1>
  <p>[одно предложение: что делает система]</p>

  <h2>Как это работает</h2>
  <!-- ASCII-схема пайплайна: вопрос → поиск → оценка → ответ/эскалация -->
  <pre>[...]</pre>

  <h2>Технологии</h2>
  <table>
    <tr><th>Компонент</th><th>Технология</th><th>Зачем</th></tr>
    <tr><td>Оркестрация</td><td>LangGraph</td><td>[почему LangGraph, а не цепочка]</td></tr>
    <tr><td>Поиск документов</td><td>ChromaDB + BM25</td><td>[почему гибридный поиск]</td></tr>
    <tr><td>Эмбеддинги</td><td>BGE-M3</td><td>[почему BGE-M3, а не OpenAI]</td></tr>
    <tr><td>Reranking</td><td>ms-marco cross-encoder</td><td>[что делает, зачем нужен]</td></tr>
    <tr><td>Генерация</td><td>Ollama / Mistral</td><td>[почему локальная LLM]</td></tr>
    <tr><td>Трейсинг</td><td>SQLite</td><td>[что логируется]</td></tr>
  </table>

  <h2>Что означают бейджи</h2>
  <p><span class="badge badge-quality">Качество: 85</span>
     — [объяснить: LLM сам оценивает ответ от 0 до 100. Высокое = ответ точный и основан на контексте]</p>
  <p><span class="badge badge-quality">Маршрут: auto</span>
     — [объяснить: ответ отправлен автоматически]</p>
  <p><span class="badge badge-human">Маршрут: human</span>
     — [объяснить: вопрос передан оператору, причина]</p>

  <h2>Как загружать документы</h2>
  <p>[1-2 предложения: форматы, что происходит после загрузки]</p>

  <p style="margin-top:2rem"><a href="/">[← Вернуться в чат]</a></p>
</body>
</html>
```

## Также: добавить кнопку "?" в chat.html

В шапке чата (в `<header>` или рядом с кнопкой "New session") добавить:
```html
<a href="/help" target="_blank" class="btn-icon" title="О системе">?</a>
```

FastAPI уже отдаёт static файлы — `/help` будет доступен автоматически если переименовать
или добавить route. Проверь как отдаётся chat.html и сделай так же для help.html.

## CONSTRAINTS
- Создать: `static/help.html`
- Изменить: `static/chat.html` — только добавить кнопку "?" в шапку
- Никакие Python-файлы не трогать
- Заполнить все `[...]` — никаких плейсхолдеров в финале
- Стиль должен соответствовать chat.html (тёмная тема)

## DONE WHEN
- [ ] `static/help.html` существует, нет `[...]`
- [ ] Страница открывается в браузере без ошибок
- [ ] В chat.html есть ссылка/кнопка на help
