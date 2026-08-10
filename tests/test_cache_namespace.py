"""Focused tests for §9.1c versioned LLM response-cache namespace."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from evaluation.experiment_schema import Experiment

namespace = importlib.import_module("cache.namespace")


def _settings(
    *,
    vector_backend: str = "chroma",
    vectordb_chroma_dir: Path | str = "data/vectordb/chroma",
    vectordb_collection_prefix: str = "rag_docs",
    llm_provider_profile: str = "local-first",
    provider_registry_path: Path | None = None,
    project_root: Path | None = None,
) -> SimpleNamespace:
    root = project_root or Path(__file__).resolve().parent.parent
    return SimpleNamespace(
        vector_backend=vector_backend,
        vectordb_chroma_dir=Path(vectordb_chroma_dir),
        vectordb_collection_prefix=vectordb_collection_prefix,
        llm_provider_profile=llm_provider_profile,
        provider_registry_path=provider_registry_path or (root / "config" / "providers.yml"),
        project_root=root,
        model_routing_enabled=True,
    )


def test_normalize_query_is_unicode_safe_and_collapses_whitespace() -> None:
    left = namespace.normalize_query("  Café\u00a0\tRESET  ")
    right = namespace.normalize_query("café reset")
    assert left == right
    assert left == "café reset"


def test_build_key_shares_equivalent_normalized_queries(
    tmp_path: Path,
) -> None:
    settings = _settings(vectordb_chroma_dir=tmp_path / "chroma")
    k1 = namespace.build_llm_response_cache_key(
        "acme",
        "How to reset password?",
        settings=settings,
    )
    k2 = namespace.build_llm_response_cache_key(
        "acme",
        "  how   to\treset password?  ",
        settings=settings,
    )
    assert k1 is not None
    assert k1 == k2
    assert k1.startswith("llm_resp:acme:")
    assert ":v1:" in k1
    assert "password" not in k1
    assert "How to" not in k1


def test_build_key_isolates_tenants(tmp_path: Path) -> None:
    settings = _settings(vectordb_chroma_dir=tmp_path / "chroma")
    k1 = namespace.build_llm_response_cache_key("acme", "same", settings=settings)
    k2 = namespace.build_llm_response_cache_key("mega", "same", settings=settings)
    assert k1 is not None and k2 is not None
    assert k1 != k2
    assert k1.startswith("llm_resp:acme:")
    assert k2.startswith("llm_resp:mega:")


def test_build_key_changes_with_index_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chroma_dir = tmp_path / "chroma"
    settings = _settings(vectordb_chroma_dir=chroma_dir)

    def _identity(tenant: str, *, settings=None) -> str:
        _ = tenant, settings
        return "chroma:rag_docs_acme:g1"

    monkeypatch.setattr(namespace, "resolve_index_identity", _identity)
    k1 = namespace.build_llm_response_cache_key("acme", "q", settings=settings)

    def _identity_v2(tenant: str, *, settings=None) -> str:
        _ = tenant, settings
        return "chroma:rag_docs_acme:g2"

    monkeypatch.setattr(namespace, "resolve_index_identity", _identity_v2)
    k2 = namespace.build_llm_response_cache_key("acme", "q", settings=settings)
    assert k1 is not None and k2 is not None
    assert k1 != k2


def test_build_key_changes_with_effective_prompt_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(vectordb_chroma_dir=tmp_path / "chroma")
    k1 = namespace.build_llm_response_cache_key("acme", "q", settings=settings)

    prompts = importlib.import_module("agent.prompts")
    original = prompts.PROMPT_REGISTRY["qa"]["text"]
    monkeypatch.setitem(
        prompts.PROMPT_REGISTRY["qa"],
        "text",
        original + "\n# cache-namespace-probe",
    )
    k2 = namespace.build_llm_response_cache_key("acme", "q", settings=settings)
    assert k1 is not None and k2 is not None
    assert k1 != k2


def test_build_key_changes_with_experiment_prompt_override(
    tmp_path: Path,
) -> None:
    from datetime import datetime, timezone

    settings = _settings(vectordb_chroma_dir=tmp_path / "chroma")
    experiment = Experiment(
        id="2026-08-09-cache-ns",
        name="cache-ns",
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        created_by="tests",
        description="prompt override for cache namespace",
        prompt_overrides={"qa": "EXPERIMENT OVERRIDE {question}"},
        settings_overrides={},
        parent_experiment_id=None,
        status="running",
        tags=["cache"],
    )
    k1 = namespace.build_llm_response_cache_key("acme", "q", settings=settings)
    k2 = namespace.build_llm_response_cache_key(
        "acme",
        "q",
        settings=settings,
        experiment=experiment,
    )
    assert k1 is not None and k2 is not None
    assert k1 != k2


def test_build_key_changes_with_model_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(
        vectordb_chroma_dir=tmp_path / "chroma",
        llm_provider_profile="local-first",
    )
    k1 = namespace.build_llm_response_cache_key("acme", "q", settings=settings)

    def _model_alt(*, settings=None, experiment=None) -> str:
        _ = settings, experiment
        return "profile=external-mistral|fast=mistral:ministral-3b-latest|strong=mistral:mistral-small-latest"

    monkeypatch.setattr(namespace, "resolve_model_identity", _model_alt)
    k2 = namespace.build_llm_response_cache_key("acme", "q", settings=settings)
    assert k1 is not None and k2 is not None
    assert k1 != k2


def test_build_key_uses_legacy_generation_for_manifest_less_chroma(
    tmp_path: Path,
) -> None:
    settings = _settings(vectordb_chroma_dir=tmp_path / "chroma")
    identity = namespace.resolve_index_identity("acme", settings=settings)
    assert identity is not None
    assert identity.endswith(":g0") or ":legacy:" in identity or identity.endswith(":legacy")
    key = namespace.build_llm_response_cache_key("acme", "q", settings=settings)
    assert key is not None
    assert key.startswith("llm_resp:acme:v1:")


def test_build_key_fail_closed_for_unversioned_backend(tmp_path: Path) -> None:
    settings = _settings(
        vector_backend="qdrant",
        vectordb_chroma_dir=tmp_path / "chroma",
    )
    assert namespace.resolve_index_identity("acme", settings=settings) is None
    assert namespace.build_llm_response_cache_key("acme", "q", settings=settings) is None


def test_build_key_fail_closed_when_model_identity_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(vectordb_chroma_dir=tmp_path / "chroma")

    def _boom(*, settings=None, experiment=None) -> str:
        _ = settings, experiment
        raise namespace.CacheIdentityError("model unresolved")

    monkeypatch.setattr(namespace, "resolve_model_identity", _boom)
    assert namespace.build_llm_response_cache_key("acme", "q", settings=settings) is None


def test_build_key_does_not_embed_raw_prompt_or_paths(
    tmp_path: Path,
) -> None:
    chroma_dir = tmp_path / "secret-chroma-path"
    settings = _settings(vectordb_chroma_dir=chroma_dir)
    key = namespace.build_llm_response_cache_key(
        "acme",
        "confidential support question about invoice 42",
        settings=settings,
    )
    assert key is not None
    assert "confidential" not in key
    assert "invoice" not in key
    assert "secret-chroma-path" not in key
    assert str(chroma_dir) not in key


def test_resolve_model_identity_is_config_only(tmp_path: Path) -> None:
    settings = _settings(
        vectordb_chroma_dir=tmp_path / "chroma",
        llm_provider_profile="local-first",
    )
    identity = namespace.resolve_model_identity(settings=settings)
    assert "ollama" in identity
    assert "qwen2.5:7b" in identity
    assert "local-first" in identity


def test_staged_prompt_override_changes_prompt_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = importlib.import_module("agent.prompt_registry")
    override_path = tmp_path / "experiment_override.yaml"
    override_path.write_text(
        yaml.safe_dump(
            {
                "experiment_id": "staged-cache-ns",
                "prompt_overrides": {"qa": "STAGED PROMPT {question}"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "EXPERIMENT_OVERRIDE_PATH", override_path)

    monkeypatch.delenv("EXPERIMENT_ID", raising=False)
    baseline = namespace.resolve_prompt_identity()

    monkeypatch.setenv("EXPERIMENT_ID", "staged-cache-ns")
    staged = namespace.resolve_prompt_identity()
    assert staged != baseline
