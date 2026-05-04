# Local Gate Wrapper

`scripts/local-gate.ps1` is a non-mutating wrapper for the local gates used by
the autopilot runner. It does not commit, push, deploy, edit files, call live
services, or read secrets.

List the commands without running them:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local-gate.ps1 -List
```

Run a dry-run with tool availability checks:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local-gate.ps1 -DryRun
```

Run the gates:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local-gate.ps1
```

The wrapper runs:

- `git diff --check`
- `ruff check .`
- strict-scope `mypy` for auth, DB, provider, settings, and agent modules
- `mypy api/app.py`
- non-integration pytest with `-p no:schemathesis` and repo-local
  `--basetemp=.tmp/pytest`

It also adds `helm lint deploy/helm/ --strict` when `deploy/helm/` files are
changed, and `pip-audit` when lock files are changed.
