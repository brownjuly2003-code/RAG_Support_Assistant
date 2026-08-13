# INDEX-DIM Windows activation readiness

## Goal

Make activation of the verified Mac-built `3 × 1024` Chroma artifact against
the working Windows corpus fail closed before any snapshot, copy, manifest
switch, or collection mutation.

## Tasks

- [x] Add a read-only preflight contract for exact source, target, snapshot,
  evidence hash, candidate shape, tree fingerprints, and disk headroom.
- [x] Prove the contract red before implementation and green afterward.
- [x] Run the preflight only after the artifact is copied to a local staging
  directory; copying and activation remain separate authorized operations.
- [ ] During a later activation slice, create and verify the snapshot before
  copying, then run dimension/content/E20 smoke and preserve a tested rollback.

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

## Done when

- [x] Focused tests, Ruff, scoped MyPy, and diff checks pass.
- [x] Preflight performs no filesystem write and reports
  `mutation_performed=false`.
- [x] Working Windows Chroma remains unchanged; no import, activation,
  manifest switch, deletion, provider call, migration, deploy, or push runs.
