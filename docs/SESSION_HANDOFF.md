# Session handoff

**Обновлено:** 2026-08-07 — **Update-97** after **7.2** @ `25788ee`.

---

## 0. Routing

1. Actual Git  
2. `AGENT_STATE.md` **Update-97**  
3. This file + `PLAN_CLOSURE_STATUS.md`

---

## 1. Facts

| | |
|--|--|
| Latest impl | `25788ee` — **7.2** mock not release PASS |
| Prior | `94ac64e` 7.1; `d6e3a55` 6.3 |
| Local complete | … + **7.1–7.2** |
| Production | NOT claimed |
| Next | **8.1** widget bootstrap (default) |
| WIP | none |

**Verify 7.2:** 35 focused passed; Ruff clean.

---

## 2. Contract 7.2 @ `25788ee`

- `apply_evidence_policy(report, release_gate=…)`
- Mock modes: `SMOKE_PASS` / `SMOKE_FAIL` — **never** release `PASS`
- `gate.passed` == release eligibility (needs evidence_valid)
- `metrics_passed` separate; smoke exit uses metrics
- `--release-gate`: exit 1 without valid evidence even if smoke green
- CI: smoke only, no `--release-gate`

---

## 3. Next: 8.1

**Widget bootstrap security** (plan §8): short-lived audience-scoped token,
`WIDGET_ALLOWED_ORIGINS`, path-specific `frame-ancestors`, strict postMessage
handshake, session_id reuse.

Alternates: §7 merge-base baseline; live provider/judge scheduled gate.

---

## 4. Do not

Re-select through **7.2**. No push/live/migrate without opt-in. One slice/turn.
