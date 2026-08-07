"""Named index-lifecycle fault points for tests and controlled drills.

Default behavior is a pure no-op. Faults are armed only in-process by tests
(or an explicit future drill harness) via :func:`arm_fault` /
:func:`fault_armed`. There is **no** environment or settings switch here —
production paths stay inert unless a caller deliberately arms a point.

2.6a covers the inventory-write and manifest-publish commit boundaries.
2.6b adds the staged known-query validation boundary (before inventory).
2.6c adds the staged embedding-dimension validation boundary (during build).
2.6d adds the unpublished-candidate cleanup/discard boundary.
Later slices may reserve additional point names (concurrency) without
changing this module's fail-closed defaults.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Final

FaultAction = Callable[[], None]

# Durable commit boundary for trusted retention inventory write.
INVENTORY_WRITE: Final[str] = "inventory_write"
# Durable commit boundary for active-version manifest publish/switch.
MANIFEST_PUBLISH: Final[str] = "manifest_publish"
# Staged known-query validation boundary (before inventory/publish).
KNOWN_QUERY: Final[str] = "known_query"
# Staged embedding-dimension validation boundary (during candidate build).
EMBEDDINGS: Final[str] = "embeddings"
# Unpublished candidate cleanup / discard boundary.
CLEANUP: Final[str] = "cleanup"

_KNOWN_POINTS: Final[frozenset[str]] = frozenset(
    {
        INVENTORY_WRITE,
        MANIFEST_PUBLISH,
        KNOWN_QUERY,
        EMBEDDINGS,
        CLEANUP,
    }
)

_ARMED: dict[str, FaultAction] = {}


class IndexLifecycleFaultError(RuntimeError):
    """Raised by default injectors when a named lifecycle fault fires."""


def known_fault_points() -> frozenset[str]:
    """Return the set of lifecycle fault point names recognized by this module."""
    return _KNOWN_POINTS


def arm_fault(name: str, action: FaultAction | BaseException | type[BaseException]) -> None:
    """Arm a single fault point until cleared.

    ``action`` may be:
    - a zero-arg callable (may raise);
    - an exception *instance* (re-raised as a fresh instance of the same type);
    - an exception *type* (raised with a standard injected message).
    """
    if name not in _KNOWN_POINTS:
        raise ValueError(f"Unknown index lifecycle fault point: {name!r}")
    _ARMED[name] = _normalize_action(name, action)


def clear_faults(name: str | None = None) -> None:
    """Clear one armed point, or all points when ``name`` is ``None``."""
    if name is None:
        _ARMED.clear()
        return
    _ARMED.pop(name, None)


def is_armed(name: str) -> bool:
    """Return whether ``name`` currently has an armed injector."""
    return name in _ARMED


def maybe_inject(name: str) -> None:
    """Run the armed injector for ``name``, or return immediately if unarmed."""
    action = _ARMED.get(name)
    if action is None:
        return
    action()


@contextmanager
def fault_armed(
    name: str,
    action: FaultAction | BaseException | type[BaseException],
) -> Iterator[None]:
    """Temporarily arm ``name`` for the duration of the context."""
    previous = _ARMED.get(name)
    arm_fault(name, action)
    try:
        yield
    finally:
        if previous is None:
            clear_faults(name)
        else:
            _ARMED[name] = previous


def _normalize_action(
    name: str,
    action: FaultAction | BaseException | type[BaseException],
) -> FaultAction:
    if isinstance(action, type) and issubclass(action, BaseException):
        exc_type = action

        def _raise_type() -> None:
            raise exc_type(f"injected index lifecycle fault at {name}")

        return _raise_type

    if isinstance(action, BaseException):
        template = action

        def _raise_instance() -> None:
            raise type(template)(str(template))

        return _raise_instance

    if callable(action):
        return action

    raise TypeError(
        "Fault action must be a callable, BaseException instance, or BaseException type"
    )


__all__ = [
    "CLEANUP",
    "EMBEDDINGS",
    "INVENTORY_WRITE",
    "KNOWN_QUERY",
    "MANIFEST_PUBLISH",
    "IndexLifecycleFaultError",
    "arm_fault",
    "clear_faults",
    "fault_armed",
    "is_armed",
    "known_fault_points",
    "maybe_inject",
]
