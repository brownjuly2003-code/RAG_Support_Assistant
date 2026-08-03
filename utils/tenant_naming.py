"""Collision-resistant physical names derived from canonical tenant IDs."""
from __future__ import annotations

import hashlib
import re

_SAFE_COMPONENT_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$"
)
_WINDOWS_RESERVED_RE = re.compile(
    r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$",
    re.IGNORECASE,
)
_HASH_HEX_LENGTH = 16
_HASH_SEPARATOR = "--"


def physical_tenant_component(tenant_id: str, *, max_length: int) -> str:
    """Return a stable safe component, hashing only lossy or truncated IDs.

    Existing safe identifiers keep their physical name. Any identifier that
    needs character replacement, boundary cleanup, or truncation receives a
    64-bit SHA-256 suffix so distinct canonical IDs do not collapse onto the
    same collection or directory name.
    """
    if max_length <= 0:
        raise ValueError("max_length must be positive")

    canonical = str(tenant_id or "default")
    if (
        len(canonical) <= max_length
        and _SAFE_COMPONENT_RE.fullmatch(canonical)
        and not _WINDOWS_RESERVED_RE.fullmatch(canonical)
    ):
        return canonical

    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:_HASH_HEX_LENGTH]
    suffix = f"{_HASH_SEPARATOR}{digest}"
    if max_length <= len(suffix):
        raise ValueError("max_length is too small for a collision-resistant tenant name")

    slug = re.sub(r"[^A-Za-z0-9._-]", "_", canonical).strip("._-") or "tenant"
    slug = slug[: max_length - len(suffix)].rstrip("._-") or "t"
    return f"{slug}{suffix}"
