# Task 42 — DB-4: Добавить PostgreSQL + Redis в docker-compose

## Goal
Текущий docker-compose.yml содержит только ollama + app.
Добавить postgres и redis как сервисы — основа для персистентных сессий и кэширования.

## Files to change
- `docker-compose.yml` — добавить postgres + redis сервисы
- `.env.example` — добавить DATABASE_URL и REDIS_URL

---

## 1. docker-compose.yml

Добавить два сервиса перед `app`:

```yaml
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: rag_assistant
      POSTGRES_USER: rag
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-rag_dev_password}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rag -d rag_assistant"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
```

В сервис `app` добавить `depends_on`:

было:
```yaml
    depends_on:
      ollama-init:
        condition: service_completed_successfully
```

стало:
```yaml
    depends_on:
      ollama-init:
        condition: service_completed_successfully
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql://rag:${POSTGRES_PASSWORD:-rag_dev_password}@postgres:5432/rag_assistant
      - REDIS_URL=redis://redis:6379/0
```

В секцию `volumes` добавить:

```yaml
  pgdata:
  redisdata:
```

---

## 2. .env.example

Добавить секцию:

```
# --- PostgreSQL ---
POSTGRES_PASSWORD=rag_dev_password
DATABASE_URL=postgresql://rag:rag_dev_password@localhost:5432/rag_assistant

# --- Redis ---
REDIS_URL=redis://localhost:6379/0
```

---

## CONSTRAINTS
- Изменить только `docker-compose.yml` и `.env.example`
- Postgres 16, Redis 7 — оба Alpine для размера
- Healthcheck на обоих сервисах
- App зависит от postgres + redis через `condition: service_healthy`
- Пароль через env var с dev-default

## DONE WHEN
- [ ] `docker compose config` — валидный YAML, 5+ сервисов
- [ ] `docker compose up postgres redis` — оба healthy
- [ ] `docker compose up` — app стартует после postgres + redis
- [ ] `.env.example` содержит `DATABASE_URL` и `REDIS_URL`
