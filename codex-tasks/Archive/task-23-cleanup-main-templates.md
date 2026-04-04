# Task 23 — Исправить templates/, убрать мусор из main.py

## Goal
`templates/` не существует → Jinja2-роуты в main.py падают с 500 при обращении.
Создать папку, переместить HTML-шаблоны, удалить мертвые маршруты.

## Background
`main.py` строка 78:
```python
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
```
`BASE_DIR = Path(__file__).resolve().parent` → это корень проекта.
Папки `templates/` нет. HTML-файлы лежат в корне: `index.html`, `ask_result.html`,
`traces.html`, `trace_detail.html`, `escalations.html`.

Роуты которые их используют: `/`, `/ask-ui`, `/escalations-ui`, `/traces-ui`, `/traces-ui/{id}`.
Роут `/chat` — не затронут, он отдаёт `static/chat.html` отдельно.

## Files to change
- `main.py` — исправить маршруты или удалить мёртвые
- создать `templates/` и переместить 5 HTML-файлов из корня

---

## Вариант: сохранить traces-viewer, починить templates/

Это полезная функциональность — traces и escalations viewer.
Нужно только создать папку и переместить файлы.

### Шаг 1: создать директорию `templates/`

Просто создать `templates/.gitkeep` (пустой файл) чтобы git отслеживал папку.

### Шаг 2: переместить HTML-файлы

Переместить из корня в `templates/`:
- `index.html` → `templates/index.html`
- `ask_result.html` → `templates/ask_result.html`
- `traces.html` → `templates/traces.html`
- `trace_detail.html` → `templates/trace_detail.html`
- `escalations.html` → `templates/escalations.html`

### Шаг 3: убрать мёртвый маршрут `/ask-ui`

Маршрут `POST /ask-ui` (`/ask-ui`) вероятно дублирует `/api/ask`.
Проверь: если он только рендерит форму запроса и не нужен рядом с `/chat` — удали.

В main.py найди:
```python
@app.post("/ask-ui", response_class=HTMLResponse)
```
Если он нигде не ссылается из других шаблонов — удали весь блок.

### Шаг 4: добавить `.gitignore` для data-артефактов

В корне создать или дополнить `.gitignore`:
```gitignore
# Data artifacts (generated at runtime)
data/
__pycache__/
*.pyc
.env
```

Если `.gitignore` уже есть — добавить только строки, которых нет.

---

## CONSTRAINTS
- Изменить только `main.py`, создать `templates/` с перемещёнными файлами, обновить `.gitignore`
- НЕ удалять `/traces-ui` и `/traces-ui/{id}` — нужны для трейсинга
- НЕ удалять `/escalations-ui` — нужен для просмотра эскалаций
- После переноса `python main.py` должен стартовать без ошибок
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `templates/` папка существует с 5 HTML-файлами (или 4, если /ask-ui удалён)
- [ ] `python -c "from main import app"` не выбрасывает исключений
- [ ] HTML-файлы УДАЛЕНЫ из корня (не дублируются)
- [ ] `.gitignore` содержит `data/`
- [ ] `pytest tests/ -v` — проходит
