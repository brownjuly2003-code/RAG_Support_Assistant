from __future__ import annotations

import warnings

warnings.warn(
    "Importing from 'state' is deprecated; use 'agent.state'.",
    DeprecationWarning,
    stacklevel=2,
)

from agent.state import *  # noqa: E402, F403
