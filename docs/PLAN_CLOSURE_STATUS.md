# Plan closure status — honest residual matrix

**Date:** 2026-08-13 (Update-198 Windows INDEX-DIM preflight ready; activation open)
**Plan file:** [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)  
**Routing:** top block of [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-198**)
**Session capsule:** [`SESSION_HANDOFF.md`](SESSION_HANDOFF.md), especially the
authoritative open-problem ledger in §1C.

> Actual Git note: the active plan file was observed **untracked** before
> Update-191. Preserve it as DoD input, but use Actual Git + the committed
> handoff for next-session routing; do not casually stage or bulk-check its
> historical checkboxes.

**Update-198:** no plan checkbox or release gate changed. A new read-only
Windows activation preflight verifies the exact staged source/evidence hash,
candidate `3 × 1024` shape, rollback target, known-query document, source and
target tree fingerprints, path separation, and snapshot headroom. The real
preflight returned `ready=true` / `mutation_performed=false`; **10 tests**, Ruff,
scoped MyPy, and diff checks passed. Working Windows Chroma retained SHA
`5c9eff00707d725a06c1a4f442833e675525d888d4d200f85049d9a77963842e`;
no snapshot, import, activation, provider call, manifest change, deletion,
migration, deploy, or push occurred.

**Update-197:** no release gate changed. The offline curated corpus now has
**76 unique cases** and every required slice has depth at least **4**
(`multi_turn=5`). The updated guard demonstrated the expected red state at the
old floor/data, then Grok and independent Codex gates each passed **20 tests**;
scoped Ruff, diff, manifest equality, unique-ID, and slice-count checks are
clean. This remains synthetic local evidence, not human-labelled, live-provider,
independent-judge, §5 quality ×3, or release evidence.

**Update-196:** documentation-only reconciliation. The authoritative handoff
now records Windows baseline `46b51b2`, Mac build checkout `7ed9cd3`, absolute
artifact paths, the verified SHA-256, and the explicit distinction between a
completed isolated artifact and an unperformed working-runtime activation. No
plan status, checkbox, implementation, test result, or runtime state changed.

**Update-195:** no plan checkbox or release gate changed. An isolated Mac copy
of the Windows 6×3 Chroma baseline produced a versioned 3×1024 candidate and
passed publish → rollback → reactivate, persisted-state inspection, the known
E20 query, and **73 focused tests**. The primary Mac 5589×1024 corpus and the
working Windows index were not mutated. The artifact is ready for a separately
scoped import/activation with a target snapshot, smoke, and rollback; this is
not production or live-quality evidence.

**Rules:**

1. Checkboxes in the plan file stay open until **behavioral DoD + evidence**.  
2. Local code slice ≠ full plan section complete ≠ production release.  
3. Actual Git wins over any SHA embedded here.  
4. Quality > speed; one named atomic slice per user turn.

**Update-191:** no plan checkbox or release gate changed. `d4583cc` expresses
the real shared agentic terminal payload as inherited `TypedDict` contracts:
quality/grounding keys are required, while KB-measure and judge-observability
keys are optional where runtime legitimately omits them. `GraphState` declares
the already-emitted `relevance_source` and `agentic_measure` keys; no eight-site
suppressions were added and runtime behavior is unchanged. Exact MyPy command
1 moved from **8 errors to Success across 72 sources**, and exact command 2 is
freshly **Success across 31 sources**. Codex passed 32 focused agentic tests
plus Ruff/diff/LF/protected-hash checks. Grok's first run used actual
`grok-4.5-build` but cancelled before reads; its follow-up wrote the scoped
diff but was budget-stopped with empty logs, so follow-up model/tests are not
claimed. VER-01 is **LOCAL TYPE-GREEN**, not Ubuntu/full-lock CI-green.

**Update-190:** no plan checkbox or release gate changed. `acc76ee` widens the
read-only `status_for_claims` collection contract from invariant `list` to
covariant `Sequence`; the function body and all runtime behavior are
unchanged. Exact MyPy command 1 moved from **9 to 8 errors** in
`agent/graph.py` across 72 sources, and all remaining findings are the agentic
TypedDict-expansion family. Grok (`grok-4.5-build`) passed 26 focused tests;
Codex passed 3 representative caller tests plus scoped
Ruff/diff/LF/protected-hash checks. No provider, migration, deploy, push,
index, database, dependency, or workflow state changed.

**Update-189:** no plan checkbox or release gate changed. `25455f5` narrows
both `finalize_grade_state` returns locally to `GraphState`, which is necessary
because their `new_state` assignments share one function scope, and removes
three adjacent obsolete ignores. Runtime expressions and behavior are
unchanged. Exact MyPy command 1 moved from **10 to 9 errors** in
`agent/graph.py` across 72 sources; one claims-list invariance and eight
agentic TypedDict-expansion findings remain. The successful Grok follow-up
(`grok-4.5-build`) passed 11 focused tests; Codex passed 3 representative tests
plus scoped Ruff/diff/LF/protected-hash checks. No provider, migration, deploy,
push, index, database, dependency, or workflow state changed.

**Update-188:** no plan checkbox or release gate changed. `02df975` replaces
the imprecise heterogeneous return annotation of `_escalate_to_inbox` with a
fixed-key private `TypedDict` and reads its required `delivery_state` key
directly. Both runtime branches already guarantee that key, so behavior is
unchanged. Exact MyPy command 1 moved from **11 to 10 errors** in
`agent/graph.py` across the same 72 sources; the aggregate remains red. Grok
(`grok-4.5-build`) and Codex each observed the delta and **6 focused tests
passed**; scoped Ruff/diff/LF/protected-hash checks are clean. No provider,
migration, deploy, push, index, database, dependency, or workflow state
changed.

**Update-187:** no plan checkbox or release gate changed. `370a429` closes
only the three strict `api/app.py` findings: the cache helper return is typed
locally across `--follow-imports=skip`, the optional widget callable is checked
explicitly against `None`, and the stale `_receive` ignore is removed. Exact
MyPy command 2 moved from **3 errors in 1 file** to **Success across 31
sources**. Codex passed three independent key runtime tests plus scoped
Ruff/diff/LF/protected-hash checks. The local Grok writer produced the scoped
diff but was budget-cancelled before final JSON; its actual model, self-review,
and test count are not claimed. Command 1 still has the prior **11
`agent/graph.py` errors / 72 sources**; Linux/full-lock CI remains unproved.
No provider, migration, deploy, push, index, database, dependency, or workflow
state changed.

**Update-186:** no plan checkbox or release gate changed. `fbebe5e` removes
only the two repeated legacy annotations in `api/routers/conversation.py`;
runtime initial values and streaming behavior remain unchanged. Exact MyPy
command 2 moved from **5 errors in 2 files** to **3 errors solely in
`api/app.py`**; it remains red. Grok passed 19 focused streaming tests, Codex
passed 11 independent key tests, and scoped Ruff/diff/LF checks are clean. The
remaining three API findings and all 11 `agent/graph.py` findings remain open
as separate slices. No provider, migration, deploy, push, index, database,
dependency, or workflow state changed.

**Update-185:** no plan checkbox or release gate changed. The retained
54-package hashed lock installed successfully into a fresh Windows CPython
3.11.13 venv and both unchanged CI MyPy command lines completed under MyPy
1.19.1. Command 1 reported **11 errors in `agent/graph.py` / 72 sources**;
command 2 reported **5 errors in `api/routers/conversation.py` and
`api/app.py` / 31 sources**. Codex reproduced both exact sets. Independent
Grok source/history QA classified the outcome `TYPE-DEBT-CONFIRMED`; focused
Codex checks confirmed the API gate-coupling and stale suppression. VER-01 is
therefore **LOCAL-DIAGNOSTIC-CLOSED / TYPE-GATE RED**, not environment-blocked
and not CI-green. Exact Ubuntu/full-lock equivalence remains unproved. No
tracked source, test, manifest, workflow, provider, migration, deploy, push,
index, or database state changed.

**Update-184:** no plan checkbox or release gate changed. Grok compiled the
new hashed VER-01 v2 lock successfully: **54 packages**, zero
Torch/Triton/NVIDIA entries. Independent parsing found all **54/54** versions
identical to `requirements-dev.lock` and confirmed the exact toolchain pins
`mypy 1.19.1`, `librt 0.9.0`, `mypy-extensions 1.1.0`, `pathspec 1.1.1`, and
`typing-extensions 4.15.0`. The retained input/lock hashes are indexed in the
session handoff. Grok executor/self-review and a separate read-only audit both
stopped at denied multiline `python -c` inspection commands. No venv was
created; install and both exact CI MyPy commands did not run. VER-01 therefore
remains **OPEN / EXECUTION-BLOCKED**, not type-green or CI-green. No tracked
source, test, manifest, provider, migration, deploy, push, index, or database
state changed.

**Update-183:** no plan checkbox or release gate changed. Root-cause evidence
now separates the type-check contract from runtime installation: the shared
dev lock has 222 packages, including 17 `torch`/Triton/NVIDIA GPU entries.
A MyPy-only venv was fast but produced non-authoritative errors because typed
runtime packages were absent. A constrained `--no-deps` direct lock installed
50 packages with zero GPU entries, but MyPy could not start without its own
toolchain dependencies. The single correction failed before installation
because it requested `typing-extensions 4.16.0` while the checked-in lock pins
`4.15.0`. VER-01 remains **OPEN / ENV-BLOCKED**; no CI MyPy green claim exists.
The next distinct experiment must use the checked-in toolchain versions
`mypy 1.19.1`, `librt 0.9.0`, `mypy-extensions 1.1.0`, `pathspec 1.1.1`, and
`typing-extensions 4.15.0`, run both exact CI commands, and only then consider
a repository lock/workflow contract. No tracked source, manifest, provider,
migration, deploy, push, index, or database state changed.

**Update-182:** no plan checkbox or release gate changed. A fresh WSL2
Ubuntu 22.04 / Python 3.11.15 venv resolved all **222** exact hashed packages,
but its only install attempt hit the explicit **480-second timeout** while
processing the large Linux GPU dependency set. Install exit was nonzero, so
both exact CI MyPy commands were correctly not run. This is the second bounded
WSL install that failed to reach runnable MyPy; raw local retry is now
exhausted. VER-01 remains **OPEN / ENV-BLOCKED**. A distinct fresh Linux CI
route requires remote/push authority, and changing the lock architecture is a
separate task. No product code, provider, migration, deploy, push, index, or
database mutation occurred.

**Update-181:** no plan checkbox or release gate changed. VER-01 remains
**OPEN / ENV-BLOCKED**. Windows Python 3.11 cannot install the Linux-target
hashed lock because `nvidia-cufile` has no Windows wheel. WSL2 Ubuntu 22.04
x86_64 with Python 3.11.15 accepted the exact lock, but the isolated install
was still running after 5m34s and had not produced runnable MyPy before its PID
was terminated. No MyPy/test gate ran. The retained Linux paths are
`/tmp/rag-ver01-py311-20260812c` and
`/tmp/rag-ver01-uv-cache-20260812c`; a later verification turn may resume them
with a sufficient bounded window or use fresh Linux CI. This is setup evidence,
not locked-CI evidence. No code, provider, migration, deploy, push, index, or
database mutation occurred.

**Update-180:** no plan checkbox or release gate changed. `e400d88` closes the
repository/CI Starlette TestClient dependency contract by pinning `httpx2
2.10.0` in the dev input and hashed lock. Its strict-warning isolated band
passed 33 tests; the new-stack audit found no known vulnerabilities, while the
full 222-package dev-lock audit timed out and remains unclaimed. The current
global Python is not lock-synchronized and still emits the warning. No
provider call, migration, runtime mutation, push, or deploy occurred.

**Update-179:** offline classification of the retained post-QG seed-42 report
found 12 timestamp-only and 6 prompt-echo candidate answers; the other two were
failed-escalation fallbacks. `63aa5df` rejects the evidenced browser artifacts,
and `dbd2b28` routes the resulting generation-provider outage human/not_verified
without automatic ticket registration. The authoritative live verdict remains
**FAIL** (candidate 25% versus baseline 90%, 13 regressions, 0 new passes), and
`gracekelly-mixed` declares no fallback. Seeds 43–44 and passing ×3 evidence do
not exist. No new provider call, index/database mutation, migration, deploy,
push, or scheduler change occurred.

---

## Closure truth (executive)

| Plan § | Local implementation | Full section DoD | Blocks release |
|--------|----------------------|------------------|----------------|
| **1** live multi-tenant / backup / RPO | partial chart/docs only | **OPEN** (opt-in live) | **yes** Gate A |
| **2** index lifecycle | **2.1–2.6g local residual closed + isolated 3×1024 artifact verified + Windows activation preflight ready** | **OPEN** snapshot/import/working-runtime activation and live PG/Redis/Celery/Chroma | yes for live index ops |
| **3** execution / session / budget | **3.1a–3.1i local** | **OPEN** multi-replica durable version | partial |
| **4** unified pipeline + escalation | **4.1–4.8 local** | **OPEN** parity default still off (product) | partial |
| **5** grounding fail-closed | **5.1–5.7 + QG-01/QG-02/QG-03A/QG-03B/QG-04 + GraceKelly artifact containment + HYBRID-MEM env local** | **OPEN** post-QG seed 42 has valid complete evidence but **FAILS** at 25% candidate vs 90% baseline; passing ×3 remains open | **yes** quality |
| **6** judge / safety / agentic parity | **6.1–6.7 local** | OPEN (production human dual-annotator sample) | **yes** |
| **7** eval gate fail-closed | **7.1–7.8 local + one-case direct-provider live PASS** | OPEN (scheduled breadth + independent judge) | **yes** |
| **8** widget / edge security | **8.1–8.5 local** | OPEN (live IdP; prod allowlist ops) | yes |
| **9** cache / architecture / SLO | **9.1a–9.1c + 9.2a–9.2f + 9.3a–9.5d3 owner slices local** | OPEN (SLA-gated sessions, live alert delivery) | soft |
| **10** final verification / canary | Python 3.13 CI-shaped unit+coverage local-green: **1851 passed / 4 skipped**, **77.04%** ≥ 72%; VER-01 retained Windows Python 3.11 MyPy command 1 **72/72 green** and command 2 **31/31 green** | **OPEN** exact Ubuntu/full 222-package-lock equivalence, integration/live services, migrations, image/Helm, canary and rollback | **yes** |

**Project / production release: NOT claimed.**

Not claimable until §1 live evidence + §5 live quality metrics + §6–8 residual + §10.

---

## Off-plan provider capability (no closure credit)

`faaa815` adds the explicit `opencode-zen-free` trial profile, fixed to
`nemotron-3-ultra-free` with no declared fallback. Local startup/key,
OpenAI-compatible endpoint, live-gate/workflow, Helm Secret, documentation,
and regression contracts are verified.

This changes **none** of the §1–§10 rows above: no Zen or other live provider
call ran, no quality evidence was collected, and no production claim is made.
The provider documents the free endpoint as temporary/logged trial service;
use only non-sensitive test data and recheck external terms before enabling it.

---

## Current live-quality incident (Update-179 evidence; unchanged in Update-180)

The post-QG native vector-only run produced valid complete child evidence for
seed 42 but failed the quality gate: candidate pass 25% (baseline 90%, required
≥85%), 13 regressions, 0 new passes, context precision 0.3012, context recall
0.725, FULL 0.70, MISS 5, faithfulness 0.7101, and answer relevancy 0.30.
Two GraceKelly browser tasks hit the same `Locator.click` 5-second timeout.
Offline classification found browser-shaped output in 18/20 candidate answers:
12 timestamp-only values and 6 prompt echoes; the remaining two were failed-
escalation fallbacks. `63aa5df` and `dbd2b28` contain these shapes locally but
do not recover quality. Seeds 43–44 did not run, so no valid three-run aggregate
or release evidence exists.

| Incident slice | Local status | Live status |
|----------------|--------------|-------------|
| **QG-01** `warranty-receipt-storage` | fixed at `c3ae4f4` | replayed and regressed; candidate exposed prompt text plus a timestamp |
| **QG-02** `error-e20-hose-kink` | fixed at `1304ff4` (routing-test baseline `c157796`) | replayed and regressed; candidate returned a timestamp |
| **QG-03A** `error-e20-filter-or-pump` verifier outage | fixed at `80c2603`; retained trace proved `verify_facts` transport failure and answer overwrite | replayed and regressed; candidate returned a timestamp |
| **QG-03B** same case content path | fixed at `5662ea7`; relevant contextual-header shells now resolve to content-bearing chunks from the same logical source | live replay did not recover the E20 answer |
| **QG-04** `error-e30` | shared cause fixed at `5662ea7`; exact retained five-document replay guarded at `5f8bb78` | replayed and regressed; candidate returned a timestamp |
| **QG-LIVE artifact containment** | `63aa5df` rejects timestamp-only/prompt-echo answers; `dbd2b28` sends expected generation-provider outages human/not_verified through response safety | not live-replayed; `gracekelly-mixed` has no fallback and the authoritative seed-42 verdict remains FAIL |

The active collection remains dimension 3 while the remote embedding lane is
dimension 1024. The successful diagnostic run used a retained six-document
compatible copy and vector-only retrieval. It does not prove default hybrid
quality. `3c90368` provides an explicit `--disable-child-reranker` path;
focused tests and a real lightweight Windows child prove that the child
receives the key as present and blank. Update-175 enabled the unchanged 1 GiB
watchdog; one bounded default-hybrid smoke was killed at **4044.1 MiB private /
801.4 MiB working set** during reranker loading. OPS-01 is enforced, while
default hybrid remains memory-blocked and has no quality evidence.

Detailed defect, environment, release, workspace, and external-boundary facts
are maintained in [`SESSION_HANDOFF.md`](SESSION_HANDOFF.md) §1C. Do not
duplicate or reinterpret them as closed plan checkboxes.

---

## Quality-first closure order (standing decision)

User priority: **quality over speed**, close plan thoroughly and honestly.

| Order | Work | Status |
|-------|------|--------|
| 1–13 | §5.1–5.3, §6.1–6.3, §7.1–7.2, §8.1–8.5 | **done** (see ledgers) |
| 14 | §7.3 merge-base baseline artifact | **done** `0d34be2` |
| 15 | DEP-01 docs-site npm audit | **done** `f622d58` |
| 16 | §7.4 curated dataset slices | **done** `8f4269f` |
| 17 | §7.5 CI baseline-artifact wire | **done** `4eceed3` |
| 18 | §6.4 routing calibration artifact | **done** `a7cefc3` |
| 19 | §6.5 measured agentic KB gate | **done** `431893c` |
| 20 | §7.6 live provider gate scaffold | **done** `d1ae4d6` |
| 21 | §7.7 deeper curated corpus (≥3/slice) | **done** `47e255a` |
| 21a | §7.8 required-slice depth ≥4 | **done** (resolve Update-197 through Actual Git) |
| 22 | §6.6 agentic LLM evaluate wire | **done** `69c6fdf` |
| 23 | §6.7 human calibration readiness + CLI | **done** `c707c46` |
| 24 | §4.6 outbox retry schedule | **done** `11acfec` |
| 25 | §4.7 graph node status SSE | **done** `6b91a35` |
| 26 | §4.8 provider token stream through generate | **done** `fc7f07b` |
| 27 | §5.4 independent retrieval relevance | **done** `4f95e18` |
| 28 | §5.5 live quality metrics gate scaffold | **done** `a901692` |
| 29 | §5.6 exact live child report → DoD wire | **done** `fb72dd2` |
| 30 | §5.7 producer emits all 7 canonical metrics | **done** `13bf255` |
| 31 | QG-01 vector parent expansion | **done local** `c3ae4f4`; post-QG live replay still failed |
| 32 | QG-02 generation failure routing | **done local** `1304ff4`; post-QG live replay still failed |
| 33 | QG-03A verifier-outage routing | **done local** `80c2603`; post-QG live replay still failed |
| 34 | QG-03B contextual-header grading | **done local** `5662ea7`; post-QG live replay still failed |
| 35 | QG-04 retained E30 replay | **done local** `5f8bb78`; post-QG live replay still failed |
| 36 | HYBRID-MEM child environment propagation | **done local** `3c90368`; watchdog enforced in Update-175; default hybrid memory-blocked above 1 GiB |
| 37 | §9.1a bounded Redis fallback | **done local** `db65e37`; no live Redis |
| 38 | §9.1b Redis reconnect backoff | **done local** `eb8466e`; no live Redis |
| 39 | human sample / opt-in live ×3 evidence | **external/data authority required** |
| 40 | §2/§3 residual if product needs | residual |
| 41 | Astro 7 (clears DEP-01 moderate residual) | **done local** `cea370b`; zero audit findings / zero exceptions |
| 42 | §1 + §10 | **opt-in live only** |

Do **not** fake-close §1 or §10 with mock-only evidence.

---

## §2 map (honest — live DoD open)

| Bullet | Local | Residual |
|--------|-------|----------|
| inventory / retention / operator / lifecycle | through 2.5b + related | live DoD |
| fault injection | **2.6a–2.6g** | local residual closed |
| live PG/Redis/Celery/Chroma + migrations | not started | **opt-in**; migrations **019–023** on disk |

**Do not re-select 2.x.** Last §2 fault-injection impl: `f347feb` (**2.6g**).

---

## §3 map + ledger

| Slice | SHA |
|-------|-----|
| 3.1a | `a21f364` |
| 3.1b | `76179d5` |
| 3.1c | `d9ba87e` |
| 3.1d | `48c2381` |
| 3.1e | `b98b917` |
| 3.1f | `2581855` |
| 3.1g | `ae13000` |
| 3.1h | `ab7b417` |
| 3.1i | `fe2f0aa` |

**Residual:** multi-replica durable session version.

---

## §4 map + ledger

| Slice | SHA | What |
|-------|-----|------|
| 4.1 | `eaf41f3` | single terminal/history when parity succeeds |
| 4.2 | `f1c846e` | graph-only generation when parity on |
| 4.3 | `ad5e435` | durable idempotent escalation |
| 4.4 | `0371971` | auto human-route on normal ask |
| 4.5 | `6453530` | outbox retry without second ticket |
| **4.6** | `11acfec` | Celery beat + CLI outbox schedule |
| **4.7** | `6b91a35` | real LangGraph node status SSE |
| **4.8** | **`fc7f07b`** | provider token stream through generate |

**Residual after 4.8:**

| Item | Status |
|------|--------|
| Graph **node** SSE on parity path | **done local** (4.7) |
| Answer **token** stream from provider generate | **done local** (4.8; when stream capable) |
| Fallback UX chunks when stream N/A | **done local** (`graph_answer_chunks`) |
| `STREAMING_RAG_PARITY` default | **off** (product decision to flip) |
| Outbox schedule (beat/CLI) | **done local** (4.6) |

---

## §5 map + ledger

| Slice | Status | SHA |
|-------|--------|-----|
| **5.1** | **done** | `7c53bdb` |
| **5.2** | **done** | `50bb220` |
| **5.3** | **done** | `1cdecb2` |
| **5.4** | **done** | `4f95e18` independent retrieval relevance |
| **5.5** | **done local** | `a901692` live quality metrics gate scaffold |
| **5.6** | **done local** | `fb72dd2` exact child report parse + release-honest DoD wire |
| **5.7** | **done local** | `13bf255` canonical metric producer + completeness provenance |
| Live DoD evidence | **open / failing** | post-QG valid seed-42 run fails at 25% candidate vs 90% baseline; seeds 43–44 and passing ×3 remain opt-in |

**Residual after 5.7:** the producer emits all seven canonical metrics with
candidate-only provenance and fails real release runs closed on incomplete
measurement. A later authorized vector-only seed-42 run produced valid child
evidence but failed the thresholds recorded above; QG-01, QG-02, QG-03A,
QG-03B, and QG-04 are local-only repairs. Actual passing
precision/recall/faithfulness ×3 evidence remains explicit opt-in. Relevance is
**not** quality/100, and §5 metrics are not substituted from legacy
scores/counts.

---

## §6 map + ledger

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **6.1** | **done local** | `b3494a0` | unmeasured agentic; never auto on fixed scores |
| **6.2** | **done local** | `d0317e9` | PII redact + injection refuse→human |
| **6.3** | **done local** | `d6e3a55` | independent judge; fail-closed on outage/parse |
| **6.4** | **done local** | `a7cefc3` | routing calibration artifact + threshold resolve |
| **6.5** | **done local** | `431893c` | measured grounding when agentic has KB docs |
| **6.6** | **done local** | `69c6fdf` | LLM evaluate wire on KB agentic terminals |
| **6.7** | **done local** | `c707c46` | human readiness gate + recalibrate CLI |
| 6.x | residual | — | production dual-annotator sample + reissue |

**6.4 residual:** seed is bootstrap-defaults (historical 80/80/0.8/70), not live  
human production labelling DoD.

**6.7 residual:** readiness gate is ready; **real human labels not collected**.  
Seed `labelled_routes.jsonl` is `label_source=synthetic` and correctly fails  
`--require-human`.

---

## §7 map + ledger

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **7.1** | **done local** | `94ac64e` | infra/skip/empty effective → FAIL |
| **7.2** | **done local** | `25788ee` | mock = SMOKE only; release needs evidence |
| **7.3** | **done local** | `0d34be2` | merge-base baseline artifact load/write/require |
| **7.4** | **done local** | `8f4269f` | 10 required slices + min_context_recall; 47 cases |
| **7.5** | **done local** | `4eceed3` | CI write + upload + require-wire baseline artifact |
| **7.6** | **done local** | `d1ae4d6` | scheduled live provider gate scaffold (opt-in) |
| **7.7** | **done local** | `47e255a` | min 3 cases per required slice; 67 cases |
| **7.8** | **done local** | resolve through Actual Git | min 4 cases per required slice; 76 unique cases |
| 7.x | residual | — | live execute with secrets; optional further depth |

**7.2 residual:** CI still runs `--mock-experiment-runtime` as **smoke** (documented non-evidence).  
**7.6 residual:** one authorized direct-provider case now has valid complete child evidence and release PASS; scheduled breadth and independent-judge evidence remain open.
**7.8 residual:** still synthetic curated (not production human labels); optional deeper still.

### Dataset depth (7.8)

| Slice | Count |
|-------|------:|
| multi_tenant | 4 |
| multi_turn | 5 |
| claim_citation | 4 |
| no_answer | 4 |
| tools | 4 |
| streaming | 4 |
| adversarial | 4 |
| pii | 4 |
| durable_escalation | 4 |
| context_recall | 4 |
| **total** | **76** |

---

## §8 map + ledger

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **8.1** | **done local** | `0bee13e` | bootstrap JWT, allowlist, frame-ancestors, session/token JS |
| **8.2** | **done local** | `756562e` | ASGI received-byte limits; upload stream + exclusive/atomic place |
| **8.3** | **done local** | `13a9a5b` | email_verified; (issuer, subject); no rebind; shared tenant map |
| **8.4** | **done local** | `68a30b2` | placeholders rejected; ALLOW_DEV_ADMIN_LOGIN banned in production |
| **8.5** | **done local** | `4d6be52` | Playwright cross-origin E2E; iframe Origin=API allowed; fail-closed empty/disallowed |

**8 residual:** live IdP; production must set `WIDGET_ALLOWED_ORIGINS`; Chromium-only E2E.

---

## DEP-01 (docs-site supply chain)

| Item | Status | SHA |
|------|--------|-----|
| Lock refresh + high=0 | **done local** | `f622d58` |
| Dated exceptions + `audit:deps` | **done local** | `f622d58` |
| Astro 7 major + zero-audit lock | **done local** | `cea370b` |

**Exceptions:** none after the 2026-08-11 Astro 7 lock refresh.

---

## §9 map + ledger

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **9.1a** | **done local** | `db65e37` | process-local Redis fallback honors TTL, is lock-protected, and evicts LRU entries above 1024; partial Redis deletes remain counted on `SCAN` failure |
| **9.1b** | **done local** | `eb8466e` | connection/ping and cache-operation failures invalidate the client; serialized reconnect delays grow from 1 second to a 30-second cap and reset after recovery |
| **9.1c** | **done local** | `893efe3` | response-cache keys bind tenant, active Chroma collection/generation, effective prompts, configured provider-model routing, and normalized query; unresolved identity skips cache read/write |
| **9.2a** | **done local** | `3fe6d6d` | a bounded `operation=publish|retention|unknown` counter records publish and automatic/manual retention failures once; a warning alert groups increases by operation |
| **9.2b** | **done local** | `11e52f1` | each client-visible `route=auto` sync/SSE result increments bounded `verification=verified|unverified`; missing/unexpected grounding is unverified and the alert target is zero |
| **9.2c** | **done local** | `64f40b3` | each real shared inbox delivery attempt increments bounded `outcome=delivered|failed|unknown` exactly once across initial and retry paths; non-attempts remain uncounted and failures have a warning alert |
| **9.2d** | **done local** | `9817e89` | each applied unsafe pre-response increments bounded `action=redact|refuse|unknown` once; clean/empty answers remain uncounted, metric failure is fail-open, and refusals have a warning alert |
| **9.2e** | **done local** | `5a2f696` | label-free orphan-work gauge increments once when capacity transfers to any of five shared future callbacks and decrements once on completion; normal sync work stays uncounted, metric failure is fail-open, and work above zero for five minutes warns |
| **9.2f** | **done local** | `344e174` | ten confirmed session/ticket/KB-draft ownership mismatches increment bounded `resource=session|ticket|kb_draft|unknown` once; missing/same-tenant access stays uncounted, metric failure is fail-open, opaque 404s remain unchanged, and any five-minute increase warns after 30 seconds |
| **9.3a** | **done local** | `1237f3c` | a portable `DS_PROMETHEUS` dashboard gives each named signal one non-overlapping panel, preserves bounded/adaptive PromQL and zero-target semantics, and is guarded by offline JSON contract tests |
| **9.4a** | **done local** | `cea370b` | Astro 7.2 / Starlight 0.41 retain the unified Mermaid pipeline and prior whitespace behavior; dependency audit is zero with an empty validated exception register |
| **9.5a** | **done local** | `9c207b6` | TraceService is the injectable single owner of start/log/finish and pre-persistence redaction; SQLite module-level signatures remain compatible |
| **9.5b** | **done local** | `03057aa` | EscalationService owns durable ticket creation and inbox/outbox delivery lifecycle while preserving module-level compatibility |
| **9.5c1** | **done local** | `84fbdf7` | IngestionJobService owns the nine API-side durable enqueue/status operations with unchanged module-level signatures |
| **9.5c2** | **done local** | `890155a` | IngestionJobService owns worker require/claim/heartbeat/completed-CAS/failed-CAS entry points without changing lease or terminal semantics |
| **9.5d1** | **done local** | `aefcf20` | PipelineRunner owns pipeline capacity release and orphan-future completion handoff; router helpers remain compatibility seams |
| **9.5d2** | **done local** | `d865b06` | PipelineRunner owns sync `/api/ask` executor submission, shielded deadline, and timeout transfer to orphan-capacity lifecycle |
| **9.5d3** | **done local** | `c53f724` | PipelineRunner owns streaming graph/event executor submission, queue and shielded-future wait deadlines, and timeout transfer to orphan-capacity lifecycle; router retains SSE semantics and compatibility seams |

**Residual:** SessionService remains deferred pending a multi-replica
SLA/consistency decision. No ungated local architecture owner is preselected,
and no live Redis, Grafana import, metric-scrape, or alert-delivery evidence
exists.

---

## What “plan closed” means

The plan is **closed** only when:

1. Every section §1–§10 meets its own **behavioral DoD + evidence**.  
2. Unverified auto-rate is zero under live policy.  
3. Restore/rollback/canary confirmed where required.  
4. Production release does **not** rest on graceful skip, fixed agentic scores,  
   mock release PASS, or self-judge without human calibration.

Local green slices alone **do not** close the plan.

---

## Next session pick (one only)

OPS-01 is enforced and default hybrid is memory-blocked above the 1 GiB local
ceiling before retrieval/provider execution. Do not retry it locally without a
narrowed design expected below that limit. The isolated INDEX-DIM artifact is
verified; importing or activating it in a working runtime is a separate
target-specific mutation requiring a recoverable snapshot, smoke, and
rollback. VER-03 and QG-01–QG-04 remain locally green, while the post-QG
seed-42 live replay still failed. No ungated local implementation is
preselected. A next provider step needs separate authority for
`D:\GraceKelly`, or an explicit routing/cost decision before adding any
fallback. Do not spend another paid seed without a fresh exact opt-in.

Gated alternatives remain: further live provider breadth/independent judge,
quality ×3 (`--execute` + secrets + fresh opt-in), a real dual-annotator human
sample, or the product decision to default `STREAMING_RAG_PARITY=true`. The
default hybrid path requires a sub-1-GiB design change before local replay.

This list is not authorization. The executable boundary and current facts are
spelled out in [`SESSION_HANDOFF.md`](SESSION_HANDOFF.md) §2A. In a new
direct-autonomy turn, select at most one local slice; otherwise stop after
reconciliation. Do not convert this routing note into authority for a live
retry, scheduler change, index mutation, migration, push, or deploy.

`3a37fd2` separately closes the local VER-02 `vectordb` type debt under
`--follow-imports=skip`. It changes no plan checkbox and does not establish a
full repository, locked Python-3.11, CI, or production verification result.

**Do not re-select** 2.x–3.x, **4.1–4.8**, **5.1–5.7**, 6.1–6.7, 7.1–7.8, 8.1–8.5, **9.1a–9.1c**, **9.2a–9.2f**, **9.3a–9.5d3 completed slices**, VER-06, or VER-07 without a changed boundary.

---

## Last-known verification snapshot (Update-180)

| Band | Last known |
|------|------------|
| **VER-04 Starlette TestClient backend** | `e400d88`: repository dependency contract **1 failed → green**; isolated strict-warning TestClient band **33 passed** and request returned 200 through `httpx2 2.10.0`; scoped Ruff/diff clean; narrowed new-stack audit found no known vulnerabilities. Current global Python is not lock-synchronized and still warns; full 222-package dev-lock audit timed out after 124 seconds and is not claimed green. |
| **GraceKelly artifact guard** | `63aa5df`: focused TDD **3 failed → 17 passed**; independent provider/failover band **28 passed**; scoped Ruff/MyPy/diff clean; no live call |
| **Generation-provider fail-closed** | `dbd2b28`: focused TDD **1 failed → 1 passed**; missing conditional edge separately reproduced red then corrected once; final provider-graph/error/verifier/safety band **31 passed**; scoped Ruff/narrowed MyPy/diff clean; no live call |
| **7.6 bounded live provider** | run `20260812T084811Z-b195b7a9`: direct Mistral, seed 43, one case; **1/1 effective**, zero infrastructure failures, complete Section 5 metrics, authoritative child evidence/release PASS; both sides refusal rate 1.0, so scheduled breadth, independent judge, quality ×3, and whole-release claims remain open |
| **OPS-01 / HYBRID-MEM** | `PythonMemoryGuard` Running/Enabled; one default-hybrid smoke killed only PID 11984 at **4044.1 MiB private / 801.4 MiB working set** against **1024 MiB**, during reranker loading before retrieval/provider execution; default hybrid remains memory-blocked and has no quality claim |
| **VER-03 Python 3.13 unit+coverage gate** | **LOCAL-CLOSED:** fresh CI-shaped run passes **1851 tests / 4 skipped / 187 warnings in 753.44s** at **77.04%** coverage (threshold **72%**); no locked Python 3.11, integration/live-service, migration, image/Helm, or release-green claim |
| **9.5d3 PipelineRunner streaming execution/deadline owner** | Grok TDD transcript **2 failed → 6 passed**, first focused band **32 passed**; QA follow-up added event-worker and exception-fallback ownership; Codex independent owner/provider-token stream band **7 passed**; Ruff/format/scoped MyPy/diff/LF/protected hashes green |
| **9.5d2 PipelineRunner sync execution/deadline owner** | ownership **2 failed / 2 passed → 4 passed**; owner/concurrency/request-timeout/stream-capacity/chat-streaming band **22 passed**; Ruff/format/scoped MyPy/diff/LF/protected hashes green |
| **9.5d1 PipelineRunner capacity lifecycle owner** | ownership **2 failed → 2 passed**; pipeline concurrency/stream-capacity/request-timeout/chat-streaming band **20 passed**; Ruff/narrowed MyPy/format/diff/LF/protected hashes green |
| **9.5c2 IngestionJobService worker owner** | ownership **1 failed → 1 passed**; job-contract/liveness/worker/outage/duplicate-claim band **111 passed**; static/signature/boundary gates green |
| **9.5c1 IngestionJobService API owner** | ownership **1 failed → 1 passed**; job-contract/upload-idempotency band **73 passed**; scoped static/boundary gates green |
| **9.5b EscalationService lifecycle owner** | ownership **1 failed → 1 passed**; focused escalation band **32 passed**; scoped static/boundary gates green |
| **VER-07 retention audit tenant contract** | exact stale assertion **1 failed → 1 passed**; adjacent trace-retention/audit-retention/audit-tenant/tenant-enforcement band **22 passed**; Ruff lint + diff/LF + runtime-diff + protected hashes clean; whole-file formatter debt reproduces on clean `HEAD` |
| **9.5a TraceService lifecycle owner** | TDD import error → **3 passed**; adjacent **34 passed / 1 pre-existing failed**; narrowed **34 passed / 1 deselected**; final **13 passed**; scoped Ruff/format + narrowed MyPy + diff/LF + protected hashes clean |
| **9.4a Astro 7 / DEP-01** | independent pytest **5 passed**, one warning; Astro check **0/0/0**; npm audit **0 vulnerabilities**; static build **59 pages** + Pagefind + sitemap; scoped diff/LF + protected hashes clean |
| **Update-156 transparency** | docs-only Actual Git/Grok/artifact reconciliation; docs quality gate only; no implementation test rerun or new implementation/release evidence |
| **9.3a Grafana dashboard artifact** | Grok TDD **7 failed → 7 passed**; QA threshold semantics **1 failed / 6 passed → 7 passed**; independent **7 passed**, one warning; scoped Ruff + JSON parse + cached diff/LF + protected hashes clean; no live Grafana/import/scrape/alert-delivery evidence |
| **Update-154 transparency** | docs-only reconciliation against Actual Git; no implementation file changed, no project suite rerun, and no new implementation or release evidence |
| **9.2f tenant-denied telemetry** | focused TDD **5 failed → 5 passed**; independent tenant/session/agent/KB/metrics/alerts band first rejected a zero-duration alert, then passed **54 tests** after one narrowed correction, one warning; scoped Ruff + six-source narrowed MyPy + diff/LF clean; ordinary MyPy retains four pre-existing `api/app.py` errors outside changed lines; formatter debt remains outside added lines; no live scrape/alert delivery |
| **9.2e orphan-work telemetry** | focused TDD **5 failed → 5 passed**; independent pipeline/stream/metrics/alerts/timeout band first exposed test-isolation leakage, then passed **37 tests** after one narrowed correction, one warning; scoped Ruff + narrowed metrics MyPy + diff/LF clean; ordinary two-source MyPy retains two pre-existing `no-redef` errors outside changed lines; formatter debt remains outside added lines; no live scrape/alert delivery |
| **9.2d safety-block telemetry** | focused TDD **5 failed → 5 passed**; full response-safety/metrics/alerts/unverified-auto band **35 passed**, one warning; post-format focused gate **5 passed**; scoped Ruff + two-source MyPy + diff/LF clean; formatter debt remains outside added lines; no live scrape/alert delivery |
| **9.2c escalation-delivery telemetry** | Grok focused TDD **8 failed → 8 passed** after one narrowed test-fixture correction; independent four-file band **33 passed**, one warning; scoped Ruff + two-source MyPy + diff/LF clean; whole-file formatter debt remains outside added lines; no live scrape/alert delivery |
| **Update-149 docs reconciliation** | docs quality **13 passed**, one warning; scoped diff/LF clean; no project tests rerun and no new implementation evidence |
| **VER-06 agentic safety mock contract** | exact stale test **1 failed** → **1 passed**; independent response-safety/agentic/auto-telemetry band **44 passed**, one warning; scoped Ruff + diff/LF clean; pre-existing whole-file formatter debt remains; production code unchanged |
| **9.2b unverified auto-rate telemetry** | focused TDD **4 failed / 5 passed** → **9 passed**; independent **60 passed / 1 failed**, failure reproduced alone as pre-existing VER-06; narrowed rerun **60 passed**, 1 deselected, one warning; scoped Ruff + new-file format + narrowed two-source MyPy + diff/LF clean; no live scrape/alert delivery |
| **9.2a index lifecycle failure telemetry** | focused TDD **10 failed / 2 passed** → **12 passed**; final lifecycle/metrics/alert band **75 passed**, 61 deselected, one known warning; docs **13 passed**; scoped Ruff + narrowed two-source MyPy + diff/LF clean; pre-existing whole-file format debt remains; no live scrape/alert delivery |
| **VER-05** | stale zero-caller assertion red **1 failed** → exact admin-only caller contract; independent retention/admin band **51 passed**, 62 deselected, one known warning; scoped Ruff + diff clean; pre-existing whole-file format debt remains |
| **9.1c versioned cache namespace** | HTTP settings-source regression **2 failed** → **2 passed**; final namespace/HTTP-cache/Redis/manifest band **40 passed** with two known warnings; Ruff + changed-range format + narrowed MyPy + diff clean; no live Redis/provider/index mutation |
| **9.1b Redis reconnect backoff** | recovery red **2 failed** → green **2 passed**; focused Redis file **9 passed**; final Redis/cache band **15 passed** with two known warnings; Ruff check/format + scoped MyPy + diff clean; no live Redis |
| **9.1a bounded Redis fallback** | TTL/cap red **2 failed** → focused **2 passed**; partial-delete count red **1 failed** → green **1 passed**; final Redis/cache band **13 passed** with two known warnings; Ruff check/format + scoped MyPy + diff clean; no live Redis |
| **VER-02** | exact MyPy red **1 error** → green **1 source**; lifecycle/lock band **11 passed**; Ruff clean; package `vectordb` MyPy **10 sources** with `--follow-imports=skip`; VER-01/full locked CI remain open |
| **HYBRID-MEM env** | TDD red **1 failed** → focused **2 passed**; independent live-quality/regression band **57 passed**; Ruff + changed-file Mypy + diff clean; real lightweight Windows child saw the key present and blank; no model/hybrid/live run |
| **QG-04** | exact local replay **1 passed** and independent band **31 passed**; post-QG live seed 42 still regressed on `error-e30` |
| **QG-03B** | TDD red **1 failed** → focused green **1 passed** and independent band **24 passed**; post-QG live seed 42 did not recover the E20 candidate answer |
| **QG-03A** | Grok red 1 failed → focused **6 passed** + Ruff; independent verifier/grounding/citation/graph-error/judge/provider band **49 passed** + Ruff + diff clean; ordinary changed-file Mypy exposed 9 pre-existing `typeddict-item` errors outside changed lines, narrowed run passed; no locked/full-Mypy claim |
| **QG-02** | TDD red 1 failed → green 1 passed; final focused **1 passed**; adjacent provider graph/error/model-routing/judge **31 passed**; Ruff + changed-file Mypy (`--follow-imports=skip`) + diff clean; no full locked-Mypy claim |
| **QG-01** | TDD red 2 failed / 9 passed → focused **11 passed**; independent parent/base/reranker **34 passed**; scoped Ruff + changed-file Mypy + diff clean; broader `vectordb` Mypy last had one unchanged-file error |
| **Native live quality** | seed 42 valid child evidence but quality **FAIL**; seeds 43–44 not run; no valid ×3 aggregate |
| **OpenCode Zen** | **155 passed**; Ruff, scoped Mypy, Helm Secret render, scoped diff clean; no live call |
| **5.7** | independent regression/quality band **83 passed**; Ruff + scoped diff clean |
| **5.6** | Grok focused 25 passed; independent quality/provider/workflow **46 passed**; Ruff + scoped diff clean |
| **5.5** | 33 passed (quality-metrics + provider-gate + workflows) |
| **5.4** | 56 passed (relevance + agentic + grounding/judge) |
| **4.8** | 16 passed (provider tokens + node SSE + parity) |
| **6.7** | 19 passed; seed NOT_READY |
| **7.8** | Grok + independent Codex: 20 passed (depth 4 / 76 unique cases) |
| **DEP-01** | npm audit high=0 |

Full suite / locked CI Mypy / passing live ×3 / migrate / push / deploy:
**not** claimed.
