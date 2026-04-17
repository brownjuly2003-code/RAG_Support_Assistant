# Task 53 — UX-1: Inline citations в ответах

## Goal
Коммерческие продукты (Intercom Fin, Fini) показывают sources inline: `[1]`, `[2]`.
Сейчас sources в `<details>` блоке — спрятаны. Нужно:
1. Номерные ссылки в тексте ответа
2. Hover → показать title + excerpt
3. Click → раскрыть source panel

## Files to change
- `static/chat.html` — рендеринг ответа + CSS для citations
- `agent/prompts.py` — инструкция LLM вставлять `[1]`, `[2]` в ответ

---

## 1. agent/prompts.py — build_qa_prompt

Добавить в system prompt инструкцию цитирования:

В конец system-части промпта добавить:
```
Если ты используешь информацию из контекста, ссылайся на источники в формате [1], [2] и т.д.
Нумерация соответствует порядку документов в контексте.
```

---

## 2. static/chat.html — CSS

Добавить в `<style>`:

```css
.citation-ref {
    display: inline;
    color: var(--accent, #4a90d9);
    cursor: pointer;
    font-size: 0.85em;
    vertical-align: super;
    font-weight: 600;
    padding: 0 2px;
}
.citation-ref:hover {
    text-decoration: underline;
}
.citation-tooltip {
    position: absolute;
    background: var(--bg-primary, #fff);
    border: 1px solid var(--border, #e0e0e0);
    border-radius: 8px;
    padding: 8px 12px;
    max-width: 300px;
    font-size: 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    z-index: 1000;
    pointer-events: none;
    display: none;
}
.citation-tooltip.visible { display: block; }
.citation-tooltip .source-title { font-weight: 600; margin-bottom: 4px; }
.citation-tooltip .source-excerpt { color: var(--text-secondary, #555); }
```

---

## 3. static/chat.html — JS

В функции `addMessage`, после рендеринга markdown в `content.innerHTML`:

```javascript
// Заменить [1], [2] и т.д. на кликабельные citation refs
if (meta && meta.sources && meta.sources.length > 0) {
    let html = content.innerHTML;
    meta.sources.forEach(function(src, i) {
        const num = i + 1;
        const ref = '<span class="citation-ref" data-citation="' + num + '">[' + num + ']</span>';
        html = html.replace(new RegExp('\\[' + num + '\\]', 'g'), ref);
    });
    content.innerHTML = html;

    // Tooltip on hover
    content.querySelectorAll('.citation-ref').forEach(function(ref) {
        ref.addEventListener('mouseenter', function(e) {
            const idx = parseInt(ref.dataset.citation) - 1;
            const src = meta.sources[idx];
            if (!src) return;

            let tooltip = document.getElementById('citationTooltip');
            if (!tooltip) {
                tooltip = document.createElement('div');
                tooltip.id = 'citationTooltip';
                tooltip.className = 'citation-tooltip';
                document.body.appendChild(tooltip);
            }
            tooltip.innerHTML =
                '<div class="source-title">' + (src.source || 'Источник') + '</div>' +
                '<div class="source-excerpt">' + (src.page_content || '').substring(0, 150) + '...</div>';
            tooltip.classList.add('visible');

            const rect = ref.getBoundingClientRect();
            tooltip.style.left = rect.left + 'px';
            tooltip.style.top = (rect.bottom + 4) + 'px';
        });
        ref.addEventListener('mouseleave', function() {
            const tooltip = document.getElementById('citationTooltip');
            if (tooltip) tooltip.classList.remove('visible');
        });
    });
}
```

---

## CONSTRAINTS
- Изменить `agent/prompts.py` и `static/chat.html`
- Если LLM не вставил `[1]` — ничего не ломается (regex просто не найдёт match)
- Tooltip позиционируется relative to citation ref
- Не ломать существующий `<details>` sources block — он остаётся как fallback

## DONE WHEN
- [ ] Промпт инструктирует LLM цитировать `[1]`, `[2]`
- [ ] `[1]` в тексте → кликабельный superscript
- [ ] Hover на `[1]` → tooltip с source title + excerpt
- [ ] Если LLM не цитирует — ответ рендерится как обычно
- [ ] Существующий sources `<details>` блок остаётся
