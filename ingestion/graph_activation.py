"""
ingestion/graph_activation.py

Activation condition for the graph-retrieval lane (GraphRAG).

Implements the gate from docs/plans/2026-06-05-graph-retrieval-activation.md:
``RAG_GRAPH_RETRIEVAL=off|on|auto`` (default ``off``).  In ``auto`` mode the
lane is considered activated only when BOTH signals hold:

    1. corpus size:   chunk count after ingestion >= RAG_GRAPH_MIN_CHUNKS;
    2. connectivity:  measured cross-doc entity share (from the Phase-1 probe,
       supplied via RAG_GRAPH_CROSSDOC_SHARE) >= RAG_GRAPH_MIN_CROSSDOC_SHARE.

Without probe data ``auto`` resolves to disabled — size alone does not prove
the graph would help (50k chunks of unrelated FAQs give the graph nothing).

The decision is evaluated and logged on every ingestion with the actual
metric values, so the moment the corpus crosses the thresholds is visible in
logs without any manual re-measurement.  Note: the graph lane itself is
Phase 2 of the plan and is not built yet; until then ``on``/satisfied-``auto``
only signal that building it is justified.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_VALID_MODES = ("off", "on", "auto")


@dataclass(frozen=True)
class GraphActivationDecision:
    """Outcome of evaluating the graph-lane activation condition."""

    activated: bool
    mode: str  # normalized RAG_GRAPH_RETRIEVAL value
    reason: str
    chunk_count: int
    min_chunks: int
    crossdoc_share: float | None  # measured probe value, None = probe not run
    min_crossdoc_share: float

    def as_log_fields(self) -> dict[str, Any]:
        return {
            "activated": self.activated,
            "mode": self.mode,
            "reason": self.reason,
            "chunk_count": self.chunk_count,
            "min_chunks": self.min_chunks,
            "crossdoc_share": self.crossdoc_share,
            "min_crossdoc_share": self.min_crossdoc_share,
        }


def resolve_graph_activation(
    chunk_count: int, settings: Any = None
) -> GraphActivationDecision:
    """Evaluate the graph-lane activation condition for the current corpus.

    Args:
        chunk_count: number of chunks produced by the current ingestion.
        settings: settings object; defaults to ``get_settings()``.

    Returns:
        GraphActivationDecision with the verdict, the deciding reason and
        the actual metric values used.
    """
    if settings is None:
        from config.settings import get_settings

        settings = get_settings()

    raw_mode = str(getattr(settings, "graph_retrieval", "off") or "off").strip().lower()
    mode = raw_mode if raw_mode in _VALID_MODES else "off"
    min_chunks = int(getattr(settings, "graph_min_chunks", 20000))
    min_share = float(getattr(settings, "graph_min_crossdoc_share", 0.15))
    share = getattr(settings, "graph_crossdoc_share", None)
    if share is not None:
        share = float(share)

    if mode == "on":
        activated, reason = True, "forced on (RAG_GRAPH_RETRIEVAL=on)"
    elif mode == "off":
        activated = False
        reason = (
            "disabled (RAG_GRAPH_RETRIEVAL=off)"
            if raw_mode in _VALID_MODES
            else f"disabled (invalid RAG_GRAPH_RETRIEVAL={raw_mode!r}, fallback off)"
        )
    elif chunk_count < min_chunks:
        activated = False
        reason = f"auto: chunk threshold not met ({chunk_count} < {min_chunks})"
    elif share is None:
        activated = False
        reason = (
            "auto: chunk threshold met but connectivity probe not run "
            "(RAG_GRAPH_CROSSDOC_SHARE unset; see scripts in the plan, Phase 1)"
        )
    elif share < min_share:
        activated = False
        reason = f"auto: cross-doc share below gate ({share:.3f} < {min_share:.3f})"
    else:
        activated = True
        reason = (
            f"auto: thresholds met (chunks {chunk_count} >= {min_chunks}, "
            f"cross-doc share {share:.3f} >= {min_share:.3f})"
        )

    return GraphActivationDecision(
        activated=activated,
        mode=mode,
        reason=reason,
        chunk_count=chunk_count,
        min_chunks=min_chunks,
        crossdoc_share=share,
        min_crossdoc_share=min_share,
    )


def log_graph_activation(chunk_count: int, settings: Any = None) -> GraphActivationDecision:
    """Evaluate the condition and log the decision with actual metrics.

    Called from the ingestion pipeline; INFO when the lane stays off,
    WARNING when the condition is satisfied (the lane itself is not built
    yet — a satisfied condition is an action signal, see the plan doc).
    """
    decision = resolve_graph_activation(chunk_count, settings=settings)
    level = logging.WARNING if decision.activated else logging.INFO
    logger.log(
        level,
        "[GraphActivation] activated=%s mode=%s chunks=%d/%d crossdoc_share=%s/%.2f — %s",
        decision.activated,
        decision.mode,
        decision.chunk_count,
        decision.min_chunks,
        "n/a" if decision.crossdoc_share is None else f"{decision.crossdoc_share:.3f}",
        decision.min_crossdoc_share,
        decision.reason,
    )
    return decision
