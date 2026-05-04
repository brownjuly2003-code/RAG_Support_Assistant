# Windows Test Workflow

Run these commands from the repository root in Windows PowerShell.

## Full Suite

```powershell
python -m pytest -p no:schemathesis --basetemp=.tmp/pytest
```

`-p no:schemathesis` disables the auto-loaded Schemathesis pytest plugin that
is broken on the current Windows development machine. `--basetemp=.tmp/pytest`
keeps pytest temp files inside the repository when the user temp root is not
readable.

## Focused Runs

Use the same pytest flags for focused suites:

```powershell
python -m pytest tests/test_provider_settings.py -q -p no:schemathesis --basetemp=.tmp/pytest-focused
```

For integration tests:

```powershell
python -m pytest tests/integration -q -p no:schemathesis --basetemp=.tmp/pytest-integration
```

Some integration, browser, Docker, or external-tool tests may skip when the
optional dependency or service is unavailable locally.
