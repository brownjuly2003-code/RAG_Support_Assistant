# Task 172 — Helm chart lint & server-side dry-run audit

## Goal
Проверить что Helm chart `deploy/helm/` проходит `helm lint` и `kubectl apply --dry-run=server` без ошибок/предупреждений, фиксануть все warnings/errors, и привести CI gate на lint.

## Context
- Проект поставляется Helm chart'ом в `deploy/helm/` (`Chart.yaml`, `values.yaml`, `templates/`). В `templates/` 16 манифестов: `deployment.yaml`, `deployment-email-poller.yaml`, `service.yaml`, `ingress.yaml`, `hpa.yaml`, `configmap.yaml` и 10 `cronjob-*.yaml` (включая 4 свежих из Arc 7 Batch J+minors: `cronjob-backup-snapshot.yaml`, `cronjob-backup-integrity.yaml`, `cronjob-restore-verify.yaml`, `cronjob-curated-staleness.yaml`).
- Ни один из этих манифестов не прогонялся через `helm lint` или `kubectl apply --dry-run` в существующей сессии — YAML-синтаксис проверяется только unit-тестами на Python-уровне (строковый grep), которые не ловят Go-template errors, missing values, incorrect API versions, container-image mismatch и т. д.
- CI (`.github/workflows/ci.yml`) сейчас не содержит helm job.

## Deliverables
- `.github/workflows/ci.yml` — новый job `helm`:
  - runs-on: `ubuntu-latest`.
  - steps: checkout → `azure/setup-helm@v4` (pin major) → `helm lint deploy/helm/ --strict` → `helm template deploy/helm/ --values deploy/helm/values.yaml > /tmp/rendered.yaml` → `kubectl apply --dry-run=client -f /tmp/rendered.yaml` (server dry-run не доступен без кластера, client достаточно для schema check).
  - trigger: `pull_request`, `push` в `master`.
- `deploy/helm/values.yaml` — добавить sane defaults для всех `.Values.*` refs чтобы `helm template` не падал на missing values. Если уже есть — ничего не трогать.
- Исправить любые warnings/errors из `helm lint --strict` и `kubectl apply --dry-run=client`:
  - missing `apiVersion` / `kind`.
  - `spec.schedule` для CronJob'ов должен быть валидный cron.
  - container image refs должны использовать `{{ .Values.image.repository }}:{{ .Values.image.tag }}` (не hardcoded).
  - `resources.requests/limits` — присутствуют для всех контейнеров.
  - labels `app.kubernetes.io/*` — стандартные chart labels везде где применимо.
- `docs/operations/helm-lint.md` — короткая страница: как локально прогнать `helm lint deploy/helm/` + пример вывода + список ожидаемых warnings (если есть acceptable-by-design).
- `docs/CHANGELOG.md` — запись про helm lint gate.

## Acceptance criteria
- [ ] Локально `helm lint deploy/helm/ --strict` завершается exit 0, без warnings.
- [ ] Локально `helm template deploy/helm/ --values deploy/helm/values.yaml | kubectl apply --dry-run=client -f -` завершается exit 0 для всех 16+ манифестов.
- [ ] CI job `helm` зелёный в PR preview.
- [ ] Rendered CronJob'ы имеют корректный `spec.schedule` (валидный 5-field cron), `restartPolicy: OnFailure`, `backoffLimit`.
- [ ] Rendered Deployment имеет `readinessProbe` и `livenessProbe`, `resources.requests/limits`.
- [ ] `helm template` вывод детерминирован (двукратный прогон даёт идентичный результат, кроме timestamps).
- [ ] Unit suite без регрессий.

## Notes
- `helm` на Windows-разработки нет; CX может работать под Ubuntu (GitHub-hosted runner или Docker image). Локально CX может установить `helm` через `brew install helm` / `snap install helm --classic` / `curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash`.
- `kubectl` client-side dry-run не требует kubeconfig/cluster — `kubectl apply --dry-run=client -f manifest.yaml` работает off-line.
- Не использовать `helm install --dry-run` — требует реального кластера. `helm template` + `kubectl apply --dry-run=client` эквивалентны для schema check.
- Если `--strict` lint выдаёт warning про best-practice labels (`app.kubernetes.io/managed-by`, `helm.sh/chart`) — добавить в `templates/_helpers.tpl` стандартный helpers блок (`define "chart.labels"`) и переиспользовать везде.
- Не менять behaviour манифестов (schedule, env, volumes) — только fix warnings и correctness.
- Если lint обнаружит fundamental issue (например, CronJob `apiVersion: batch/v1beta1` deprecated в k8s 1.25+) — обновить до current stable (`batch/v1`).
