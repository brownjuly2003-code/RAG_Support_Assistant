# Non-Live Backlog Continuation - 2026-05-02

> Historical completion note. This non-live continuation is complete; the active
> backlog source is now `docs/plans/2026-05-01-backlog.md`, with live
> GraceKelly/Mistral benchmark work requiring explicit opt-in.

## Goal
Continue the remaining safe backlog without running live GraceKelly, Mistral, or paid/API benchmark paths.

## Tasks
- [x] Confirm live benchmark docs require explicit opt-in -> Verify: grep active docs for `--allow-paid-apis` and live warnings.
- [x] Check a11y/performance tooling availability -> Verify: `axe` and `lighthouse` commands are either found or documented as missing.
- [x] Run focused non-live docs/a11y tests -> Verify: pytest passes without live provider calls.
- [x] Report remaining blocked work -> Verify: final status names blockers and next commands.

## Done When
- [x] No live provider/API benchmark has run.
- [x] Active docs and tests still point future work at opt-in live runs only.
- [x] A11y/performance status is clear for the next session.
