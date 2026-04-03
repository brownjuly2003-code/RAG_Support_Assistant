# Task 06 — Close global ruff check

## Problem
`ruff check .` fails on two files outside the main codebase:
- `graph_route_example.py` — example/demo file
- `Сброс настрок COMET.py` — unrelated utility, Cyrillic filename

## Solution: two steps

### Step 1 — Create pyproject.toml
Create `pyproject.toml` in project root:

```toml
[tool.ruff]
line-length = 100
exclude = [
    "Сброс настрок COMET.py",
    "graph_route_example.py",
]

[tool.ruff.lint]
select = ["E", "F", "W"]
ignore = ["E501"]
```

### Step 2 — Fix graph_route_example.py
Run `ruff check --fix graph_route_example.py`.
Then manually fix any remaining violations.
Do NOT change the logic or structure of the file — only import/style fixes.

## CONSTRAINTS
- Create ONLY `pyproject.toml` and fix `graph_route_example.py`
- Do NOT touch any other file
- After fix: `ruff check .` → exit code 0

## DONE WHEN
- [ ] `ruff check .` exits with code 0 (no output)
- [ ] `pytest tests/ -v` still shows 16 passed
