# Task 04 — GitHub Actions CI pipeline

## Create one new file: .github/workflows/ci.yml

```yaml
name: CI

on:
  push:
    branches: ["master", "main"]
  pull_request:
    branches: ["master", "main"]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Lint
        run: ruff check .

      - name: Test
        run: pytest tests/ -v --tb=short
```

Copy this exactly. No changes.

## CONSTRAINTS
- Create ONLY `.github/workflows/ci.yml`
- Do NOT modify any existing files
- Do NOT add any other workflow files

## DONE WHEN
- [ ] `.github/workflows/ci.yml` exists
- [ ] `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` parses without error
