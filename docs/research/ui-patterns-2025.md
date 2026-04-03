# Research: современный UI для RAG/support-chat приложений (2025)

## Goal
Изучить, какой UI принято делать для корпоративных RAG-чат-ассистентов поддержки в 2025 году.
Найти примеры, паттерны, библиотеки. Зафиксировать рекомендации для нашего проекта.

## Background: текущий UI

Проект уже имеет `static/chat.html` — standalone HTML с тёмной темой, vanilla JS,
без фреймворков. Фичи: chat UI, dark mode toggle, badge'и качества и маршрута,
upload документов, session management. FastAPI отдаёт статику напрямую.

**Вопрос:** стоит ли переходить на полноценный UI-фреймворк (React/Vue/Svelte)?
Или vanilla HTML достаточно для enterprise support assistant?

## Research questions

### Q1: Тренды UI для enterprise RAG-ассистентов (2025)

**Пример 1:**
```
[Название / URL: LibreChat — https://www.librechat.ai/]
[Stack: TypeScript/React frontend в monorepo (`/client`), self-hosted web app.]
[Ключевые UI-паттерны: sidebar/history, model switching, file chat, search по разговорам, artifacts, agents/tools, persistent memory, enterprise auth.]
[Stars/popularity: 34.2k GitHub stars, 24.3M Docker pulls.]
```

**Пример 2:**
```
[Название / URL: Vercel AI Chatbot / Chat SDK — https://github.com/vercel/ai-chatbot и https://github.com/vercel/ai]
[Stack: Next.js + React + TypeScript + Tailwind/shadcn/ui + AI SDK.]
[Ключевые UI-паттерны: streaming, persisted history, auth, attachments/blob storage, unified provider abstraction, server-driven chat actions.]
[Stars/popularity: `vercel/ai-chatbot` ~19k stars, `vercel/ai` ~20.1k stars.]
```

**Пример 3:**
```
[Название / URL: assistant-ui — https://github.com/assistant-ui/assistant-ui]
[Stack: TypeScript/React library.]
[Ключевые UI-паттерны: production-grade chat primitives, streaming, auto-scroll, attachments, tool rendering, accessibility, customizable thread/message/input primitives.]
[Stars/popularity: 8.4k stars.]
```

**Пример 4:**
```
[Название / URL: CopilotKit — https://github.com/CopilotKit/CopilotKit]
[Stack: React + TypeScript.]
[Ключевые UI-паттерны: chat UI, generative UI, shared state между агентом и интерфейсом, human-in-the-loop workflows, tool calls и rich in-app copilots.]
[Stars/popularity: 28.6k stars.]
```

**Вывод по трендам:**
```
[Доминирующий stack в 2025: React/Next.js/TypeScript; чаще всего поверх Tailwind + shadcn/ui или собственных headless primitives.]
[Самые популярные UI-паттерны для RAG-чата: streaming ответа, persisted threads/sidebar, attachments/files, tool/artifact rendering, human-in-the-loop actions, auth и аналитика.]
[Vanilla HTML: всё ещё приемлемо для небольшого внутреннего PoC или простого standalone-чата, но это уже не доминирующий путь для feature-rich enterprise assistant.]
```

---

### Q2: Ключевые UI-паттерны для RAG support assistant

**Source citations в ответе:**
```
[Принято ли показывать источники рядом с ответом? Да, для RAG/support это ожидаемый trust-pattern. По reviewed продуктам доминирует не "академическая сноска", а practical evidence UI: expandable blocks, side details, artifacts, tool outputs. Это вывод по продуктовым паттернам reviewed OSS, а не одна буквальная спецификация.]
[Как обычно показывают: expandable beneath-the-answer block или соседняя панель; реже — плотные inline footnotes.]
[Пример: у нас уже есть collapsible sources block; в более зрелых стэках (assistant-ui, CopilotKit, Vercel templates, LibreChat) рядом с сообщением часто живут attachments, tool results, artifacts и thread metadata.]
```

**Streaming ответов (SSE/WebSocket):**
```
[Насколько это стало нормой в 2025? По reviewed стэкам — практически нормой. assistant-ui прямо заявляет streaming и real-time updates; Vercel AI Chatbot и AI SDK строятся вокруг stream-first UX; CopilotKit поддерживает message streaming и agent responses.]
[Влияет ли на восприятие качества? Да. Streaming не делает ответ точнее, но заметно улучшает perceived latency и ощущение "живой" системы.]
[Реализация: SSE vs WebSocket — что проще для FastAPI? Для нашего кейса проще SSE: поток токенов идёт в одну сторону и хорошо ложится на генерацию ответа. WebSocket нужен, если мы пойдём в bidirectional agent events, shared state и tool-driven live UI.]
```

**Feedback на ответ (👍/👎):**
```
[Насколько важно для RAG-системы поддержки? Высоко. Это дешёвый путь собирать реальные hard cases и связывать UI с eval loop.]
[Как данные используются: пополнение offline dataset, разбор low-quality маршрутов, настройка порогов auto/human, поиск деградаций после изменений.]
[Стоит ли добавить в наш проект? Да. Минимальный вариант — thumbs up/down на bot message + optional reason для downvote.]
```

**History / multiple sessions:**
```
[Принято ли хранить историю сессий на стороне UI? Да, но в зрелых системах обычно не только в localStorage, а с серверной persistence и явным списком тредов.]
[Паттерн: sidebar с историей vs просто новая сессия? В 2025 доминирует sidebar/history list. Кнопка `New session` без видимой истории — уже минималистичный PoC-паттерн.]
```

---

### Q3: Библиотеки / open-source UI компоненты для RAG-чата

**Вариант 1 (embedded widget):**
```
[Название: CopilotKit]
[URL: https://github.com/CopilotKit/CopilotKit]
[Плюсы для нашего кейса: даёт chat UI и human-in-the-loop/generative UI паттерны, если захотим встроить support-copilot не как отдельную страницу, а как функциональный слой поверх продукта.]
[Минусы: заметно тяжелее нашего текущего standalone HTML; ценность раскрывается только если нужен agent-native UI, shared state и tool rendering.]
```

**Вариант 2 (React/Vue компонент):**
```
[Название: assistant-ui]
[URL: https://github.com/assistant-ui/assistant-ui]
[Плюсы: один из самых практичных React-наборов именно под chat UX — streaming, threads, attachments, tool outputs, а11y, composable primitives.]
[Минусы: требует миграции на React-стек; для простого PoC это может быть архитектурным оверхедом.]
```

**Вариант 3 (headless / near-vanilla):**
```
[Название: Vercel AI SDK / Chat SDK]
[URL: https://github.com/vercel/ai и https://github.com/vercel/ai-chatbot]
[Плюсы: сильный reference stack для streaming chat, persistence и provider abstraction; можно брать как архитектурный ориентир даже если не копировать UI целиком.]
[Минусы: это уже экосистема Next.js/React, а не настоящий vanilla/web-components путь. Среди reviewed источников не видно столь же доминирующего vanilla/web-components лидера; экосистема явно сместилась в React-first сторону.]
```

---

### Q4: Оценка текущего `static/chat.html`

**Что уже хорошо:**
```
[Standalone-архитектура очень дешёвая в поддержке и отлично подходит для FastAPI static serving.]
[Есть уже правильные базовые элементы support-чата: upload документов, quality/route badges, source disclosure, dark mode, session reset.]
[Для внутреннего PoC текущий UI читаемый, быстрый и не перегружен.]
```

**Чего не хватает (топ-3 самых важных для support-assistant):**
```
1. [feature: streaming ответа] — [почему важно для support: улучшает time-to-first-token и субъективно делает систему заметно быстрее без смены модели.]
2. [feature: видимая история тредов / sidebar sessions] — [почему важно: оператору и пользователю проще возвращаться к предыдущим кейсам, а не терять контекст за одной "текущей" сессией.]
3. [feature: feedback на каждый ответ + richer handoff transparency] — [почему важно: support-сценарий живёт на trust loop; нужно быстро собирать негативный фидбек и объяснять, почему запрос ушёл в `human`.]
```

**Стоит ли переходить на React/Vue?**
```
[Рекомендация: пока нет, но держать путь миграции открытым.]
[Аргументы: текущий scope ещё помещается в vanilla HTML. Самые ценные ближайшие улучшения — streaming, feedback, session sidebar, чуть богаче sources/handoff UI — можно сделать без полной миграции. Но если roadmap включает persistent multi-user threads, auth, tool panels, artifacts, generative UI и сложное состояние, тогда React/Next.js станет оправданным.]
[Стоимость миграции vs выгода: прямо сейчас стоимость миграции выше выгоды; после появления 3-4 state-heavy функций выгода резко вырастет.]
```

---

## Output: Recommendation

```
РЕКОМЕНДАЦИЯ ДЛЯ ПРОЕКТА:

Stack:
[Оставить vanilla HTML сейчас.]
Обоснование: текущий UI уже покрывает базовый PoC-сценарий, а ближайшие высокоценные улучшения не требуют немедленного перехода на фреймворк. Экосистема 2025 действительно React-first, но миграцию лучше делать по сигналу сложности, а не "для моды".

Топ-3 улучшения UI (по соотношению ценность/усилия):
1. [Добавить streaming ответа через SSE.]
2. [Сделать явный sidebar/history для нескольких сессий.]
3. [Добавить thumbs up/down и явное объяснение причин `human` route.]

Приоритет для support-ticket сценария:
[Сначала прозрачность и управляемость (sources/handoff/feedback), затем perceived speed (streaming), затем удобство возврата к кейсам (history/sidebar).]
```

## Sources used

- `static/chat.html`
- https://www.librechat.ai/
- https://www.librechat.ai/docs/development/conventions
- https://github.com/vercel/ai-chatbot
- https://github.com/vercel/ai
- https://github.com/assistant-ui/assistant-ui
- https://www.assistant-ui.com/
- https://github.com/CopilotKit/CopilotKit
- https://www.copilotkit.ai/
