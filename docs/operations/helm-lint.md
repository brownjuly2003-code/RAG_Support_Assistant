# Helm lint runbook

Аудитория: разработчик / SRE. Документ описывает локальную проверку chart `deploy/helm/` перед PR или ручным релизом.

## Что проверяем

- `helm lint deploy/helm/ --strict`
- `helm template deploy/helm/ --values deploy/helm/values.yaml`
- `kubectl apply --dry-run=client -f rendered.yaml`

## Предварительные требования

- `helm` 3.x
- `kubectl`
- Docker
- `kind` для локального API discovery

Все команды ниже запускать из корня репозитория.

## Команды

```bash
helm lint deploy/helm/ --strict
helm template deploy/helm/ --values deploy/helm/values.yaml > /tmp/rendered.yaml
kind delete cluster --name rag-helm-lint || true
kind create cluster --name rag-helm-lint
kubectl apply --dry-run=client -f /tmp/rendered.yaml
kind delete cluster --name rag-helm-lint
```

Для PowerShell вместо `/tmp/rendered.yaml` используйте `$env:TEMP\\rag-rendered.yaml`.

## Почему локально нужен kind

Актуальные версии `kubectl` даже с `--dry-run=client` всё равно делают API discovery и без доступного API server могут падать на `failed to download openapi` или `unable to recognize`. Поэтому локальная и CI-проверка поднимают временный `kind` cluster, но сама валидационная команда остаётся той же: `kubectl apply --dry-run=client -f rendered.yaml`.

## Пример вывода

```text
==> Linting deploy/helm

1 chart(s) linted, 0 chart(s) failed

configmap/release-name-config created (dry run)
service/release-name-app created (dry run)
deployment.apps/release-name-email-poller created (dry run)
deployment.apps/release-name-app created (dry run)
horizontalpodautoscaler.autoscaling/release-name-app created (dry run)
...
cronjob.batch/release-name-kb-builder created (dry run)
```

## Ожидаемые warnings

Допустимых warnings нет. Ожидаемое состояние:

- `helm lint deploy/helm/ --strict` завершает работу с exit 0
- `kubectl apply --dry-run=client -f rendered.yaml` завершает работу с exit 0
