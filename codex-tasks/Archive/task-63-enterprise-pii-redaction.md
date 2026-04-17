# Task 63 — COMP-2: PII redaction в логах и traces

## Goal
Автоматическое обнаружение и маскирование PII (email, телефон, паспорт, ИНН)
в логах, traces и audit records.

## Files to create
- `utils/__init__.py`
- `utils/pii.py` — PII detection + redaction

## Files to change
- `config/logging_config.py` — добавить PII filter
- `tracing/sqlite_trace.py` — redact state_json

---

## 1. utils/__init__.py

```python
"""Utility modules."""
```

---

## 2. utils/pii.py

```python
"""PII detection and redaction."""
from __future__ import annotations

import re

# Patterns
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
_PHONE_RU_RE = re.compile(r'(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')
_PHONE_INTL_RE = re.compile(r'\+\d{1,3}[\s\-]?\d{6,14}')
_PASSPORT_RE = re.compile(r'\b\d{2}\s?\d{2}\s?\d{6}\b')  # Russian passport: XX XX XXXXXX
_INN_RE = re.compile(r'\b\d{10,12}\b')  # INN: 10 or 12 digits
_CARD_RE = re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b')  # Card number

_PATTERNS = [
    (_EMAIL_RE, "***@***.***"),
    (_PHONE_RU_RE, "+7-***-***-**-**"),
    (_PHONE_INTL_RE, "+*-*****"),
    (_CARD_RE, "****-****-****-****"),
    (_PASSPORT_RE, "** ** ******"),
    # INN intentionally last — broad pattern, only redact if 10 or 12 digits exactly
]


def redact_pii(text: str) -> str:
    """Replace PII patterns with masked versions."""
    if not text:
        return text
    result = text
    result = _EMAIL_RE.sub("***@***.***", result)
    result = _PHONE_RU_RE.sub("+7-***-***-**-**", result)
    result = _PHONE_INTL_RE.sub("+*-*****", result)
    result = _CARD_RE.sub("****-****-****-****", result)
    # Passport — only if looks like XX XX XXXXXX
    result = _PASSPORT_RE.sub("** ** ******", result)
    return result


def contains_pii(text: str) -> bool:
    """Check if text contains PII."""
    if not text:
        return False
    for pattern, _ in _PATTERNS:
        if pattern.search(text):
            return True
    return False
```

---

## 3. config/logging_config.py — PII filter

Добавить logging Filter:

```python
import logging
from utils.pii import redact_pii


class PIIRedactionFilter(logging.Filter):
    """Redact PII from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_pii(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact_pii(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(redact_pii(str(a)) if isinstance(a, str) else a for a in record.args)
        return True
```

В `setup_logging()` добавить filter на root logger:
```python
    pii_filter = PIIRedactionFilter()
    for handler in logging.root.handlers:
        handler.addFilter(pii_filter)
```

---

## 4. tracing/sqlite_trace.py — redact state_json

В `log_step()`, перед записью state_json:

```python
from utils.pii import redact_pii

# Redact PII in state snapshot
state_str = _json.dumps(safe_state, ensure_ascii=False)
state_str = redact_pii(state_str)
```

---

## 5. tests/test_pii.py (новый)

```python
"""PII redaction tests."""
from utils.pii import redact_pii, contains_pii


def test_redact_email():
    assert "***@***.***" in redact_pii("Contact user@example.com for details")


def test_redact_phone():
    assert "+7-***" in redact_pii("Звоните +7 (999) 123-45-67")


def test_redact_card():
    assert "****-****" in redact_pii("Карта 1234 5678 9012 3456")


def test_no_pii():
    text = "Обычный текст без персональных данных"
    assert redact_pii(text) == text


def test_contains_pii():
    assert contains_pii("email: test@test.com")
    assert not contains_pii("just regular text")
```

---

## CONSTRAINTS
- Создать `utils/pii.py`, обновить logging и tracing
- PII redaction не должна ломать non-PII текст
- Performance: regex на каждый лог — acceptably fast
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `redact_pii("user@mail.com")` → `***@***.***`
- [ ] `redact_pii("+7 999 123-45-67")` → `+7-***-***-**-**`
- [ ] Логи автоматически redact-ят PII через filter
- [ ] trace state_json redacted
- [ ] `pytest tests/ -v` — проходит
