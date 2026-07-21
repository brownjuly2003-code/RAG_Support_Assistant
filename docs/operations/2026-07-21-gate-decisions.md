# Gate decisions — 2026-07-21

Authority: user delegated all remaining project gates to the agent
(«все гейты — на твоё решение»).

Source backlog: `docs/operations/2026-07-18-plan-fable.md` items 7–8 and
carried Q1b / multi-replica / C1 from AGENT_STATE Update-5/6.

## N4 — public repo vs Pages kitchen (hybrid)

| Class | Examples | Tracked in git? | GitHub Pages? |
|-------|----------|-----------------|---------------|
| Product docs | README, QUICKSTART, DEPLOYMENT, OPERATIONS, CHANGELOG | yes | yes |
| Product audits | `docs/audits/*` | yes | yes (technical transparency) |
| Agent/process kitchen | `AGENT_STATE.md`, `docs/sessions/**`, `docs/operations/**`, `docs/plans/**`, research/fable notes | yes | **no** (`KITCHEN_DIR_PREFIXES`) |
| Secrets / credentials | never | **no** | **no** |

Rationale:

1. The real incident (2026-07-19) was **Pages indexing** of handoffs, not
   «file exists in a public git repo». Root kitchen was never synced to Pages
   (only `README.md` + `DEPRECATIONS.md`); `docs/sessions/` was the hole and
   is now kitchen-blocked.
2. `git rm --cached` does not erase history and costs continuity for agents.
3. Product audits stay public as a deliberate showcase; they were spot-checked
   for LAN IPs / secret-file paths — clean.

Operational rule for agents: new handoff, ops report, or process audit goes
under `docs/sessions/` or `docs/operations/` (kitchen). Product-facing audit
summaries may go under `docs/audits/`.

## Q1b — nightly RAGAS drift + CI quality floor

**Decision: DEFER.**

Q1 heavy A/B (2026-07-18) was **NO-SHIP on all 7 arms**. No retrieval default
changed. Wiring a nightly drift job or a CI floor against context_precision
without a shippable arm only burns tokens and flakes CI. Revisit when:

- a SHIP-criteria arm exists, or
- product owners set a new official precision baseline intentionally.

Harness remains: `scripts/ab_context_precision.py` and
`docs/operations/2026-07-18-q1-context-precision-ab-*.md`.

## Multi-replica implementation

**Decision: DEFER.**

Design is complete (`docs/plans/2026-07-18-multi-replica-design.md`). Headline
there still holds: do not start without a concrete multi-replica SLA. Two real
blockers when started later: confirm-action pending state and distributed rate
limiting.

## C1 — split `agent/graph.py`

**Decision: DEFER.**

Both recent audits forbid silent broad refactors. Split only when a concrete
feature or bug forces modularization of a boundary, not as a hygiene drive.

## L1 — silent `except` / `pass`

**Decision: opportunistic only.** No dedicated sweep. Fix when touching the
module for other reasons.

## FastAPI lock bump

**Decision: SHIP** (executed in Update-6). Mine for metric route prefixes was
already fixed version-agnostically; lock moved `0.136.1 → 0.139.2`.
