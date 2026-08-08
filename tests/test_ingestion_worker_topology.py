"""Contracts for plan step 4.2: operational ingestion worker topology.

Covers Compose worker service, shared worker-health probe, and Helm sidecar
topology with fail-closed single-slot invariants.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"
HELM_DIR = ROOT / "deploy" / "helm"
TEMPLATES = HELM_DIR / "templates"
VALUES = HELM_DIR / "values.yaml"
DEPLOYMENT = TEMPLATES / "deployment.yaml"
WORKER_HEALTH = ROOT / "tasks" / "worker_health.py"

_HELM = shutil.which("helm")
requires_helm = pytest.mark.skipif(_HELM is None, reason="helm binary not available")

_BASE_SET = [
    "--set",
    "secrets.existingSecret=ci-placeholder",
    "--set",
    "env.CORS_ORIGINS=https://support.example.com",
    "--set",
    "postgresql.auth.password=ci-placeholder",
]


def _load_compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _load_values() -> dict[str, Any]:
    return yaml.safe_load(VALUES.read_text(encoding="utf-8"))


def _helm_template(*extra: str) -> subprocess.CompletedProcess[str]:
    assert _HELM is not None
    cmd = [
        _HELM,
        "template",
        "rag-test",
        str(HELM_DIR),
        "--values",
        str(VALUES),
        *_BASE_SET,
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _docs(rendered: str) -> list[dict[str, Any]]:
    return [d for d in yaml.safe_load_all(rendered) if d]


def _by_kind(docs: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [d for d in docs if d.get("kind") == kind]


def _app_deployment(docs: list[dict[str, Any]]) -> dict[str, Any]:
    return next(d for d in _by_kind(docs, "Deployment") if d["metadata"]["name"] == "rag-test-app")


def _containers_by_name(dep: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in dep["spec"]["template"]["spec"]["containers"]}


def _env_map(service: dict[str, Any]) -> dict[str, str]:
    """Normalize compose environment list/map into a flat str->str dict."""
    raw = service.get("environment", {})
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    out: dict[str, str] = {}
    for item in raw:
        key, _, value = str(item).partition("=")
        out[key] = value
    return out


def _command_text(service: dict[str, Any]) -> str:
    cmd = service.get("command")
    if cmd is None:
        return ""
    if isinstance(cmd, list):
        return " ".join(str(part) for part in cmd)
    return str(cmd)


def _grace_seconds(value: Any) -> int:
    """Normalize Compose/Helm grace values to whole seconds."""
    if isinstance(value, bool):
        raise AssertionError(f"unexpected boolean grace value: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().lower()
    if text.endswith("ms"):
        return int(text[:-2]) // 1000
    if text.endswith("s"):
        return int(text[:-1])
    if text.endswith("m"):
        return int(text[:-1]) * 60
    if text.endswith("h"):
        return int(text[:-1]) * 3600
    return int(text)


# ---------------------------------------------------------------------------
# Compose worker topology
# ---------------------------------------------------------------------------


def test_compose_defines_single_ingestion_worker_service() -> None:
    compose = _load_compose()
    services = compose["services"]
    assert "worker" in services
    worker = services["worker"]
    app = services["app"]

    # Same image/source as app
    assert worker.get("build") == app.get("build")
    assert worker.get("image") == app.get("image")

    # Same env file
    assert worker.get("env_file") == app.get("env_file")

    # Required public env parity with app
    worker_env = _env_map(worker)
    app_env = _env_map(app)
    for key in (
        "RAG_ENV",
        "OLLAMA_BASE_URL",
        "DATABASE_URL",
        "REDIS_URL",
        "OTEL_ENABLED",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_SERVICE_NAME",
    ):
        assert key in worker_env, f"worker missing env {key}"
        assert worker_env[key] == app_env[key], f"worker env {key} diverges from app"

    cmd = _command_text(worker)
    assert "tasks.celery_app:celery_app" in cmd
    assert "worker" in cmd
    assert "--concurrency=1" in cmd or "--concurrency 1" in cmd
    # Stable node-name pattern addressable by the health probe
    assert "ingest@" in cmd
    assert "%h" in cmd or "hostname" in cmd.lower()

    # Shared durable data mount
    assert "./data:/app/data" in worker.get("volumes", [])
    assert "./data:/app/data" in app.get("volumes", [])

    # No host ports on the worker
    assert not worker.get("ports")

    # Safe restart + long warm-shutdown grace for ingestion.
    # No Celery task_time_limit is configured in-repo; embedding/indexing of
    # large docs can exceed a few minutes, so default grace is 3600s.
    assert worker.get("restart") == "unless-stopped"
    grace = worker.get("stop_grace_period")
    assert grace is not None
    assert _grace_seconds(grace) >= 3600

    # Depends on the same required stack as the app
    worker_deps = worker.get("depends_on", {})
    app_deps = app.get("depends_on", {})
    for dep_name, dep_cfg in app_deps.items():
        assert dep_name in worker_deps
        assert worker_deps[dep_name] == dep_cfg

    # Exactly one dedicated ingestion *worker* (concurrency path). Plan §4.6 may
    # add a Celery *beat* schedule process (worker-beat) — that is not a second
    # ingestion worker and must not claim parallel ingest concurrency.
    celery_services = [
        name
        for name, svc in services.items()
        if "tasks.celery_app:celery_app" in _command_text(svc)
    ]
    assert "worker" in celery_services
    ingest_workers = [
        name
        for name in celery_services
        if re.search(r"(^|[\s])worker([\s]|$)", _command_text(services[name]))
    ]
    assert ingest_workers == ["worker"], (
        f"expected single ingest worker, got {ingest_workers}"
    )

    # Healthcheck must invoke the exact-worker probe (not a PID/process grep)
    health = worker.get("healthcheck")
    assert health is not None
    test = health.get("test")
    assert test is not None
    test_text = " ".join(str(p) for p in test) if isinstance(test, list) else str(test)
    assert "worker_health" in test_text
    assert "pgrep" not in test_text.lower()
    assert "ps " not in test_text.lower()
    assert "grep" not in test_text.lower()


# ---------------------------------------------------------------------------
# Worker health helper
# ---------------------------------------------------------------------------


def test_worker_health_module_exists_and_has_no_import_time_network() -> None:
    assert WORKER_HEALTH.is_file()
    source = WORKER_HEALTH.read_text(encoding="utf-8")
    # No network work / broker contact at import time: ping must be inside a function
    assert "def " in source
    # Control ping should not run at module import scope
    top_level = []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(('"""', "'''")):
            continue
        if line[:1].isspace():
            continue
        top_level.append(stripped)
    top_joined = "\n".join(top_level)
    assert "control.ping" not in top_joined
    assert "ping(" not in top_joined or "def " in top_joined


def test_worker_health_node_matches_celery_percent_h_identity() -> None:
    """Celery ``--hostname=ingest@%h`` expands ``%h`` via socket.gethostname().

    Probe destination must use the same host token so exact-node pings work
    inside Linux containers (short or FQDN hostnames).
    """
    from celery.utils.nodenames import host_format

    from tasks import worker_health

    for host in ("testhost", "rag-app-abc123", "pod.namespace.svc.cluster.local"):
        celery_node = host_format("ingest@%h", host)
        assert celery_node == f"ingest@{host}"
        assert worker_health.expected_node_name(host) == celery_node


def test_worker_health_success_on_valid_pong(monkeypatch: pytest.MonkeyPatch) -> None:
    from tasks import worker_health

    node = worker_health.expected_node_name("testhost")
    assert node == "ingest@testhost"

    monkeypatch.setattr(worker_health.socket, "gethostname", lambda: "testhost")
    fake_control = MagicMock()
    fake_control.ping.return_value = [{node: {"ok": "pong"}}]
    fake_app = SimpleNamespace(control=fake_control)
    monkeypatch.setattr(worker_health, "_get_celery_app", lambda: fake_app)

    assert worker_health.check_worker(timeout=0.5) == 0
    fake_control.ping.assert_called_once()
    kwargs = fake_control.ping.call_args.kwargs
    assert kwargs["destination"] == [node]
    # Requested timeout must reach control.ping (not a hard-coded inner value).
    assert kwargs["timeout"] == 0.5


@pytest.mark.parametrize(
    "replies",
    [
        [],
        None,
        [{}],
        [{"other@host": {"ok": "pong"}}],
        [{"ingest@testhost": {"ok": "not-pong"}}],
        [{"ingest@testhost": "pong"}],
        "pong",
        [{"ingest@testhost": {"ok": "pong"}, "extra": 1}],  # still ok if primary valid
    ],
)
def test_worker_health_rejects_empty_or_malformed_replies(
    monkeypatch: pytest.MonkeyPatch,
    replies: Any,
) -> None:
    from tasks import worker_health

    monkeypatch.setattr(worker_health.socket, "gethostname", lambda: "testhost")
    node = "ingest@testhost"
    fake_control = MagicMock()
    fake_control.ping.return_value = replies
    fake_app = SimpleNamespace(control=fake_control)
    monkeypatch.setattr(worker_health, "_get_celery_app", lambda: fake_app)

    # The dual-key dict case still contains a valid pong for the expected node.
    if (
        isinstance(replies, list)
        and replies
        and isinstance(replies[0], dict)
        and isinstance(replies[0].get(node), dict)
        and replies[0][node].get("ok") == "pong"
    ):
        assert worker_health.check_worker() == 0
    else:
        assert worker_health.check_worker() == 1


def test_worker_health_exception_returns_nonzero_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tasks import worker_health

    monkeypatch.setattr(worker_health.socket, "gethostname", lambda: "testhost")

    def _boom(**_kwargs: Any) -> list[Any]:
        raise ConnectionError(
            "Error connecting to redis://:super-secret-password@redis:6379/0"
        )

    fake_control = MagicMock()
    fake_control.ping.side_effect = _boom
    fake_app = SimpleNamespace(control=fake_control)
    monkeypatch.setattr(worker_health, "_get_celery_app", lambda: fake_app)

    assert worker_health.check_worker() == 1
    # main() path should also stay secret-free
    with pytest.raises(SystemExit) as exc:
        worker_health.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "super-secret-password" not in combined
    assert "redis://" not in combined
    assert "ConnectionError" not in combined


# ---------------------------------------------------------------------------
# Helm values + static template contracts
# ---------------------------------------------------------------------------


def test_helm_values_define_worker_defaults() -> None:
    values = _load_values()
    worker = values["worker"]
    assert worker["enabled"] is True
    assert worker["concurrency"] == 1
    assert isinstance(worker["concurrency"], int)
    assert "logLevel" in worker
    assert "resources" in worker
    assert "requests" in worker["resources"]
    assert "limits" in worker["resources"]
    # Match Compose: long warm-shutdown default (no in-repo task_time_limit).
    assert int(worker["terminationGracePeriodSeconds"]) >= 3600
    # Probe timings present
    for probe in ("readinessProbe", "livenessProbe"):
        assert probe in worker
        for key in ("initialDelaySeconds", "periodSeconds", "timeoutSeconds", "failureThreshold"):
            assert key in worker[probe]


def test_helm_deployment_template_has_worker_sidecar_and_fail_closed() -> None:
    dep = DEPLOYMENT.read_text(encoding="utf-8")
    assert "worker.enabled" in dep
    assert "worker.concurrency" in dep
    assert "tasks.celery_app:celery_app" in dep
    assert "worker_health" in dep
    assert "terminationGracePeriodSeconds" in dep
    assert "fail" in dep
    # Fail-closed mentions for multi-slot / missing data
    assert "replicaCount" in dep
    assert "persistence.data" in dep


# ---------------------------------------------------------------------------
# Helm render contracts
# ---------------------------------------------------------------------------


@requires_helm
def test_helm_default_render_includes_enabled_worker_sidecar() -> None:
    result = _helm_template()
    assert result.returncode == 0, result.stderr
    dep = _app_deployment(_docs(result.stdout))
    pod = dep["spec"]["template"]["spec"]
    containers = _containers_by_name(dep)

    assert "app" in containers
    assert "worker" in containers
    assert len(containers) == 2

    worker = containers["worker"]
    app = containers["app"]

    # Same image
    assert worker["image"] == app["image"]

    # Same envFrom (ConfigMap + Secret)
    assert worker.get("envFrom") == app.get("envFrom")
    assert any("configMapRef" in str(e) for e in worker["envFrom"])
    assert any("secretRef" in str(e) for e in worker["envFrom"])

    # Command / concurrency / node name
    cmd_parts = [str(p) for p in (worker.get("command") or []) + (worker.get("args") or [])]
    cmd = " ".join(cmd_parts)
    assert "tasks.celery_app:celery_app" in cmd
    assert "worker" in cmd
    assert "--concurrency=1" in cmd or "--concurrency" in cmd_parts
    assert "--hostname=ingest@%h" in cmd or "ingest@%h" in cmd

    # Sidecar publishes no container port (app alone owns :8000)
    assert not worker.get("ports")

    # Writable /app/data
    mounts = {m["name"]: m for m in worker.get("volumeMounts", [])}
    assert mounts["data"]["mountPath"] == "/app/data"
    assert mounts["data"].get("readOnly") in (None, False)

    # Security contexts
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert worker["securityContext"]["runAsNonRoot"] is True
    assert worker["securityContext"]["allowPrivilegeEscalation"] is False
    assert "ALL" in worker["securityContext"]["capabilities"]["drop"]

    # Resources from worker values
    assert "resources" in worker
    assert "requests" in worker["resources"]
    assert "limits" in worker["resources"]

    # Probes address exact worker via worker_health
    for probe_name in ("readinessProbe", "livenessProbe"):
        probe = worker[probe_name]
        assert "exec" in probe
        probe_cmd = " ".join(str(p) for p in probe["exec"]["command"])
        assert "worker_health" in probe_cmd
        assert probe["initialDelaySeconds"] >= 1
        assert probe["periodSeconds"] >= 1
        assert probe["timeoutSeconds"] >= 1
        assert probe["failureThreshold"] >= 1

    # Long pod termination grace (defensible default for embedding/indexing)
    assert int(pod["terminationGracePeriodSeconds"]) >= 3600

    # Checksum annotations still present on the pod template
    annotations = dep["spec"]["template"]["metadata"]["annotations"]
    assert "checksum/config" in annotations
    assert "checksum/secret" in annotations
    assert re.fullmatch(r"[0-9a-f]{64}", annotations["checksum/config"])
    assert re.fullmatch(r"[0-9a-f]{64}", annotations["checksum/secret"])

    # Single replica remains the default
    assert dep["spec"]["replicas"] == 1


@requires_helm
def test_helm_worker_disabled_leaves_app_contract_intact() -> None:
    result = _helm_template("--set", "worker.enabled=false")
    assert result.returncode == 0, result.stderr
    dep = _app_deployment(_docs(result.stdout))
    containers = _containers_by_name(dep)

    assert list(containers) == ["app"]
    assert "worker" not in containers
    # No worker-driven termination grace override required when disabled
    # (either absent or left at cluster default — must not break app)
    app = containers["app"]
    assert app["ports"][0]["containerPort"] == 8000
    assert "envFrom" in app
    assert "readinessProbe" in app
    assert "livenessProbe" in app
    # Data mount still present under default persistence
    mounts = {m["name"]: m for m in app.get("volumeMounts", [])}
    assert mounts["data"]["mountPath"] == "/app/data"
    annotations = dep["spec"]["template"]["metadata"]["annotations"]
    assert "checksum/config" in annotations
    assert "checksum/secret" in annotations


@requires_helm
def test_helm_fail_closed_when_worker_enabled_without_data_persistence() -> None:
    result = _helm_template(
        "--set",
        "env.RAG_ENV=development",
        "--set",
        "persistence.data.enabled=false",
        # worker remains enabled by default
    )
    assert result.returncode != 0
    combined = ((result.stderr or "") + (result.stdout or "")).lower()
    assert "worker" in combined or "persistence" in combined or "data" in combined


@requires_helm
def test_helm_fail_closed_when_replica_count_not_one_with_worker() -> None:
    result = _helm_template("--set", "replicaCount=2")
    assert result.returncode != 0
    combined = ((result.stderr or "") + (result.stdout or "")).lower()
    assert "replica" in combined or "worker" in combined


@requires_helm
def test_helm_fail_closed_when_worker_concurrency_not_one() -> None:
    result = _helm_template("--set", "worker.concurrency=2")
    assert result.returncode != 0
    combined = ((result.stderr or "") + (result.stdout or "")).lower()
    assert "concurrency" in combined or "worker" in combined


@requires_helm
def test_helm_nonproduction_data_disabled_with_worker_disabled_renders() -> None:
    """Existing non-prod data-disabled path remains only when worker is off."""
    result = _helm_template(
        "--set",
        "env.RAG_ENV=development",
        "--set",
        "persistence.data.enabled=false",
        "--set",
        "worker.enabled=false",
    )
    assert result.returncode == 0, result.stderr
    dep = _app_deployment(_docs(result.stdout))
    containers = _containers_by_name(dep)
    assert "worker" not in containers
    app = containers["app"]
    readiness = app["readinessProbe"]
    assert readiness["httpGet"]["path"] == "/api/health/ready"
    assert "exec" not in readiness


@requires_helm
def test_helm_existing_data_claim_keeps_worker_sidecar() -> None:
    result = _helm_template("--set", "persistence.data.existingClaim=ext-data")
    assert result.returncode == 0, result.stderr
    docs = _docs(result.stdout)
    dep = _app_deployment(docs)
    containers = _containers_by_name(dep)
    assert "app" in containers
    assert "worker" in containers

    volumes = {
        v["name"]: v for v in dep["spec"]["template"]["spec"].get("volumes", [])
    }
    assert volumes["data"]["persistentVolumeClaim"]["claimName"] == "ext-data"
    for name in ("app", "worker"):
        mounts = {m["name"]: m for m in containers[name].get("volumeMounts", [])}
        assert mounts["data"]["mountPath"] == "/app/data"
        assert mounts["data"].get("readOnly") in (None, False)


@requires_helm
def test_helm_non_default_image_tag_shared_by_worker() -> None:
    result = _helm_template("--set", "image.tag=1.2.3-qa")
    assert result.returncode == 0, result.stderr
    dep = _app_deployment(_docs(result.stdout))
    containers = _containers_by_name(dep)
    assert "worker" in containers
    assert containers["worker"]["image"] == containers["app"]["image"]
    assert "1.2.3-qa" in containers["worker"]["image"]


def test_deployment_docs_distinguish_web_and_ingestion_and_list_open_gates() -> None:
    text = (ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    # Web vs ingestion roles must not be collapsed into one "worker".
    assert "Uvicorn" in text
    assert "Celery" in text
    assert "--concurrency=1" in text
    assert "ingest@%h" in text or "ingest@<hostname>" in text
    # Long warm-shutdown default (seconds), consistent with Compose/Helm.
    assert "3600" in text
    # Still-open reliability gates — topology slice must not claim them done.
    lowered = text.lower()
    for needle in (
        "reaper",
        "idempotency",
        "queue-age",
        "ing-02",
        "ten-03",
        "live",
    ):
        assert needle in lowered, f"DEPLOYMENT.md missing open-gate mention: {needle}"
