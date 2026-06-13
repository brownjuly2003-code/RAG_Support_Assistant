# Adaptive Retrieval — Track R / R1: lightweight router classifier

> Date: 2026-06-14 · Workstream: adaptive-retrieval (Track R, router cost).
> Plan: `docs/plans/2026-06-13-adaptive-retrieval-factcard-plan.md` (Track R, R1).
> Artifacts: `evaluation/adaptive_retrieval/train_router_classifier.py` (harness),
> `evaluation/adaptive_retrieval/r1_router_results.json` (results).
> Verdict: **R1 verify met and exceeded** — a cheap classifier is *both* more
> accurate on the shipped routing decision *and* free, vs the LLM router.
> Wiring it in (R2) stays **gated** on the Phase-5 offline delta.

## Goal (R1)

> Plan R1: "Обучить TF-IDF+SVM (или MiniLM) на Phase-0-разметке; сравнить с LLM
> `classify_complexity` по macro-F1 **и** по токенам/latency → Verify: F1 не хуже
> + экономия per-query вызова."

Train a lightweight classifier on the Phase-0 labels and compare it against the
existing LLM `classify_complexity` node on **macro-F1** and **cost**.

## Method

- **Data:** `evaluation/adaptive_retrieval/phase0_labels.jsonl` — 135 hand-labelled
  queries (`query_class` ∈ {simple, factual, enumeration, multi-condition};
  `needs_factcard` bool). Source of truth: `build_phase0_labels.py`.
- **Lightweight classifier:** TF-IDF (`word` 1–2 grams + `char_wb` 3–5 grams,
  sublinear tf) → `LinearSVC(class_weight="balanced")`. Char n-grams give cheap
  robustness to Russian morphology without a stemmer. Evaluated with
  **stratified 5-fold cross-validation** (seed 42), so every score is on
  held-out folds (no leakage; the vectorizer is refit per fold via a Pipeline).
- **Targets.**
  - `query_class` (4-class) — the literal Phase-0 taxonomy.
  - **`route` (binary)** — the decision that actually ships through
    `agent.graph._select_retrieval_strategy`. With the default
    `retrieval_strategy="hybrid"` config the only complexity-driven branch is
    `complexity=="simple" → vector`, else `hybrid` (graph only if configured
    graph + global). So we derive the routing gold from `query_class`:
    `{simple, factual} → vector`, `{enumeration, multi-condition} → hybrid`.
    The LLM emits `SIMPLE/COMPLEX/GLOBAL`, a different taxonomy — `route` is the
    only apples-to-apples target both classifiers can be scored on.
  - `needs_factcard` (binary) — relevant to the Track-F lane router.
- **LLM baseline:** `ministral-3b-latest` via the `external-mistral` profile —
  the fast-tier model that `classify_complexity` uses in the `gracekelly-mixed`
  / `external-mistral` routing profiles. Prompt + parsing copied verbatim from
  `agent/prompts.py` (`CLASSIFY_COMPLEXITY_PROMPT_V1`) and
  `agent.graph.make_classify_complexity_node`, then mapped complexity→route the
  same way the graph does. Live run: 135/135 queries, **0 errors**. (The default
  profile `gracekelly-primary` uses GraceKelly/`sonar-2` for the fast tier;
  driving 135 browser submits is heavy/flaky on Windows, so ministral-3b — the
  realistic *routing-enabled* classify model — is the baseline.)

## Results

### Lightweight classifier (stratified 5-fold CV)

| target | macro-F1 | accuracy |
|---|---|---|
| `query_class` (4-class) | **0.6345** | 0.6963 |
| **`route` (binary)** | **0.8313** | 0.8741 |
| `needs_factcard` (binary) | **0.8712** | 0.8889 |

Per-class (`route`): hybrid P0.877 R0.959 **F1 0.916** (n=97) · vector P0.862
R0.658 **F1 0.746** (n=38).
Per-class (`needs_factcard`): factcard P0.897 R0.761 **F1 0.824** (n=46) · no
P0.885 R0.955 **F1 0.919** (n=89).
4-class is dragged down by `factual` (F1 0.370, n=18) — it gets confused with
`simple`/`enumeration`; the small support and the fuzzy simple↔factual boundary
explain it. This does **not** hurt the `route` target, where simple and factual
collapse to the same `vector` decision.

### LLM `classify_complexity` (ministral-3b) on `route`

| | macro-F1 | accuracy | input tok/query | latency mean | latency p95 |
|---|---|---|---|---|---|
| LLM ministral-3b | **0.5946** | 0.7630 | ~191 | 1091 ms | 1261 ms |

Per-class (`route`): hybrid P0.76 R0.979 F1 0.856 · **vector P0.80 R0.211 F1
0.333**. The LLM has a strong **hybrid bias** — it labels almost everything
COMPLEX/GLOBAL and recovers only 21 % of the vector-eligible (short factual)
queries. Total input cost for one pass over the eval set: **25 774 tokens**.

### Head-to-head on the shipped routing decision

| classifier | route macro-F1 | tokens/query | latency/query |
|---|---|---|---|
| **lightweight TF-IDF+SVM** | **0.8313** | **0** | **0.16 ms** |
| LLM ministral-3b | 0.5946 | ~191 | ~1091 ms |
| **Δ (light − LLM)** | **+0.2367** | −191 | ~−1091 ms |

## Verdict

**R1 verify met and exceeded.** The plan asked for "F1 не хуже + экономия
per-query". The lightweight classifier is *strictly better* on both axes: it
beats the LLM router by **+0.237 macro-F1** on the decision that ships *and*
replaces a ~191-token / ~1.1 s LLM call with a **0-token / 0.16 ms** local
predict. There is no quality/cost trade-off here — the cheap classifier wins
outright.

## Important caveat (do not over-claim the cost saving)

`model_routing_enabled` defaults to **false** and `retrieval_strategy` to
**hybrid** (measured 2026-06-14). In that default config the
`classify_complexity` node short-circuits to `complexity="unknown"` *without
calling the LLM at all*, and the router always returns `hybrid` (the D2
baseline). So **there is no per-query LLM classify cost in the current
production default** — the ~191 tokens/query saving is *potential*, realised
only if/when model routing is enabled. R1's real value: it removes the main
reason routing is off (the per-query LLM tax), making routing essentially free
to enable.

## Recommendation / next (gated)

- **R1 = done.** Cheap classifier validated: more accurate than the LLM router,
  zero marginal cost. Keep the harness + JSON as the reproducible record.
- **R2 (wiring) stays GATED.** Whether to actually enable routing and insert the
  classifier before `_select_retrieval_strategy` must still pass **Phase-5**:
  - headroom is small (D2 is already FULL 96/100 on retrieval), so a routing
    change can only *lose* on quality unless it demonstrably helps;
  - mis-routing is a silent regression — needs the offline D2-vs-D2+router delta
    (recall on `needs_factcard` not down, others not down, p95 latency in band,
    tokens/query ≤ baseline) before ship, exactly like arms E/F NO-SHIP;
  - the binary route gold here is *derived* from human `query_class`, not from a
    measured retrieval win — R2 must validate against actual retrieval outcomes.
- **NO-SHIP is an acceptable outcome** (as for arms E/F). R1 only establishes the
  classifier is cheap and faithful to the human routing intent; it does **not**
  prove enabling routing improves end-to-end quality. That is Phase-5's job.

## Reproduce

```bash
# offline only (free, deterministic):
python evaluation/adaptive_retrieval/train_router_classifier.py

# with live LLM comparison (ministral-3b); set MISTRAL_API_KEY in env first:
MISTRAL_API_KEY=... LLM_PROVIDER_PROFILE=external-mistral MODEL_ROUTING_ENABLED=true \
  python evaluation/adaptive_retrieval/train_router_classifier.py --llm
```
