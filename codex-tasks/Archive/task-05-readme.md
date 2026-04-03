# Task 05 — README.md

## Write README.md in project root

Fill in the template below. Replace every `[...]` with actual content from the codebase.
Read the following files before writing: api/app.py (endpoints), config/settings.py (env vars),
graph.py (pipeline nodes), docker-compose.yml.

---

```markdown
# RAG Support Assistant

[2-3 sentences: what the system does, what tech stack, what problem it solves]

## Architecture

Pipeline flow:
```
transform_query → retrieve → grade_docs → generate → evaluate → route_or_retry
                                                                      ↓        ↓
                                                                   log      handle_error
                                                                   ↓              ↓
                                                                  END      escalate + END
```

- **Retrieval**: [describe hybrid search: BM25 + ChromaDB + cross-encoder reranker]
- **Generation**: [LLM used, where it runs]
- **Evaluation**: [what quality_score means, when auto vs human]
- **Escalation**: [what happens on route=human or route=error]

## Quick Start

**Prerequisites:** Python 3.11+, [Ollama install command]

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start Ollama and pull model
ollama serve
ollama pull mistral

# 3. Run
python main.py
```

Open http://localhost:8000

## Environment Variables

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Description |
|----------|---------|-------------|
[fill one row per variable from config/settings.py — 8-10 most important ones]

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/ask | [description] |
| POST | /api/upload | [description] |
| GET | /api/health | [description] |
| GET | /api/sessions/{id}/history | [description] |
| DELETE | /api/sessions/{id} | [description] |

## Tests

```bash
pytest tests/ -v
```

## Docker

```bash
cp .env.example .env
# Edit .env — set OLLAMA_BASE_URL to your Ollama host
docker compose up
```
```

---

## CONSTRAINTS
- Write ONLY `README.md`
- Max 120 lines
- No placeholder `[...]` left in the final file — fill everything in
- Do NOT modify any other file

## DONE WHEN
- [ ] `README.md` exists and has no `[...]` placeholders
- [ ] File is under 120 lines
