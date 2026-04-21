# GitHub Readiness: RAG Support Assistant

**Assessment date**: 2026-04-02

## What it is
- One-sentence description: A local Python/FastAPI proof-of-concept for a support-oriented RAG assistant with LangGraph routing, local Ollama inference, SQLite tracing, and optional human escalation to a JSONL inbox or Bitrix24.
- Problem it solves: It tries to answer support questions from local documents, grade answer quality, and escalate uncertain cases instead of silently hallucinating.
- Target audience: ML engineers, solution architects, internal tooling teams, and support automation teams that want an on-prem/local-first RAG prototype, especially in environments that care about privacy or Bitrix24 integration.
- Tech stack: Python, FastAPI, LangChain, LangGraph, Chroma, SQLite, Ollama, sentence-transformers, BM25 reranking helpers, Jinja/HTML/CSS/JS, optional Bitrix24 webhook integration.

## Uniqueness
- Similar projects on GitHub:
  - `curiousily/ragbase` - https://github.com/curiousily/ragbase
  - `stackitcloud/rag-template` - https://github.com/stackitcloud/rag-template
  - `srbhr/Local-RAG-with-Ollama` - https://github.com/srbhr/Local-RAG-with-Ollama
  - `cpepper96/ollama-local-rag` - https://github.com/cpepper96/ollama-local-rag
  - `Isa1asN/local-rag` - https://github.com/Isa1asN/local-rag
- What makes THIS one different: The best differentiator is not "local RAG" itself, because GitHub already has many of those. The differentiator is the support-ops angle: quality scoring, auto-vs-human routing, local SQLite tracing, and Bitrix-oriented escalation.
- Would someone star this? Why? Honest answer: not in its current state. If cleaned up and made reproducible, it could earn stars from teams looking for a practical "local support RAG" starter rather than yet another generic chat-with-docs demo.

## Completeness
| Aspect | Status | Details |
|--------|--------|---------|
| Core functionality works | partial | Some lower-level modules import, but the default app entrypoints do not import cleanly in this workspace. Import smoke checks for `main`, `api.app`, and `graph` failed because several root modules resolve paths one level too high and try to use `D:\\data`. |
| Has README | yes | quality: good, but it is currently untracked in git and materially out of sync with the real file/module layout. |
| Has tests | yes | 4 root-level test modules, but `pytest -q` fails during collection with missing modules (`agent.graph`, `integrations.mock_inbox`, `demo.seed_docs`). Coverage estimate: low and currently non-actionable because the suite is broken before execution. |
| Has examples/docs | yes | There is substantial narrative documentation and a chat UI, but README examples reference files and functions that do not exist in the tracked project state. The `demo/` folder is effectively empty in this workspace. |
| Has license | no | No `LICENSE` file found. This is a real blocker for public GitHub release. |
| Has .gitignore | yes | Present and sensible for Python/local data. It excludes `data/`, `.env`, and database/cache artifacts. |
| No hardcoded secrets/paths | no | No obvious secrets were found, but several root modules compute the project root incorrectly and effectively point runtime data to `D:\\data` instead of the repo's `data/` directory. |
| No personal data | yes | No obvious personal/customer data was found in inspected source/docs. Local runtime artifacts exist under ignored `data/`, but they are not part of the tracked repo snapshot. |
| Dependencies are standard | no | Most dependencies are standard OSS packages, but the repo has declaration/runtime drift: e.g. `bitrix.py` imports `requests`, which is not in `requirements.txt`, and major runtime functionality depends on many untracked files. |

## Code quality
- Estimated quality: 4/10
- Code style consistency: mixed
- Architecture: acceptable on paper, but messy in the delivered repository state
- Comments/docs in code: good
- Language: mixed; code identifiers are mostly English, but many comments/docs are Russian. For broad GitHub adoption, README and user-facing docs should be English or bilingual.

## Before publishing (must fix)
| # | What | Severity | Effort |
|---|------|----------|--------|
| 1 | Make the repository coherent in git: right now only a small tracked core exists, while many important modules/docs/tests/UI files are untracked. Decide what actually belongs in the public repo and commit/clean accordingly. | CRITICAL | M |
| 2 | Fix the package/layout mismatch. The codebase mixes "root-level modules" with a package-shaped narrative (`agent/*`, `integrations/*`, `vectordb/*`) that does not actually exist in tracked form. This causes import failures and broken tests. | CRITICAL | M |
| 3 | Fix path resolution bugs in root modules (`main.py`, `mock_inbox.py`, `sqlite_trace.py`) that resolve the project root one level too high and try to use `D:\\data`. | CRITICAL | S |
| 4 | Make the default app runnable. `main.py` expects a `templates/` directory that does not exist, and README commands reference modules/files such as `api/main.py`, `ingestion.chunking`, `vectordb.manager`, and `demo/seed_docs.py` that are missing or untracked. | CRITICAL | M |
| 5 | Repair or replace the test suite so `pytest` is green. Public release with tests that fail during collection looks careless and undermines trust immediately. | HIGH | M |
| 6 | Add a license. Without one, the public repo is legally unclear and less usable than its code quality alone would suggest. | HIGH | S |

## Before publishing (should fix)
| # | What | Why | Effort |
|---|------|-----|--------|
| 1 | Rewrite README against the actual repository state | The current README is detailed, but it overpromises and references missing modules/functions, which is worse than having a shorter README. | M |
| 2 | Add `.env.example` and a minimal reproducible setup path | Public users need one obvious happy path for Ollama model setup, env vars, and first run. | S |
| 3 | Declare missing dependencies such as `requests` | Small packaging mistakes create avoidable first-run failures. | S |
| 4 | Translate or normalize docs/comments to English or bilingual | The repo is much easier to star, fork, and contribute to if the public-facing narrative is not mostly Russian-only. | M |
| 5 | Add CI for imports/tests/smoke checks | This repo needs automated proof that entrypoints, tests, and packaging remain aligned. | M |
| 6 | Remove duplicate or misleading architectural narratives | There are multiple parallel descriptions of a cleaner package structure than what is actually present. That makes the repo feel half-migrated. | M |
| 7 | Provide real demo data or a tiny sample corpus | The support use case is easier to evaluate if the repo ships with a working demo scenario instead of referencing absent `demo/docs`. | S |
| 8 | Add a screenshot/GIF of the UI and a clear product pitch | The project's strongest selling point is practical workflow, not raw novelty. Show it quickly. | S |

## Scores
| Metric | Score (1-10) | Comment |
|--------|-------------|---------|
| Usefulness (does it solve a real problem?) | 8 | The problem is real and practical: private/local support QA with escalation instead of blind automation. |
| Uniqueness (is there already something better?) | 6 | Generic local RAG repos are common, but the support-routing + Bitrix + SQLite tracing angle gives this project some identity. |
| Completeness (can someone use it as-is?) | 3 | Not reliably. The repo structure, tests, README, and runnable entrypoints do not currently line up. |
| Code quality | 4 | There is real implementation work here, but the delivered tree looks half-reorganized and not release-curated. |
| Documentation | 4 | Volume is good; accuracy is not. Public docs must match the code that is actually in the repo. |
| **Overall GitHub-ready** | **3** | **Interesting idea, not publish-ready repository.** |

## Verdict
FIX THEN PUBLISH

Reason: The concept is useful enough to justify a public repo, and it has a plausible niche as a local support RAG starter. But the current workspace is not release-ready because repository contents, runtime layout, tests, and documentation disagree with each other in ways that will immediately break first impressions.
