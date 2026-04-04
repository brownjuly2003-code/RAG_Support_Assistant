# Task 27 — Apply model recommendation: mistral → qwen2.5:7b

## Goal
Сменить дефолтную модель проекта с `mistral` на `qwen2.5:7b`.
Основание: R1-рисерч (MERA Industrial 0.555 vs 0.213) + симуляция task-26.

## Prerequisite
Прочитай `docs/research/simulated_model_comparison.md` (task-26).
Если файл не существует — остановись: "BLOCKED: task-26 not done".

## Files to change
- `config/settings.py` — изменить default `ollama_model_name`
- `docker-compose.yml` — изменить модель в `ollama-init`
- `.env.example` — обновить комментарий и значение по умолчанию
- `README.md` — обновить упоминание модели

---

## 1. config/settings.py

Найти строку:
```python
ollama_model_name: str = os.getenv("OLLAMA_MODEL_NAME", "mistral")
```
Заменить на:
```python
ollama_model_name: str = os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b")
```

---

## 2. docker-compose.yml

Найти в сервисе `ollama-init`:
```yaml
entrypoint: ["ollama", "pull", "mistral"]
```
Заменить на:
```yaml
entrypoint: ["ollama", "pull", "qwen2.5:7b"]
```

---

## 3. .env.example

Найти:
```dotenv
OLLAMA_MODEL_NAME=mistral
```
Заменить на:
```dotenv
# Generation model. Recommended: qwen2.5:7b (best Russian quality, MERA Industrial 0.555)
# Alternatives: gemma3:4b (8GB RAM), llama3.1:8b, mistral (legacy default)
OLLAMA_MODEL_NAME=qwen2.5:7b
```

---

## 4. README.md

Найти упоминание `mistral` в таблице Environment Variables:
```markdown
| `OLLAMA_MODEL_NAME` | `mistral` | модель генерации ответов |
```
Заменить на:
```markdown
| `OLLAMA_MODEL_NAME` | `qwen2.5:7b` | модель генерации ответов |
```

Найти в секции Quick Start:
```bash
ollama pull mistral
```
Заменить на:
```bash
ollama pull qwen2.5:7b
```

---

## CONSTRAINTS
- Изменить только 4 файла: `config/settings.py`, `docker-compose.yml`, `.env.example`, `README.md`
- Не менять логику — только строки со значением модели
- `pytest tests/ -v` — проходит (тесты не зависят от имени модели)

## DONE WHEN
- [ ] `get_settings().ollama_model_name` по умолчанию возвращает `"qwen2.5:7b"`
- [ ] `docker-compose.yml` тянет `qwen2.5:7b` при первом запуске
- [ ] `.env.example` содержит комментарий с обоснованием и альтернативами
- [ ] `README.md` упоминает `qwen2.5:7b` вместо `mistral`
- [ ] `pytest tests/ -v` — все тесты проходят
