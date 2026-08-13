# INDEX-DIM Windows activation and rollback runbook

## Goal

Activate the verified Mac-built `3 × 1024` Chroma artifact against the working
Windows corpus only after exact preflight, recoverable snapshot, tenant-lock,
acceptance, rollback proof, and final reactivation. Every failed prerequisite
must stop before the next mutation boundary.

## Tasks

- [x] Add a read-only preflight contract for exact source, target, snapshot,
  evidence hash, candidate shape, tree fingerprints, and disk headroom.
- [x] Prove the contract red before implementation and green afterward.
- [x] Run the preflight only after the artifact is copied to a local staging
  directory; copying and activation remain separate authorized operations.
- [x] Attempt activation and stop before snapshot/copy when the mandatory
  PostgreSQL advisory-lock service is unavailable.
- [x] Diagnose the unchanged retry boundary: WSL VHD attachment fails with
  `Wsl/Service/CreateInstance/MountVhd/HCS/E_ACCESSDENIED`; one narrowed
  `wsl --shutdown` correction did not change the result.
- [x] Narrow the attach failure past successful system/swap VHD setup and stop
  at the admin-only Ubuntu VHD owner test; the non-elevated test changed
  nothing and returned `Access is denied`.
- [ ] Establish and verify a reachable PostgreSQL tenant-lock service.
- [ ] Create and verify the snapshot before copying, then run
  dimension/content/E20 smoke, prove snapshot restore, and reactivate.

## Current state

| Item | Current truth |
|------|---------------|
| Product implementation | `0cba9d1` (`scripts/index_activation_preflight.py`) |
| Blocker record | `bac1939` (Update-199) |
| Canonical staging | `.tmp/index-dim-windows-chroma-source-20260813`; exact fingerprint below |
| Quarantined opened copy | `.tmp/index-dim-windows-chroma-source-opened-20260813`; diagnostic only, never activate from it |
| Windows target | Unchanged legacy tree at exact fingerprint below |
| Snapshot | `.tmp/index-dim-windows-target-snapshot-before-activation` — absent |
| Manifest / retention registry | `data/vectordb/index-manifests` / `data/vectordb/index-retention` — absent |
| Lock service | PostgreSQL ports `5432`/`55432` are unavailable; Docker and Ubuntu WSL startup are blocked below PostgreSQL by VHD attach `E_ACCESSDENIED` |
| Runtime | Docker Desktop stopped; WSL attach still fails after one `wsl --shutdown`; a non-elevated owner test processed zero files; no temporary PostgreSQL service was left running |
| Ubuntu VHD owner | `BUILTIN\Administrators`; current user has no direct ACE and cannot test a current-user owner without elevation |

Opening canonical staging with `chromadb.PersistentClient` is forbidden. The
Update-199 probe proved candidate `3 × 1024`, all three sources, and E20 top-1,
but Chroma changed persistence bytes. That copy was quarantined and canonical
staging was freshly restored from the Mac artifact to its exact SHA.

## Fixed inputs

- Windows target: `D:\RAG_Support_Assistant\data\vectordb\chroma`.
- Candidate: `rag_docs-v-default-3f2b79fbe1246ab3`, count `3`, dimension
  `1024`; previous collection `rag_docs_default`.
- Evidence SHA-256:
  `c49feed5812cc44987b4478f0737d99c075f350b8ba66fb8ebba3e70df86a382`.
- Staged Chroma tree fingerprint (631 files / 56,309,636 bytes):
  `1ce875318d2d4c903a684e7d1dd6326d4dd4366b0e131c6c8418fd9e94835b96`.
- Known-query evidence must include `errors_e10_e30.md`.

## Verified read-only command

```powershell
python scripts/index_activation_preflight.py `
  --source .tmp/index-dim-windows-chroma-source-20260813 `
  --target data/vectordb/chroma `
  --snapshot .tmp/index-dim-windows-target-snapshot-before-activation `
  --evidence .tmp/index-dim-rebuild-result-20260813.json `
  --expected-evidence-sha256 c49feed5812cc44987b4478f0737d99c075f350b8ba66fb8ebba3e70df86a382 `
  --expected-source-sha256 1ce875318d2d4c903a684e7d1dd6326d4dd4366b0e131c6c8418fd9e94835b96
```

The verified result was `ready=true` and `mutation_performed=false`. It fixed
the pre-activation Windows target fingerprint at 627 files / 55,885,536 bytes /
SHA-256 `5c9eff00707d725a06c1a4f442833e675525d888d4d200f85049d9a77963842e`.
The proposed snapshot path remained absent.

## Resume protocol

1. Refresh Git and protect the four owner-dirty files: `BACKLOG.md`,
   `README.md`, `audit_gpt_23_07_26.md`, and `plan_sol_23_07_26`.
2. Confirm no project Python/uvicorn/Celery process has the target open.
3. From an elevated Windows shell, run exactly one owner hypothesis against
   `D:\WSL\Ubuntu-22.04\ext4.vhdx`: set its owner to `JULIADEV25\uedom`,
   verify the owner, and make one ordinary Ubuntu attach attempt. Do not touch
   Docker VHDX files or broaden ACLs. If the same attach error remains, stop
   this hypothesis. Otherwise use the restored Ubuntu capability or a
   separately authorized reachable PostgreSQL `DATABASE_URL`. Do not raw-retry
   the unchanged Docker/WSL startup path. Acquire and release
   the normal `default` tenant advisory-lock context as a connectivity probe.
   Stop if this fails; never bypass the lock or forge a token.
4. Run the verified preflight command above. Stop unless both tree hashes and
   the evidence hash match, `ready=true`, `mutation_performed=false`, and the
   snapshot path is absent.
5. Acquire the `default` tenant lock again and hold it continuously through
   steps 6–10. Recheck the target fingerprint, absent snapshot, absent
   manifest/retention registries, and absence of another runtime after lock
   acquisition and before the first mutation.
6. Move/copy the complete original target to the named snapshot and verify its
   fingerprint equals 627 files / 55,885,536 bytes / SHA
   `5c9eff00707d725a06c1a4f442833e675525d888d4d200f85049d9a77963842e`.
   Install from canonical staging without opening canonical staging with
   Chroma.
7. Before publication, require candidate
   `rag_docs-v-default-3f2b79fbe1246ab3`, count `3`, dimension `1024`, exact
   sources `errors_e10_e30.md`, `returns_policy.md`, and `warranty.md`, E20
   content, and `errors_e10_e30.md` as E20 top-1. No provider call is needed.
   Record retention and publish only through existing lock-guarded APIs.
   Require generation 1 active on the candidate with previous
   `rag_docs_default`.
8. Accept the active candidate, then call the existing rollback API. Require
   generation 2 active on `rag_docs_default` with previous candidate. Preserve
   the installed candidate tree at `.tmp/index-dim-windows-candidate-hold`,
   restore the snapshot to the Windows target, and prove the original target
   fingerprint.
9. Move the restored target back to the snapshot path, reinstall the preserved
   candidate tree, validate it again, and publish it through the same held lock.
   Require generation 3 active on the candidate with previous
   `rag_docs_default`.
10. Repeat count/dimension/source/E20 acceptance and only then release the lock.
    Retain the verified snapshot until final reporting explicitly decides its
    fate.

## Stop and rollback conditions

Stop before the next mutation when any expected path, SHA, count, dimension,
source set, lock result, generation, or runtime condition differs. If target
mutation has started, keep the tenant lock held, use the existing rollback API
when a manifest was published, make the manifest active target compatible with
the legacy snapshot, restore only from the verified snapshot, and recheck its
exact fingerprint. Preserve activation-created sidecar state as diagnostic
evidence if baseline-absent paths must be moved aside; never silently delete or
manually rewrite them. Do not delete either retained collection, reuse the
quarantined opened copy, call a provider, run migrations, deploy, push, or claim
production readiness.

## Done when

- [x] Focused tests, Ruff, scoped MyPy, and diff checks pass.
- [x] Preflight performs no filesystem write and reports
  `mutation_performed=false`.
- [x] Working Windows Chroma remains unchanged; no import, activation,
  manifest switch, deletion, provider call, migration, deploy, or push runs.
- [ ] PostgreSQL advisory-lock acquisition/release is proven before mutation.
- [ ] Snapshot fingerprint matches the original Windows target.
- [ ] Candidate passes count/dimension/source/E20 acceptance without a provider.
- [ ] Manifest generations 1 → 2 → 3 prove publish → rollback → reactivate
  while the same tenant lock remains held.
- [ ] Snapshot restore is proven between rollback and final reactivation, then
  the candidate is accepted again.
- [ ] Final report states the active manifest/collection, retained rollback
  artifact, sidecar state, exact verification results, and any cleanup
  performed.
