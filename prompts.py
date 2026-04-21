from __future__ import annotations

import warnings

warnings.warn(
    "Importing from 'prompts' is deprecated; use 'agent.prompts'.",
    DeprecationWarning,
    stacklevel=2,
)

from agent.prompts import *  # noqa: E402, F403
