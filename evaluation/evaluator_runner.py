from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy import JSON, bindparam, text

from db import engine as _db_engine
from evaluation.online_evaluators import (
    evaluate_answer_length_anomaly,
    evaluate_citation_coverage,
    evaluate_language_mismatch,
    evaluate_pii_leak_suspicion,
    evaluate_refusal_detected,
    evaluate_retrieval_hit_rate,
    evaluate_tool_use_efficiency,
)
from monitoring.prometheus import record_online_evaluator_error, record_online_evaluator_run


ONLINE_EVALUATORS = {
    "citation_coverage": evaluate_citation_coverage,
    "answer_length_anomaly": lambda state: evaluate_answer_length_anomaly(
        state,
        mean=float(state.get("answer_length_mean") or len(str(state.get("answer") or "").split())),
        std=float(state.get("answer_length_std") or 1.0),
    ),
    "retrieval_hit_rate": evaluate_retrieval_hit_rate,
    "tool_use_efficiency": evaluate_tool_use_efficiency,
    "refusal_detected": evaluate_refusal_detected,
    "pii_leak_suspicion": evaluate_pii_leak_suspicion,
    "language_mismatch": evaluate_language_mismatch,
}

_INSERT_TRACE_EVALUATION = text(
    """
    INSERT INTO trace_evaluations (
        trace_id,
        evaluator_name,
        score,
        verdict,
        metadata
    )
    VALUES (
        :trace_id,
        :evaluator_name,
        :score,
        :verdict,
        :metadata
    )
    """
).bindparams(bindparam("metadata", type_=JSON()))

_UPSERT_TRACE_STUB = text(
    """
    INSERT INTO traces (id, started_at, finished_at, final_route, final_quality, final_relevance)
    VALUES (:trace_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, NULL, NULL)
    ON CONFLICT (id) DO NOTHING
    """
)


def run_online_evaluators(
    trace_state: dict[str, Any],
    *,
    timeout_ms: int = 500,
) -> dict[str, dict[str, Any]]:
    started_at = time.perf_counter()
    results: dict[str, dict[str, Any]] = {}

    for evaluator_name, evaluator in ONLINE_EVALUATORS.items():
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        if elapsed_ms > timeout_ms:
            result = {"score": 0.0, "verdict": "timeout", "metadata": {}}
            results[evaluator_name] = result
            record_online_evaluator_run(evaluator_name, "timeout", 0.0)
            continue

        try:
            payload = evaluator(trace_state)
        except Exception as exc:
            result = {
                "score": 0.0,
                "verdict": "error",
                "metadata": {"error": str(exc)},
            }
            record_online_evaluator_error(evaluator_name)
        else:
            metadata = payload.get("metadata")
            result = {
                "score": float(payload.get("score") or 0.0),
                "verdict": str(payload.get("verdict") or "unknown"),
                "metadata": metadata if isinstance(metadata, dict) else {},
            }

        results[evaluator_name] = result
        record_online_evaluator_run(
            evaluator_name,
            str(result["verdict"]),
            float(result["score"]),
        )

    return results


async def persist_online_evaluations(
    trace_id: str,
    results: dict[str, dict[str, Any]],
    session_factory: Any = None,
) -> None:
    _factory = _db_engine.async_session if session_factory is None else session_factory

    # Bug 2 deeper fix: when using the default global async_session we open a
    # single engine connection, upsert a stub trace row, and then issue all
    # evaluator INSERTs sequentially inside the same transaction.  This avoids
    # the asyncpg "another operation is in progress" race that happens when
    # multiple concurrent checkouts hit the same connection from the pool.
    # Bug 4 fix: the stub is inserted in the same transaction as the
    # trace_evaluations rows, so the FK constraint is guaranteed to hold.
    if _factory is _db_engine.async_session:
        async with _db_engine.engine.begin() as conn:
            await conn.execute(_UPSERT_TRACE_STUB, {"trace_id": trace_id})
            for evaluator_name, payload in results.items():
                metadata = payload.get("metadata")
                await conn.execute(
                    _INSERT_TRACE_EVALUATION,
                    {
                        "trace_id": trace_id,
                        "evaluator_name": evaluator_name,
                        "score": float(payload.get("score") or 0.0),
                        "verdict": str(payload.get("verdict") or "unknown"),
                        "metadata": metadata if isinstance(metadata, dict) else {},
                    },
                )
        return

    # Custom session_factory path (unit tests): keep the concurrent per-evaluator
    # session behaviour that existing tests depend on.
    async def _persist_one(evaluator_name: str, payload: dict[str, Any]) -> None:
        async with _factory() as session:
            metadata = payload.get("metadata")
            await session.execute(
                _INSERT_TRACE_EVALUATION,
                {
                    "trace_id": trace_id,
                    "evaluator_name": evaluator_name,
                    "score": float(payload.get("score") or 0.0),
                    "verdict": str(payload.get("verdict") or "unknown"),
                    "metadata": metadata if isinstance(metadata, dict) else {},
                },
            )
            await session.commit()

    await asyncio.gather(
        *[
            _persist_one(evaluator_name, payload)
            for evaluator_name, payload in results.items()
        ]
    )
