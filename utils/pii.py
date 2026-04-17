"""PII detection and redaction."""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RU_RE = re.compile(
    r"(?<!\w)(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\w)"
)
_PHONE_INTL_RE = re.compile(r"(?<!\w)\+\d{1,3}[\s\-]?\d{6,14}(?!\w)")
_PASSPORT_RE = re.compile(r"\b\d{2}\s?\d{2}\s?\d{6}\b")
_INN_RE = re.compile(r"\b\d{10,12}\b")
_CARD_RE = re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b")

_PATTERNS = [
    (_EMAIL_RE, "***@***.***"),
    (_PHONE_RU_RE, "+7-***-***-**-**"),
    (_PHONE_INTL_RE, "+*-*****"),
    (_CARD_RE, "****-****-****-****"),
    (_PASSPORT_RE, "** ** ******"),
    (_INN_RE, None),
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
    result = _PASSPORT_RE.sub("** ** ******", result)
    result = _INN_RE.sub(lambda match: "*" * len(match.group(0)), result)
    return result


def contains_pii(text: str) -> bool:
    """Check if text contains PII."""
    if not text:
        return False
    for pattern, _ in _PATTERNS:
        if pattern.search(text):
            return True
    return False
