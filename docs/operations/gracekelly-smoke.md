# GraceKelly smoke runbook

Manual runtime smoke for the live GraceKelly integration in `RAG_Support_Assistant`.
This script is intentionally not wired into CI.

> **Live warning.** Run this smoke only after explicit user opt-in. It targets
> live GraceKelly runtime behavior and may exercise browser-backed or API-backed
> upstream paths depending on the active GraceKelly configuration.
>
> 2026-05-30 readiness note: Mistral key presence was validated without
> printing the value, but local GraceKelly was not reachable on
> `http://127.0.0.1:8011/healthz/ready`. This runbook still requires a staged
> runtime; do not start it in constrained local sessions.

## Preconditions

- `D:\GraceKelly\` is running and listening on `http://127.0.0.1:8011`.
- RAG is running on `http://127.0.0.1:8000`.
- RAG was started with `LLM_PROVIDER_PROFILE=gracekelly-primary`.
- RAG reads `GRACEKELLY_BASE_URL`, so the effective `.env` / process environment should contain:
  `GRACEKELLY_BASE_URL=http://127.0.0.1:8011`
- A Prometheus scrape baseline was collected before the smoke run.

## Auth

If RAG enforces auth, export one of these before running the smoke:

- `API_KEY=<value>` for `X-API-Key`
- `RAG_BEARER_TOKEN=<jwt>` for bearer auth

If GraceKelly requires bearer auth for `/api/v1/orchestrate`, export:

- `GRACEKELLY_API_KEY=<value>`

## Run

Healthy-path smoke:

```bash
python scripts/gracekelly_smoke.py --verbose
```

Failover-only smoke:

```bash
python scripts/gracekelly_smoke.py --simulate-down --verbose
```

`--simulate-down` does not hot-switch the upstream URL inside a running RAG process.
Use it only against a RAG instance that was already started with unreachable
GraceKelly upstream, for example:

```bash
set LLM_PROVIDER_PROFILE=gracekelly-primary
set GRACEKELLY_BASE_URL=http://127.0.0.1:9999
python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
python scripts/gracekelly_smoke.py --simulate-down --verbose
```

An alternative is to stop the real GraceKelly process before the failover run.

## What The Script Verifies

Default run:

- step 1: direct GraceKelly readiness on `/healthz/ready`
- step 2: active RAG provider profile is GraceKelly-backed
- step 3: `/api/ask` returns a live answer and trace metadata shows `provider=gracekelly`
- step 4: tool loop is visible in trace data when the current runtime exposes it; otherwise `SKIPPED`
- step 5: direct GraceKelly schema dispatch on `/api/v1/orchestrate`
- step 6: SSE streaming on `/api/chat/stream`
- step 7: Prometheus metrics for GraceKelly cost accounting; zero-cost current-runtime gaps are reported as `SKIPPED`
- step 8: `SKIPPED` by default, because failover needs a separately prepared runtime

`--simulate-down` run:

- steps 1-7 are marked `SKIPPED`
- step 8 asserts GraceKelly -> Ollama fallback via `llm_provider_fallback_total{from_provider="gracekelly",to_provider="ollama",reason="unavailable"}`

## Example Output

```text
✓ step 1 healthz (18.4 ms): 200 ready
✓ step 2 profile (11.7 ms): active_profile=gracekelly-primary
✓ step 3 simple ask (1432.6 ms): trace=9a8f... provider=gracekelly model=claude-sonnet-4-6-api answer_len=2
~ step 4 tool loop (1268.3 ms): tool loop not observable in current runtime (likely RAG_AGENTIC_MODE=false or no GraceKelly tool trace)
✓ step 5 schema (802.1 ms): model=claude-sonnet-4-6-api route=support
✓ step 6 streaming (1644.0 ms): chunks=7 final=type=result
~ step 7 metrics (21.3 ms): llm_cost_usd_total does not export zero-cost GraceKelly traces in the current runtime
~ step 8 failover (0.0 ms): rerun with --simulate-down against a RAG instance started with unreachable GRACEKELLY_BASE_URL or with GraceKelly stopped

step           status   latency_ms  detail
-------------  -------  ----------  ----------------------------------------
1 healthz      PASS          18.4   200 ready
2 profile      PASS          11.7   active_profile=gracekelly-primary
3 simple ask   PASS        1432.6   trace=9a8f... provider=gracekelly model=claude-sonnet-4-6-api answer_len=2
4 tool loop    SKIPPED     1268.3   tool loop not observable in current runtime (likely RAG_AGENTIC_MODE=false or no GraceKelly tool trace)
5 schema       PASS         802.1   model=claude-sonnet-4-6-api route=support
6 streaming    PASS        1644.0   chunks=7 final=type=result
7 metrics      SKIPPED       21.3   llm_cost_usd_total does not export zero-cost GraceKelly traces in the current runtime
8 failover     SKIPPED        0.0   rerun with --simulate-down against a RAG instance started with unreachable GRACEKELLY_BASE_URL or with GraceKelly stopped
```

## Exit Codes

- `0`: all required checks passed; any skipped steps were explicitly marked `SKIPPED`
- `1`: GraceKelly readiness failed
- `2`: profile or simple ask failed
- `3`: tool-loop validation failed
- `4`: schema dispatch failed
- `5`: streaming failed
- `6`: metrics failed
- `7`: failover failed

## Troubleshooting

- GraceKelly readiness fails with `GraceKelly not reachable at ... start D:\GraceKelly\ first`:
  start `D:\GraceKelly\`, then retry the smoke.
- `/api/admin/providers` does not show `gracekelly-primary`:
  restart RAG with `LLM_PROVIDER_PROFILE=gracekelly-primary`.
- step 3 shows `provider=ollama` instead of `gracekelly`:
  check RAG logs and the active GraceKelly URL; the runtime is already on fallback.
- step 4 is `SKIPPED`:
  check whether `RAG_AGENTIC_MODE=true` is enabled and whether GraceKelly tool traces are wired for the current route.
- step 6 final marker is `type=result` instead of `done=true`:
  this is the current SSE contract in `api/app.py`; the smoke accepts it as the live completion marker.
- step 7 is `SKIPPED` for cost metrics:
  current Prometheus export ignores `cost_usd <= 0`, while GraceKelly traces store `cost_usd=0.0`.
- `--simulate-down` does not trigger fallback:
  make sure the target RAG instance itself was started with unreachable `GRACEKELLY_BASE_URL` or that the real GraceKelly process is stopped before running the failover smoke.
