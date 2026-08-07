"""5.3 — grader / top-1 / all-docs-rejected fail-closed."""

from __future__ import annotations

from agent import doc_grade as dg
from agent.graph import make_generate_node, make_grade_docs_node
from agent.state import create_initial_state
from llm.providers import LLMResponse


def test_resolve_generation_docs_no_silent_restore_after_grade() -> None:
    state = {
        "context_docs": [{"page_content": "raw"}],
        "graded_docs": [],
        "doc_grade_reason": "Kept 0/1, filtered 1, all_docs_rejected",
    }
    assert dg.resolve_generation_context_docs(state) == []

    # Before grade (no reason): may use context.
    pre = {"context_docs": [{"page_content": "raw"}], "graded_docs": []}
    assert dg.resolve_generation_context_docs(pre) == [{"page_content": "raw"}]


def test_classify_outcomes() -> None:
    assert dg.classify_grade_outcome(context_count=0, graded_count=0, grader_errors=0) == "empty_retrieval"
    assert dg.classify_grade_outcome(context_count=2, graded_count=0, grader_errors=0) == "all_rejected"
    assert dg.classify_grade_outcome(context_count=2, graded_count=0, grader_errors=2) == "grader_error"
    assert dg.classify_grade_outcome(context_count=2, graded_count=1, grader_errors=1) == "partial_grader_error"
    assert dg.classify_grade_outcome(context_count=2, graded_count=1, grader_errors=0) == "ok"


def test_all_docs_rejected_marks_not_verified(monkeypatch) -> None:
    import agent.graph as graph

    class _AllNo:
        provider_id = "mock"
        model_name = "m"
        supports_structured_output = True

        def generate_with_schema(self, messages, schema, **kwargs):
            _ = messages, kwargs
            if "grades" in (schema.get("properties") or {}):
                return LLMResponse(
                    text='{"grades":[{"index":1,"relevant":false},{"index":2,"relevant":false}]}',
                    provider=self.provider_id,
                    model=self.model_name,
                    structured_output={
                        "grades": [
                            {"index": 1, "relevant": False},
                            {"index": 2, "relevant": False},
                        ]
                    },
                )
            return LLMResponse(
                text='{"relevant": false}',
                provider=self.provider_id,
                model=self.model_name,
                structured_output={"relevant": False},
            )

    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda *a, **k: None)

    node = make_grade_docs_node(_AllNo())
    state = create_initial_state(question="q", trace_id="t")
    state["context_docs"] = [
        {"page_content": "a", "metadata": {}},
        {"page_content": "b", "metadata": {}},
    ]
    out = node(state)
    assert out["graded_docs"] == []
    assert out.get("doc_grade_outcome") == "all_rejected"
    assert "all_docs_rejected" in (out.get("doc_grade_reason") or "")
    assert out.get("knowledge_gap") is True
    assert out.get("grounding_status") == "not_verified"


def test_grader_error_rejects_doc_not_accepts(monkeypatch) -> None:
    import agent.graph as graph

    class _Boom:
        provider_id = "mock"
        model_name = "m"
        supports_structured_output = False

        def invoke(self, prompt: str) -> str:
            raise RuntimeError("grader down")

    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda *a, **k: None)
    # Force per-doc path (single doc, no batch).
    node = make_grade_docs_node(_Boom())
    state = create_initial_state(question="q", trace_id="t")
    state["context_docs"] = [{"page_content": "only doc", "metadata": {}}]
    out = node(state)
    assert out["graded_docs"] == []
    assert out.get("doc_grade_outcome") == "grader_error"
    assert out.get("knowledge_gap") is True
    assert out.get("grounding_status") == "not_verified"


def test_generate_does_not_use_raw_context_after_all_rejected(monkeypatch) -> None:
    import agent.graph as graph

    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda *a, **k: None)

    captured_prompts: list[str] = []

    class _Gen:
        def invoke(self, prompt: str) -> str:
            captured_prompts.append(prompt)
            return "answer without restored context"

    node = make_generate_node(_Gen(), _Gen())
    state = create_initial_state(question="How to return?", trace_id="t")
    state["context_docs"] = [
        {"page_content": "SECRET_SHOULD_NOT_APPEAR_IN_PROMPT", "metadata": {}},
    ]
    state["graded_docs"] = []
    state["doc_grade_reason"] = "Kept 0/1, filtered 1, all_docs_rejected"
    state["doc_grade_outcome"] = "all_rejected"
    state["complexity"] = "complex"

    out = node(state)
    assert out.get("answer")
    joined = "\n".join(captured_prompts)
    assert "SECRET_SHOULD_NOT_APPEAR_IN_PROMPT" not in joined
