"""Compatibility shim for legacy root-level SQLite trace imports."""
from __future__ import annotations

import sys
import warnings

from tracing import _base_trace as _base_trace

warnings.warn(
    "Importing 'sqlite_trace' is deprecated; use 'tracing.sqlite_trace' instead.",
    DeprecationWarning,
    stacklevel=2,
)

sys.modules[__name__] = _base_trace
