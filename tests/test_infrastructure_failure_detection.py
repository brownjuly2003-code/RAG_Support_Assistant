from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("", False),
        ("Срок гарантии 12 месяцев", False),
        ("[provider_unavailable] Adapter circuit breaker open.", True),
        ("[PROVIDER_UNAVAILABLE] anything", True),
        ("[model_mismatch] Requested 'Claude Sonnet 4.6' but UI shows 'Sonar'.", True),
        ("[Model_Mismatch] uppercase pattern", True),
        ("Some text [model_mismatch] embedded inside.", True),
        (None, False),
    ],
)
def test_is_infrastructure_failure_classifies_external_provider_errors(
    answer: str | None, expected: bool
) -> None:
    from scripts.regression_eval import _is_infrastructure_failure

    assert _is_infrastructure_failure(answer or "") is expected
