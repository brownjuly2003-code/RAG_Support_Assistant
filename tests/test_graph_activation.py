"""Activation condition for the graph-retrieval lane (GraphRAG).

Implements the gate from docs/plans/2026-06-05-graph-retrieval-activation.md:
RAG_GRAPH_RETRIEVAL=off|on|auto, default off; "auto" activates only when the
chunk threshold AND the connectivity gate (Phase-1 probe value) both hold.
The lane itself is Phase 2 and not built yet — the condition is the contract.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from config.settings import Settings
from ingestion.graph_activation import log_graph_activation, resolve_graph_activation


def _settings(**overrides):
    base = {
        "graph_retrieval": "off",
        "graph_min_chunks": 20000,
        "graph_min_crossdoc_share": 0.15,
        "graph_crossdoc_share": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_graph_settings_defaults(monkeypatch) -> None:
    # Pin the plan's contract: default off, thresholds 20000 / 0.15,
    # probe value unset.
    for var in (
        "RAG_GRAPH_RETRIEVAL",
        "RAG_GRAPH_MIN_CHUNKS",
        "RAG_GRAPH_MIN_CROSSDOC_SHARE",
        "RAG_GRAPH_CROSSDOC_SHARE",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings()

    assert settings.graph_retrieval == "off"
    assert settings.graph_min_chunks == 20000
    assert settings.graph_min_crossdoc_share == 0.15
    assert settings.graph_crossdoc_share is None


def test_graph_settings_read_env(monkeypatch) -> None:
    monkeypatch.setenv("RAG_GRAPH_RETRIEVAL", "AUTO")
    monkeypatch.setenv("RAG_GRAPH_MIN_CHUNKS", "5000")
    monkeypatch.setenv("RAG_GRAPH_MIN_CROSSDOC_SHARE", "0.2")
    monkeypatch.setenv("RAG_GRAPH_CROSSDOC_SHARE", "0.31")

    settings = Settings()

    assert settings.graph_retrieval == "auto"
    assert settings.graph_min_chunks == 5000
    assert settings.graph_min_crossdoc_share == 0.2
    assert settings.graph_crossdoc_share == 0.31


def test_off_by_default() -> None:
    decision = resolve_graph_activation(10**6, settings=_settings())
    assert decision.activated is False
    assert decision.mode == "off"


def test_invalid_mode_falls_back_to_off() -> None:
    decision = resolve_graph_activation(10**6, settings=_settings(graph_retrieval="bogus"))
    assert decision.activated is False
    assert decision.mode == "off"
    assert "invalid" in decision.reason


def test_forced_on_ignores_thresholds() -> None:
    decision = resolve_graph_activation(1, settings=_settings(graph_retrieval="on"))
    assert decision.activated is True
    assert decision.mode == "on"


def test_auto_below_chunk_threshold() -> None:
    # Current corpus scale (~5.6k chunks) must NOT activate the lane.
    decision = resolve_graph_activation(
        5589, settings=_settings(graph_retrieval="auto", graph_crossdoc_share=0.9)
    )
    assert decision.activated is False
    assert "chunk threshold not met" in decision.reason


def test_auto_without_probe_stays_off() -> None:
    # Size alone is not enough: no connectivity probe -> no activation.
    decision = resolve_graph_activation(50000, settings=_settings(graph_retrieval="auto"))
    assert decision.activated is False
    assert "probe not run" in decision.reason


def test_auto_low_connectivity_stays_off() -> None:
    decision = resolve_graph_activation(
        50000, settings=_settings(graph_retrieval="auto", graph_crossdoc_share=0.05)
    )
    assert decision.activated is False
    assert "below gate" in decision.reason


def test_auto_both_gates_met_activates() -> None:
    decision = resolve_graph_activation(
        20000, settings=_settings(graph_retrieval="auto", graph_crossdoc_share=0.15)
    )
    assert decision.activated is True
    assert decision.chunk_count == 20000
    assert decision.crossdoc_share == 0.15


def test_log_emits_actual_metrics(caplog) -> None:
    # The plan requires the decision to be logged at ingestion with the
    # actual metric values.
    with caplog.at_level(logging.INFO, logger="ingestion.graph_activation"):
        decision = log_graph_activation(
            5589, settings=_settings(graph_retrieval="auto", graph_crossdoc_share=0.31)
        )
    assert decision.activated is False
    record = next(r for r in caplog.records if "[GraphActivation]" in r.getMessage())
    message = record.getMessage()
    assert "chunks=5589/20000" in message
    assert "0.310" in message
    assert record.levelno == logging.INFO


def test_log_warns_when_condition_met(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="ingestion.graph_activation"):
        decision = log_graph_activation(
            25000, settings=_settings(graph_retrieval="auto", graph_crossdoc_share=0.4)
        )
    assert decision.activated is True
    record = next(r for r in caplog.records if "[GraphActivation]" in r.getMessage())
    assert record.levelno == logging.WARNING
