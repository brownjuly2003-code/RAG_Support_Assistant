# Quickstart — RAG Support Assistant

> The minimum steps to run the service **locally** and verify it works.
>
> **No hosted Hugging Face Space** is provided or planned. Users run this
> application on their own machine. Hugging Face is not a required publication
> or user-runtime dependency for the external-user recipe below.

## 0. Requirements

- Python 3.11+ (tested on 3.13)
- Docker Desktop (for Postgres + Redis in dev and for regression eval)
- Disk/RAM depend on the selected profile (Ollama models need extra space;
  the external Mistral + remote embeddings path does not download local
  embedding/reranker weights)

Per selected profile:
- **External Mistral (recommended for external users)** — your own
  `MISTRAL_API_KEY`; remote embeddings; local reranker disabled. No model-hub
  download for embeddings/reranker.
- **Ollama** (`https://ollama.com/download`) — repository default
  `local-first` provider for owner/local use; no API key.
- **GraceKelly** — optional owner/internal orchestrator (separate install).

## 1. Dependencies

```bash
# From your clone of this repository
python -m venv .venv
. .venv/Scripts/activate          # Windows PowerShell: . .venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
```

## 2. Configuration

```bash
cp .env.example .env              # Windows: copy .env.example .env
```

Open `.env` and fill in the required values. Minimal scenarios:

| Scenario | Required variables |
| --- | --- |
| **External user: Mistral + remote embeddings (no HF download)** | See **Scenario A** below |
| **Local-only Ollama** (repo default for owner) | Start Ollama and pull `qwen2.5:7b`; `LLM_PROVIDER_PROFILE=local-first` is implied |
| **Direct Mistral (generation only)** | `MISTRAL_API_KEY=<your-key>` + `LLM_PROVIDER_PROFILE=external-mistral` (local embeddings/reranker still follow other defaults unless overridden) |
| **GraceKelly primary** (owner/internal) | GraceKelly base URL + `LLM_PROVIDER_PROFILE=gracekelly-primary` |
| **GraceKelly mixed routing** (owner/internal) | `MISTRAL_API_KEY=<your-key>` + `LLM_PROVIDER_PROFILE=gracekelly-mixed` + `GRACEKELLY_REQUEST_TIMEOUT_SEC=120` |

Full list of variables — see `docs/CONFIGURATION.md` and `README.md`.

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

## 4. Scenario A — External user: Mistral API + remote embeddings (no HF download)

Recommended path when you only have a Mistral API key and want to avoid
downloading local embedding/reranker models from a model hub.

Verified against current settings/code (`config/settings.py`,
`vectordb/_base_manager.py`, `docs/CONFIGURATION.md`):

- `LLM_PROVIDER_PROFILE=external-mistral` → direct Mistral for generation
  (`config/providers.yml`)
- `RAG_EMBEDDING_BACKEND=remote` + remote URL/model/key-env → Mistral-compatible
  embeddings API (no local SentenceTransformer load)
- `RAG_RERANKER_MODEL=` (empty) → `get_reranker()` returns `None` and skips the
  cross-encoder model download

In `.env`:

```dotenv
LLM_PROVIDER_PROFILE=external-mistral
MISTRAL_API_KEY=<your-key>
RAG_EMBEDDING_BACKEND=remote
RAG_EMBEDDING_REMOTE_URL=https://api.mistral.ai/v1/embeddings
RAG_EMBEDDING_REMOTE_MODEL=mistral-embed
RAG_EMBEDDING_REMOTE_API_KEY_ENV=MISTRAL_API_KEY
RAG_RERANKER_MODEL=
```

Then:

```bash
alembic upgrade head
python main.py
```

Open `http://localhost:8000/static/login.html` or
`http://localhost:8000/static/chat.html`.

Placeholder keys such as `changeme` are rejected. This recipe does **not** claim
the whole repository has zero historical Hugging Face references; it only
defines a user path that does not require HF downloads at runtime.

If you switch embedding backends or dimensions against an existing Chroma
directory, set a fresh `VECTORDB_CHROMA_DIR` and re-ingest documents.

## 5. Scenario B — Local-only Ollama (owner default)

Repository default remains `local-first`. Unchanged for owner/internal use.

In terminal A:

```bash
ollama serve
```

In terminal B:

```bash
ollama pull qwen2.5:7b
python main.py
```

Open `http://localhost:8000/static/login.html` (password + SSO) or
`http://localhost:8000/static/chat.html` (chat UI). After login —
`/agent` for the agent copilot dashboard. (legacy `/` index UI was removed
2026-04-27 — it was unauthenticated, see SESSION-NOTES-2026-04-27.)

`local-first` routes both fast and strong tiers through local Ollama.
`/api/health/ready` checks Ollama readiness. Set `REQUIRE_OLLAMA=true` if startup
must fail immediately when Ollama is unavailable.

Default local embedding/reranker settings may still download models unless you
override them (see Scenario A for the remote/no-reranker profile).

## 6. Scenario C — Optional GraceKelly routing (owner/internal)

Owner/internal only. Use `gracekelly-primary` for both tiers, or
`gracekelly-mixed` when final answers should use GraceKelly while helper calls
use your direct Mistral key. These profiles are **unchanged** and are separate
from the external-user Scenario A recipe.

1. Start GraceKelly (separate project on your machine).

2. In `.env`, choose one explicit profile:

   ```dotenv
   # GraceKelly for both tiers
   LLM_PROVIDER_PROFILE=gracekelly-primary

   # Or mixed routing (requires your Mistral key)
   MISTRAL_API_KEY=<your-key>
   LLM_PROVIDER_PROFILE=gracekelly-mixed
   GRACEKELLY_REQUEST_TIMEOUT_SEC=120
   ```

3. Launch RAG:

   ```bash
   python main.py
   ```

`gracekelly-mixed` routes the fast tier through Mistral API and the strong tier
through the optional GraceKelly orchestrator.

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
