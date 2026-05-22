# Quickstart — RAG Support Assistant

> The minimum steps to run the service locally and verify it works.

## 0. Requirements

- Python 3.11+ (tested on 3.13)
- Docker Desktop (for Postgres + Redis in dev and for regression eval)
- ~8 GB disk space for embeddings/reranker/cache; explicit Ollama mode requires additional space for models.

Per selected profile:
- **GraceKelly** at `D:\GraceKelly\` (port 8011) — default local orchestrator for Claude Sonnet 4.6 / GPT-5 / Gemini via Perplexity Pro.
- **Ollama** (`https://ollama.com/download`) — for explicit `local-first` scenario or fallback.
- **Mistral API key** (`MISTRAL_API_KEY`) — for direct Mistral fast-tier.

## 1. Dependencies

```bash
cd D:\RAG_Support_Assistant
python -m venv .venv
. .venv/Scripts/activate          # Windows PowerShell: . .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Configuration

```bash
cp .env.example .env              # Windows: copy .env.example .env
```

Open `.env` and fill in the required values. Minimal scenarios:

| Scenario | Required variables |
| --- | --- |
| **GraceKelly primary** (default) | `GRACEKELLY_BASE_URL=http://127.0.0.1:8011`, `LLM_PROVIDER_PROFILE=gracekelly-primary` is implied |
| **Local-only Ollama** | `LLM_PROVIDER_PROFILE=local-first` |
| **+ Mistral fast tier** | `MISTRAL_API_KEY=<key>` + `LLM_PROVIDER_PROFILE=external-mistral` |
| **GraceKelly mixed routing** (Claude Sonnet 4.6 reasoning) | `MISTRAL_API_KEY=<key>` + `LLM_PROVIDER_PROFILE=gracekelly-mixed` + `GRACEKELLY_REQUEST_TIMEOUT_SEC=120` |

Full list of variables — see `README.md` section **Environment Variables**.

## 3. Infrastructure (Postgres + Redis)

For dev — spin up disposable containers:

```bash
docker run -d --name rag-postgres -p 5432:5432 \
    -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag_dev_password -e POSTGRES_DB=rag_assistant \
    postgres:16-alpine

docker run -d --name rag-redis -p 6379:6379 redis:7-alpine
```

Then run migrations:

```bash
alembic upgrade head
```

## 4. Scenario A — GraceKelly primary (default)

```bash
# Start GraceKelly in a separate terminal
cd D:\GraceKelly
uvicorn gracekelly.main:create_app --factory --host 127.0.0.1 --port 8011

# Launch RAG Support Assistant
cd D:\RAG_Support_Assistant
python main.py
```

Open `http://localhost:8000/static/login.html` (password + SSO) or
`http://localhost:8000/static/chat.html` (chat UI). After login —
`/agent` for the agent copilot dashboard. (legacy `/` index UI was removed
2026-04-27 — it was unauthenticated, see SESSION-NOTES-2026-04-27.)

`gracekelly-primary` profile routes fast and strong tiers through the local GraceKelly orchestrator. `/api/health/ready` checks GraceKelly readiness and does not require Ollama if the active profile does not use Ollama.

## 5. Scenario B — explicit Local-only Ollama

```bash
# Start Ollama and pull models
ollama serve &
ollama pull qwen2.5:7b

# Launch with explicit local-first profile
LLM_PROVIDER_PROFILE=local-first python main.py
```

## 6. Scenario C — GraceKelly mixed routing

Useful when you need reasoning quality (Claude Sonnet 4.6) for final answers, but want background processing (classification, grade_docs, verify_facts) handled by fast Mistral API.

1. Start GraceKelly (separate project):

   ```bash
   cd D:\GraceKelly
   $env:GRACEKELLY_EXECUTION_PROFILE = "hybrid"
   uvicorn gracekelly.main:create_app --factory --host 127.0.0.1 --port 8011
   ```

2. In `D:\RAG_Support_Assistant\.env`:

   ```
   MISTRAL_API_KEY=<your-key>
   LLM_PROVIDER_PROFILE=gracekelly-mixed
   GRACEKELLY_REQUEST_TIMEOUT_SEC=120
   ```

3. Launch RAG:

   ```bash
   python main.py
   ```

`gracekelly-mixed` profile routes fast tier through Mistral API (~1-3s/call), strong tier (final answer) through GraceKelly browser → Perplexity Pro (Claude Sonnet 4.6, ~30-60s/call).

## 7. Document ingestion and first query

```bash
# Document for ingestion (PDF, MD, TXT)
# PowerShell (Windows) — note: curl.exe, not curl (which is the Invoke-WebRequest alias)
curl.exe -X POST http://localhost:8000/api/upload `
    -H "Authorization: Bearer <admin-jwt>" `
    -F "file=@docs/warranty.md"

# Bash (Linux/macOS)
curl -X POST http://localhost:8000/api/upload \
    -H "Authorization: Bearer <admin-jwt>" \
    -F "file=@docs/warranty.md"

# First query
# PowerShell (Windows)
curl.exe -X POST http://localhost:8000/api/ask `
    -H "Authorization: Bearer <admin-jwt>" `
    -H "Content-Type: application/json" `
    -d '{"question":"What is the warranty period?"}'

# Bash (Linux/macOS)
curl -X POST http://localhost:8000/api/ask \
    -H "Authorization: Bearer <admin-jwt>" \
    -H "Content-Type: application/json" \
    -d '{"question":"What is the warranty period?"}'
```

To get admin JWT for dev: `POST /api/auth/login` with `admin/admin` (if `ADMIN_PASSWORD_HASH` is not set in `.env`).

## 8. Health checks

```bash
curl http://localhost:8000/api/health/live      # liveness
curl http://localhost:8000/api/health/ready     # readiness (dependencies)
curl http://localhost:8000/api/metrics          # metrics snapshot
curl http://localhost:8000/api/admin/providers  # active routing profile + recent usage (auth)
```

## 9. Regression eval

For continuous quality checks against a curated 20-case dataset:

```bash
# Mock provider benchmark (no GK, no quota burn)
python scripts/regression_eval.py \
    --baseline ollama-small \
    --candidate mistral-small-latest \
    --max-cases 5 \
    --no-persist

# Live GK mixed routing (requires explicit paid/API opt-in)
python scripts/regression_eval.py \
    --baseline ministral-3b-latest \
    --candidate-profile gracekelly-mixed \
    --max-cases 20 \
    --allow-paid-apis
```

Without `--allow-paid-apis`, provider/model targets run in `mock-provider-benchmark` mode:
answers and cost/latency metrics are simulated from `evaluation/curated_cases.jsonl`,
so the command does not call GraceKelly or Mistral and does not persist to the DB when
`--no-persist` is set. Live provider calls require explicit opt-in via `--allow-paid-apis`.

Results are written to `reports/regression/<timestamp>-*.{json,md}`. PowerShell wrapper
`scripts\run_regression_via_gracekelly.ps1 -AllowLive` spins up disposable Postgres + Redis + ingestion + regression in one command after explicit live opt-in.

## 10. Common issues

:::caution[vector store is not initialized]
No ingested documents found. Upload via `POST /api/upload` or run the ingestion script.
:::

:::caution[[provider_unavailable]]
Circuit breaker is open at the adapter. Wait for cooldown (60s) or reset manually: `POST /api/admin/circuit-breaker/reset`.
:::

:::caution[[model_mismatch] … but UI shows 'Sonar']
Perplexity server-side auto-router replaced the model. This is an external GK error, classified as `infrastructure_failure` in regression eval. Reconsider the query or try a different phrasing.
:::

:::caution[HF_HUB_OFFLINE=1]
If `HF_HUB_OFFLINE=1` is set in env but `BAAI/bge-m3` is not cached — embeddings will fail. Pull the model once with `HF_HUB_OFFLINE` empty, then re-enable.
:::

:::caution[Postgres DuplicateObject on ENUM]
Migration 012 is sensitive to duplicate `CREATE TYPE`. Fixed in `d163942`; if you hit this — update the branch.
:::

## 11. Where to go next

- `README.md` — full list of env vars + public endpoints + Prometheus metrics.
- `docs/runbook.md` — operational runbook for on-call (alerts, diagnostics, actions).
- `docs/disaster-recovery.md` — DR scenarios A-F (data loss, encryption, encryption-key).
- `docs/operations/` — runbooks for backup, helm, gracekelly smoke.
- `docs/CHANGELOG.md` — change history by arcs.
