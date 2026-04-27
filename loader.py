"""Compatibility shim for legacy root-level document loader imports."""
from __future__ import annotations

import sys
import warnings

from ingestion import loader as _loader

warnings.warn(
    "Importing 'loader' is deprecated; use 'ingestion.loader' instead.",
    DeprecationWarning,
    stacklevel=2,
)

sys.modules[__name__] = _loader
