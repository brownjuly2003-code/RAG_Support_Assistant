"""Document categorization helpers for ingestion."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections.abc import Iterable, Sequence

from config.settings import get_settings

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES = [
    {"name": "returns", "description": "Returns, refunds, cancellations"},
    {"name": "shipping", "description": "Delivery, shipping, pickup"},
    {"name": "account", "description": "Account management, login, password"},
    {"name": "payment", "description": "Payments, billing, invoices"},
    {"name": "product", "description": "Product info, specs, availability"},
]

CLASSIFY_PROMPT = """Classify the document below into one or more of these
categories. Return ONLY a JSON list of category names.
If none apply, return ["uncategorized"].

Categories:
{categories}

Document:
{doc_preview}

Classification (JSON list):"""


def _strip_yaml_scalar(value: str) -> str:
    result = value.strip()
    if not result:
        return ""
    if result[0] in {"'", '"'} and result[-1:] == result[0]:
        return result[1:-1]
    return result


def _parse_simple_yaml(text: str) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    current_section: str | None = None
    current_items: list[dict[str, str]] = []
    current_item: dict[str, str] | None = None

    def flush_item() -> None:
        nonlocal current_item
        if current_item:
            current_items.append(current_item)
            current_item = None

    def flush_section() -> None:
        nonlocal current_section, current_items
        if current_section is not None:
            flush_item()
            result[current_section] = list(current_items)
            current_items = []

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if indent == 0 and stripped.endswith(":"):
            flush_section()
            current_section = stripped[:-1].strip()
            continue
        if current_section is None:
            continue
        if stripped.startswith("- "):
            flush_item()
            current_item = {}
            stripped = stripped[2:].strip()
        if current_item is None:
            current_item = {}
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        current_item[key.strip()] = _strip_yaml_scalar(value)

    flush_section()
    return result


def _normalize_categories(raw_categories: Iterable[dict[str, Any]] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in raw_categories or ():
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        normalized.append(
            {
                "name": name,
                "description": str(item.get("description") or "").strip(),
            }
        )
    return normalized or list(DEFAULT_CATEGORIES)


def load_categories(
    tenant_id: str = "default",
    config_path: str | Path | None = None,
) -> list[dict[str, str]]:
    path = Path(config_path or get_settings().categories_config_path)
    if not path.exists():
        return list(DEFAULT_CATEGORIES)

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read categories config %s: %s", path, exc)
        return list(DEFAULT_CATEGORIES)

    parsed: dict[str, Any]
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(raw_text) or {}
        parsed = loaded if isinstance(loaded, dict) else {}
    except Exception:
        parsed = _parse_simple_yaml(raw_text)

    selected = parsed.get(tenant_id) or parsed.get("default")
    return _normalize_categories(selected)


def _build_prompt(categories: Sequence[dict[str, str]], preview: str) -> str:
    categories_text = "\n".join(
        f"- {item['name']}: {item.get('description', '')}".rstrip()
        for item in categories
    )
    return CLASSIFY_PROMPT.format(categories=categories_text, doc_preview=preview[:3000])


def _invoke_llm(llm: Any, prompt: str) -> str:
    if hasattr(llm, "invoke"):
        response = llm.invoke(prompt)
    elif callable(llm):
        response = llm(prompt)
    else:
        raise TypeError("LLM object does not support invoke()")
    if hasattr(response, "content"):
        return str(response.content)
    return str(response)


def _get_fast_llm() -> Any | None:
    try:
        from agent.graph import LocalOllamaLLM

        settings = get_settings()
        return LocalOllamaLLM(model_name=settings.ingestion_categorizer_model)
    except Exception as exc:
        logger.warning("Fast categorizer model unavailable: %s", exc)
        return None


def classify_document(
    full_text: str,
    categories: Sequence[dict[str, str]],
    llm: Any | None = None,
) -> list[str]:
    preview = str(full_text or "").strip()
    if not preview:
        return ["uncategorized"]

    llm = llm or _get_fast_llm()
    if llm is None:
        return ["uncategorized"]

    try:
        raw = _invoke_llm(llm, _build_prompt(categories, preview))
        payload = json.loads(raw)
    except Exception as exc:
        logger.warning("Categorizer skipped document: %s", exc)
        return ["uncategorized"]

    if isinstance(payload, str):
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("categories") or payload.get("labels") or []
    else:
        items = []

    valid = {item["name"] for item in categories}
    assigned = [
        str(item).strip()
        for item in items
        if str(item).strip() in valid
    ]
    return assigned or ["uncategorized"]


def _doc_metadata(doc: Any) -> dict[str, Any]:
    if isinstance(doc, dict):
        metadata = doc.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            doc["metadata"] = metadata
        return metadata
    metadata = getattr(doc, "metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        setattr(doc, "metadata", metadata)
    return metadata


def _doc_text(doc: Any) -> str:
    if isinstance(doc, dict):
        return str(doc.get("page_content", "") or "")
    return str(getattr(doc, "page_content", "") or "")


def _doc_source(doc: Any, index: int) -> str:
    metadata = _doc_metadata(doc)
    source = (
        metadata.get("source")
        or metadata.get("file_name")
        or metadata.get("file_path")
        or f"document-{index}"
    )
    return Path(str(source)).name


def annotate_documents_with_categories(
    docs: Sequence[Any],
    tenant_id: str = "default",
    llm: Any | None = None,
) -> dict[str, list[str]]:
    categories = load_categories(tenant_id)
    grouped: dict[str, list[Any]] = defaultdict(list)

    for index, doc in enumerate(docs):
        grouped[_doc_source(doc, index)].append(doc)

    assigned_by_source: dict[str, list[str]] = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for source, grouped_docs in grouped.items():
        joined_text = "\n\n".join(_doc_text(doc) for doc in grouped_docs)
        assigned = classify_document(joined_text, categories, llm=llm)
        assigned_by_source[source] = assigned
        for doc in grouped_docs:
            metadata = _doc_metadata(doc)
            metadata["categories"] = list(assigned)
            metadata["primary_category"] = assigned[0]
            metadata.setdefault("doc_id", source)
            metadata.setdefault("title", str(metadata.get("source") or source))
            metadata.setdefault("last_updated", now_iso)

    return assigned_by_source
