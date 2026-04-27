"""Compatibility shim for legacy root-level vector manager imports."""
from __future__ import annotations

import sys
import warnings

from vectordb import _base_manager as _base_manager

warnings.warn(
    "Importing 'manager' is deprecated; use 'vectordb.manager' instead.",
    DeprecationWarning,
    stacklevel=2,
)

sys.modules[__name__] = _base_manager
