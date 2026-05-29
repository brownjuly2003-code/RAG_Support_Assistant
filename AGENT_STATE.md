# Agent State

## Current Project State

- Project: RAG Support Assistant.
- Stack: Python 3.13, FastAPI, LangGraph, ChromaDB, Postgres, Redis, static HTML UI, Helm/Docker deploy artifacts.
- Branch: `colab-remote-benchmark`, tracking `origin/colab-remote-benchmark`.
- Snapshot date: 2026-05-30 (Europe/Bucharest).
- Baseline HEAD before this state refresh: `6755403844f35cc86df269ae2a4030c66bf336fb`.
- Baseline file count: 697 tracked files from `git ls-files`.
- Baseline JS bundle size: not applicable; no frontend bundler config was found.
- Baseline i18n key count: not applicable; no i18n JSON catalog was found.
- Git status at snapshot time: clean before this `AGENT_STATE.md` refresh.
- Origin sync at baseline: `colab-remote-benchmark` was current with `origin/colab-remote-benchmark` at `6755403`. PR #1 is open and mergeable; CI passed on this code head before this docs-only handoff refresh. Merge/deploy/release remain explicit boundaries.

## Runtime

- Shell context: Windows PowerShell 5.1 in `D:\RAG_Support_Assistant`.
- pi CLI: available, `pi 0.72.1`.
- codex CLI: available, `codex-cli 0.128.0`.
- Python: available, `Python 3.13.7`.
- Local gate tools observed: `ruff`, `pytest`, `mypy`, `helm`, `bandit`, `pip-audit`, `pre-commit`.

## Last Verified Gates

- `git status --short --branch`: clean on `colab-remote-benchmark...origin/colab-remote-benchmark` before this `AGENT_STATE.md` refresh.
- `git rev-parse HEAD`: `6755403844f35cc86df269ae2a4030c66bf336fb`.
- `git ls-files | Measure-Object`: 697 tracked files.
- `python -c "import json, pathlib; json.loads(pathlib.Path(r'notebooks\\rag_support_colab_remote_benchmark.ipynb').read_text(encoding='utf-8')); print('notebook json ok')"`: passed before commit `a461fba`.
- `git diff --check`: passed before commit `a461fba`.
- `git ls-remote --heads origin colab-remote-benchmark`: `a461fbae52b56a9356215e3185469f22ca41a24a`.
- `Get-Command pi`: available.
- `Get-Command codex`: available.
- `pi --version`: `0.72.1`.
- `codex --version`: `codex-cli 0.128.0`.
- `powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun`: not rerun on 2026-05-30 because the current WIP is docs/notebook-only and local resource constraints forbid unnecessary heavy gates.
- PAUSE protocol dry-run simulation: passed (last verified 2026-05-04).
- BLOCKED protocol dry-run simulation: passed (last verified 2026-05-04).
- `python -m pytest -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-may07-snapshot --ignore=tests/integration`: 735 passed, 4 skipped (verified 2026-05-07 at `d0016c2`; 16:20 wall time).
- `python -m mypy auth db/models.py db/engine.py llm/providers/ config/settings.py agent/state.py agent/prompts.py agent/prompt_registry.py agent/tools.py agent/graph.py --no-incremental`: 18 source files clean (verified 2026-05-07).
- `python -m mypy api/app.py --no-incremental --follow-imports=skip`: clean (verified 2026-05-07).
- `python -m pytest tests/test_precommit_config.py -q -p no:schemathesis -p no:cacheprovider`: 9 passed, 1 warning (verified 2026-05-30 at `6755403`).
- `ruff check tests/test_precommit_config.py`: All checks passed (verified 2026-05-30 at `6755403`).
- `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path(r'.github\\workflows\\ci.yml').read_text(encoding='utf-8')); yaml.safe_load(pathlib.Path(r'.pre-commit-config.yaml').read_text(encoding='utf-8')); print('yaml ok')"`: passed (verified 2026-05-30 at `6755403`).
- `python -m ruff check .`: All checks passed (verified 2026-05-30 before `6755403`; latest code-only change after that was limited to `tests/test_precommit_config.py` and was checked with targeted Ruff above).
- `python -m bandit -r . -ll -c pyproject.toml -x ./tests,./.venv,./reports,./data,./archive-legacy,./.tmp`: 0 medium / 0 high (39 low informational), verified 2026-05-07.
- `pip-audit --strict --disable-pip --require-hashes --timeout 15 --progress-spinner off --cache-dir .tmp/pip-audit-cache --ignore-vuln CVE-2026-45829 --ignore-vuln GHSA-f4j7-r4q5-qw2c -r requirements.lock`: no known vulnerabilities found, 1 ignored (verified 2026-05-30 after the ChromaDB lock update).
- `gh pr checks 1 --watch`: all non-skipped CI jobs passed on PR #1 code head `6755403` before this docs-only handoff refresh (helm, lint, migrations, pre-commit, regression-eval, security, test-integration, test-unit, type-check).

## Operating Mode

- Applicability status: READY_WITH_GUARDRAILS.
- Scheduler status: not installed by this setup; scheduler installation is opt-in only.
- Allowed default safe work: `docs/plans/2026-05-01-backlog.md`, bounded local tasks with exact allowed paths, and local verification.
- Default forbidden work: secrets, deploy, push, production data, live external services, paid API calls, destructive commands.

## Next Step

All `docs/plans/2026-05-01-backlog.md` items remain closed. The current WIP is
the Colab remote benchmark PR:

- `905a65e` adds `docs/operations/colab-remote-benchmark.md` and
  `notebooks/rag_support_colab_remote_benchmark.ipynb`.
- `b5eb848` records the Windows laptop thin-client boundary.
- `a461fba` aligns the notebook to clone `colab-remote-benchmark` and ignores
  `.pytest-tmp*/` local pytest basetemp directories.
- `fe9a474` clears notebook Ruff and security CI issues.
- `965ccd5` documents the narrow unfixed ChromaDB audit ignore.
- `6755403` aligns the CI security config test with the multiline locked
  `pip-audit` command.

The explicitly allowed branch push was completed:
`git push origin colab-remote-benchmark:colab-remote-benchmark`. PR #1
(`https://github.com/brownjuly2003-code/RAG_Support_Assistant/pull/1`) is open,
mergeable, and had green CI on code head `6755403` before this docs-only
handoff refresh. Do not merge, deploy, release, delete branches, or enable
auto-merge without a new explicit instruction.

Notebook URL for manual Colab use:
`https://colab.research.google.com/github/brownjuly2003-code/RAG_Support_Assistant/blob/colab-remote-benchmark/notebooks/rag_support_colab_remote_benchmark.ipynb`

To run another dry-run of the autopilot guardrails:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun
```

Default safe work should come from `docs/plans/2026-05-01-backlog.md`; scheduler installation remains opt-in only.
