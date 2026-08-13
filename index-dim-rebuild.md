# INDEX-DIM-REBUILD

## Goal

Produce a validated versioned 1024D candidate from an isolated copy of the
incompatible Windows 3D index while preserving the old collection and proving
the rollback path. Import or activation in a working runtime is out of scope.

## Tasks

- [x] Confirm the canonical tenant, source documents, provider profile, active
  manifest, and retained collections without exposing secrets or mutating data.
- [x] Snapshot the active manifest and prove the current 3D/1024D mismatch.
- [x] Build a separate versioned candidate through the existing tenant-locked
  lifecycle path; do not delete or overwrite the active collection.
- [x] Validate candidate dimension, document/content count, and a known-query
  result before publication.
- [x] Publish only the validated candidate, then verify runtime retrieval and
  manifest/cache state; rollback to the captured manifest if the smoke fails.
- [x] Record concise non-secret evidence and run final scoped verification.

## Done When

- [x] Isolated artifact manifest points to the validated 1024D versioned
  collection.
- [x] Runtime retrieval passes without a dimension mismatch.
- [x] Previous 3D collection remains present and rollback-ready.
- [x] No push, deploy, migration, production access, or collection deletion ran.

## Mac execution evidence — 2026-08-13

- Isolated checkout: `~/RAG_Support_Assistant-index-rebuild-20260813` at
  `7ed9cd3`; the primary Mac checkout and its `5589 × 1024` default corpus were
  not mutated.
- Imported Windows baseline: legacy `rag_docs_default` was `6 × 3`, with no
  manifest or retention inventory.
- Final candidate: `rag_docs-v-default-3f2b79fbe1246ab3`, `3 × 1024` from the
  three canonical demo documents.
- Lifecycle proof: publish generation `1`, rollback to legacy generation `2`,
  reactivation generation `3`; final `previous_collection=rag_docs_default`.
- Known query `Что означает ошибка E20?` returned `errors_e10_e30.md`; no
  source collection was deleted.
- Imported Chroma artifact (56 MiB observed):
  `/Users/julia/RAG_Support_Assistant-index-rebuild-20260813/.runtime/windows-chroma`.
- Non-secret result artifact:
  `/Users/julia/RAG_Support_Assistant-index-rebuild-20260813/.runtime/index-dim-rebuild-result.json`,
  SHA-256
  `c49feed5812cc44987b4478f0737d99c075f350b8ba66fb8ebba3e70df86a382`.
- Independent persisted-state inspection passed. The corrected focused gate
  used the actual `tests/test_index_version_manifest.py` path and passed
  **73 tests** across manifest, runtime-switch, retention, and lifecycle fault
  injection; one pre-existing Starlette deprecation warning remains.
- This artifact did not replace the working Windows Chroma directory or the
  primary Mac corpus. Import/activation is a separate target-specific slice.
- Restart state is **artifact-closed / activation-open**. The Windows target is
  `D:\RAG_Support_Assistant\data\vectordb\chroma`; do not overwrite it without
  a recoverable snapshot plus dimension/content/E20 smoke and rollback checks.
