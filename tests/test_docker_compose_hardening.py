from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_compose() -> dict:
    return yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_default_compose_is_labeled_local_dev_only() -> None:
    content = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "Local development only" in content
    assert "not a production deployment manifest" in content


def test_default_compose_binds_published_ports_to_loopback() -> None:
    compose = _load_compose()

    exposed_ports = {
        service_name: port
        for service_name, service in compose["services"].items()
        for port in service.get("ports", [])
    }

    assert exposed_ports
    assert all(str(port).startswith("127.0.0.1:") for port in exposed_ports.values())


def test_default_compose_forces_development_environment() -> None:
    compose = _load_compose()

    assert "RAG_ENV=development" in compose["services"]["app"]["environment"]
