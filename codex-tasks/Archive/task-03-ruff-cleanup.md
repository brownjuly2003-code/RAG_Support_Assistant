# Task 03 — Ruff cleanup pass

## Problem
Several files have existing ruff violations that were never fixed.
They block `ruff check .` from passing cleanly across the whole repo.

## Files to fix (one by one, in order)

Run for each file: `ruff check --fix <file>` then manually fix anything --fix can't auto-fix.

1. `cache.py`
2. `evaluation/ragas_eval.py`
3. `prompts.py`
4. `seed_docs.py`
5. `test_retrieval.py`

## Rules
- Fix only: unused imports (F401), line length (E501 — wrap long lines), undefined names (F821)
- Do NOT change any logic, function signatures, or docstrings
- If a line is too long (E501), wrap at 100 chars using Python line continuation or parentheses
- If an import is unused (F401) — remove it unless it's a `__all__` re-export

## CONSTRAINTS
- Touch ONLY the 5 files listed above
- Do NOT touch graph.py, api/app.py, manager.py, state.py, config/ or tests/
- After each file: `ruff check <file>` → 0 errors

## DONE WHEN
- [ ] `ruff check cache.py evaluation/ragas_eval.py prompts.py seed_docs.py test_retrieval.py` → exit code 0
- [ ] `pytest tests/ -v` still shows 15+ passed (no regressions)
