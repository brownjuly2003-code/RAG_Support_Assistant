# Task 21 — Docker Compose с Ollama

## Goal
`docker compose up` должен поднять полный стек: приложение + Ollama.
Сейчас docker-compose.yml запускает только app; Ollama нужно запускать вручную.

## Background
Текущий `docker-compose.yml`:
```yaml
services:
  app:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    volumes: ["./data:/app/data"]
```

Ollama имеет официальный Docker-образ: `ollama/ollama`.
Модель нужно pull при первом запуске через `ollama pull mistral`.

## Files to change
- `docker-compose.yml` — добавить ollama service + зависимость app от ollama
- `.env.example` — добавить новые флаги (HyDE, parent-child) + обновить OLLAMA_BASE_URL
- `Dockerfile` — добавить healthcheck-скрипт если нужен wait-for-ollama

---

## 1. docker-compose.yml

Заменить полностью:

```yaml
services:

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 30s
    restart: unless-stopped

  ollama-init:
    image: ollama/ollama
    depends_on:
      ollama:
        condition: service_healthy
    volumes:
      - ollama_data:/root/.ollama
    entrypoint: ["ollama", "pull", "mistral"]
    environment:
      - OLLAMA_HOST=http://ollama:11434
    restart: "no"

  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
    volumes:
      - ./data:/app/data
    depends_on:
      ollama:
        condition: service_healthy
    restart: unless-stopped

volumes:
  ollama_data:
```

---

## 2. .env.example

Добавить в конец файла (не удалять существующие строки):

```dotenv
# Enable HyDE (Hypothetical Document Embeddings) for improved retrieval
RAG_HYDE=false
# Enable Parent-Child chunking (search child chunks, return parent context)
RAG_PARENT_CHILD=false
```

Также обновить комментарий к `OLLAMA_BASE_URL`:
```dotenv
# URL of the Ollama API. In Docker Compose use http://ollama:11434
OLLAMA_BASE_URL=http://localhost:11434
```

---

## CONSTRAINTS
- Изменить только `docker-compose.yml` и `.env.example`
- `ollama-init` — разовый контейнер (restart: "no"), не мешает повторному `docker compose up`
- Если GPU недоступен — Ollama работает на CPU (ничего дополнительного не нужно)
- Не добавлять `deploy: resources` — этоломает Docker Compose без Docker Swarm

## DONE WHEN
- [ ] `docker-compose.yml` содержит три сервиса: ollama, ollama-init, app
- [ ] `app` зависит от `ollama` через `condition: service_healthy`
- [ ] `ollama-init` автоматически делает `pull mistral` при первом запуске
- [ ] `.env.example` содержит `RAG_HYDE` и `RAG_PARENT_CHILD`
- [ ] `pytest tests/ -v` — проходит (без изменений Python-кода)
