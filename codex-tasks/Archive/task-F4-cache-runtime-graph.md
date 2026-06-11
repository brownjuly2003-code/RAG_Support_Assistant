# Task F-4 — Cache provider runtime + compiled LangGraph graph (4 traps)

> ✅ **IMPLEMENTED 2026-06-11 (Fable hardening, сессия 3), commit `63a3ee4`.**
> All 4 traps handled; tests in `tests/test_provider_runtime_cache.py` (6/6).
> Kept as the design record.

> De-scoped from the 2026-06-11 Fable-Hardening batch **on purpose**: trap #2 below
> is a money-safety regression and the change is concurrency-sensitive. Current
> behaviour is correct (just rebuilds per request) — this is an optimization, not a
> bug fix. Spec author found trap #2; the original handoff (`fable_com.md` F-4,
> `next-session-fable-hardening.md` §4) only flagged trap #1.

## Goal

Avoid rebuilding the provider runtime (YAML reload + provider instantiation) and
recompiling the LangGraph graph on every `/api/ask`. Today, per request:

- `build_provider_runtime(settings)` (`llm/providers/runtime.py:254`) reloads
  `config/providers.yml`, resolves the profile, runs the daily-cost check, and
  instantiates fast+strong `ProviderBackedLLM`. Call sites: `api/routers/conversation.py:621`
  (streaming), `agent/graph.py:1810-1811` (inside `build_support_graph`),
  `agent/graph.py:2100-2104` (`ConversationSession.__init__`).
- `build_support_graph(retriever, llm, min_quality, max_iterations)` (`agent/graph.py:1787`)
  constructs **and compiles** a fresh `StateGraph` every call (`agent/graph.py:1958`,
  inside `run_qa_pipeline`), and internally calls `build_provider_runtime` (`:1810`)
  to obtain the fast/strong LLMs the graph closes over. So `llm_fast`/`llm_strong`
  originate there.

## TRAPS — all four must be handled, or do not ship

1. **`last_response` mutable per-instance state.** `ProviderBackedLLM.last_response`
   (`llm/providers/base.py:256`; written at `:306,:323,:339,:357,:444`) is read in
   `agent/graph.py:557` (`_capture_llm_usage`) immediately after each invoke. Today
   each request builds its own LLM instance, so no race. Once a cached instance is
   shared across the `asyncio.to_thread` worker threads that run `run_qa_pipeline`,
   concurrent requests overwrite each other's `last_response` → wrong usage/cost
   attribution. **Fix:** back `last_response` with `threading.local`, preserving the
   public attribute semantics.

2. **DAILY COST LIMIT — money-safety.** `build_provider_runtime` calls
   `_enforce_daily_cost_limit(settings, registry, profile_name)` (`runtime.py:257`),
   which runs a **per-request** SQLite spend query (`_daily_paid_cost_usd`) and raises
   when `DAILY_COST_LIMIT_USD` is reached. If the whole runtime is cached, this check
   is cached too → **the spend cap silently stops enforcing** and paid-API spend can
   run unbounded. **Fix:** cache only the registry load + provider instantiation; run
   `_enforce_daily_cost_limit` on **every** request even on a cache hit.

3. **`id()`-based graph cache key + GC reuse.** Keying the compiled graph by
   `(id(retriever), id(llm_fast), id(llm_strong), …)` is only safe if those objects
   are long-lived. If they're rebuilt per request and GC'd, a new object can reuse a
   freed `id()` → a **wrong cache hit** (stale graph bound to dead LLMs). **Fix:** only
   add the graph cache *after* the runtime cache (step 2) holds strong refs to stable
   fast/strong instances. Prefer keying by the runtime cache key
   `(profile_name, mtime)` + `id(retriever)` + `min_quality` + `max_iterations`, and
   keep strong references so ids cannot be reused.

4. **Thread-safety of shared providers.** Cached fast/strong providers are shared
   across `to_thread` worker threads. The dominant mutable state is `last_response`
   (fixed by trap #1) — but audit for any other per-instance mutation, and confirm the
   underlying clients (httpx / requests / ollama / GraceKelly) are safe for concurrent
   use. The failover cache helpers in `runtime.py` use module-level state keyed by a
   tuple — confirm they remain correct under concurrency.

## Implementation order (each step independently testable)

**Step 1 — `threading.local` for `last_response`** (`llm/providers/base.py`).
Correctness prerequisite; ship/verify alone first. Keep `llm.last_response` working as
a read/write attribute (property backed by a `threading.local`). `tests/test_provider_abstraction.py`
asserts `llm.last_response is response` *within one thread* → must still pass. Add a
concurrency test: two threads each `generate()` then read `last_response`; assert no
cross-talk.

**Step 2 — runtime cache** (`llm/providers/runtime.py`). Cache `(registry, resolved
profile, fast/strong providers)` keyed by `(profile_name, mtime(provider_registry_path))`.
On a hit, **reuse** the cached `ProviderRuntime` but **still call**
`_enforce_daily_cost_limit` every request (trap #2). Invalidate on `providers.yml`
mtime change. Tests: (a) a second call with the file unchanged does **not** re-instantiate
providers (monkeypatch `_build_provider` with a call counter); (b) the cost limit still
**raises on every call** when over budget (monkeypatch `_daily_paid_cost_usd` high);
(c) an mtime change rebuilds.

**Step 3 — compiled-graph cache** (`agent/graph.py` `build_support_graph`). Cache the
compiled graph keyed by `(runtime cache identity, id(retriever), min_quality,
max_iterations)`. Only after step 2 (stable runtime). Tests: a second
`build_support_graph` with the same retriever+runtime returns the **same** compiled
object (identity); a different `min_quality` → a different object; a concurrency test
that two threads invoking `run_qa_pipeline` share the graph without state corruption
(LangGraph compiled graphs carry no per-invoke state — state is passed into `invoke()`).

## Files to change
- `llm/providers/base.py` — `threading.local`-backed `last_response`
- `llm/providers/runtime.py` — runtime cache; keep daily-cost check per-request
- `agent/graph.py` — compiled-graph cache in `build_support_graph`

## Files to create
- `tests/test_provider_runtime_cache.py` — runtime cache reuse + cost-limit preserved
  + mtime invalidation + `last_response` thread isolation + graph cache identity +
  concurrency

## Acceptance
- All existing tests green, especially `tests/test_provider_abstraction.py`,
  `tests/test_model_routing.py`, `tests/test_online_evaluators.py`,
  `tests/test_provider_graph_integration.py`.
- `DAILY_COST_LIMIT_USD` still enforced **per request** (new test proves it).
- No cross-thread `last_response`/usage bleed (new concurrency test).
- `ruff` + `py_compile` clean.

## Gotchas / context
- Full suite on this machine only with `RAG_RERANKER_MODEL=""` (AGENT_STATE cont.14).
- `manager.get_retriever(embeddings=None)` pulls the real BGE-M3 in tests — stub
  `manager.get_embeddings` (see `tests/test_chunks_restore.py`).
- Confirm whether `build_support_graph`'s `llm` parameter is actually used or whether
  it always re-derives fast/strong from `build_provider_runtime` at `:1810` — the cache
  key must reflect what the compiled graph truly closes over.
