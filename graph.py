# ruff: noqa: E402
from __future__ import annotations

import warnings

warnings.warn(
    "Importing from 'graph' is deprecated; use 'agent.graph'.",
    DeprecationWarning,
    stacklevel=2,
)

from agent.graph import *  # noqa: F403
