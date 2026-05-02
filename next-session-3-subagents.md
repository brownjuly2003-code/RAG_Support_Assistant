# Next Session: Three-Subagent Plan

## Goal
Resolve the next non-live-service backlog safely without touching paid GraceKelly/Mistral benchmark paths unless the user explicitly opts in.

## Tasks
- [ ] Lead: confirm `git status --short`, current HEAD, and active backlog in `docs/plans/2026-05-01-backlog.md` -> Verify: no unexpected modified files before edits.
- [ ] Subagent 1: inspect streaming parity risks in `api/routers/conversation.py` and related tests -> Verify: report exact failing/gap tests before implementation.
- [ ] Subagent 2: inspect Helm secret split debt in `deploy/helm/*` and CI helm commands -> Verify: report required chart changes and dry-run commands.
- [ ] Subagent 3: inspect safe benchmark options in `scripts/regression_eval.py` and `evaluation/curated_cases.jsonl` -> Verify: propose mock/default-only run, with live API cost explicitly gated.
- [ ] Lead: choose one lane to implement after reading all three reports -> Verify: affected-file list is disjoint from other lanes.
- [ ] Lead: write failing focused test first for the chosen lane -> Verify: focused test fails for the expected reason.
- [ ] Lead: implement the smallest fix and rerun focused tests -> Verify: focused tests pass.
- [ ] Lead: run broader relevant pytest and `ruff check .` -> Verify: commands exit 0 or document the exact blocker.

## Done When
- [ ] One lane is shipped with tests and docs updated where needed.
- [ ] No live paid/API benchmark is run without explicit user opt-in.
- [ ] `git status --short` contains only intended files before commit.
