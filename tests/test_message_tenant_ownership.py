"""TEN-01 step 2: DB-level Message/Session composite tenant ownership.

Covers ORM metadata, migration 018 upgrade/downgrade contracts, and the
shared ask-message write path. Live Postgres upgrade is intentionally out of
scope; migration order is verified via a focused fake Alembic ``op``.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from db.models import Message, Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = PROJECT_ROOT / "alembic" / "versions" / "018_message_tenant_ownership.py"


def _load_migration() -> ModuleType:
    assert MIGRATION_PATH.is_file(), f"missing migration: {MIGRATION_PATH}"
    spec = importlib.util.spec_from_file_location(
        "migration_018_message_tenant_ownership",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_message_has_required_tenant_id_column() -> None:
    col = Message.__table__.c.tenant_id
    assert col is not None
    assert col.nullable is False
    assert col.server_default is None


def test_session_has_named_composite_unique_for_fk_target() -> None:
    uniques = [
        c
        for c in Session.__table__.constraints
        if isinstance(c, UniqueConstraint)
    ]
    matching = [
        c
        for c in uniques
        if {col.name for col in c.columns} == {"id", "tenant_id"}
    ]
    assert matching, "Session must expose UniqueConstraint(id, tenant_id) for composite FK"
    assert matching[0].name, "composite unique must be named/identifiable"
    assert matching[0].name == "uq_sessions_id_tenant_id"


def test_message_composite_fk_to_session_with_cascade() -> None:
    fks = [
        c
        for c in Message.__table__.constraints
        if isinstance(c, ForeignKeyConstraint)
    ]
    assert len(fks) == 1, f"expected exactly one FK on messages, got {fks!r}"
    fk = fks[0]
    local_cols = tuple(col.name for col in fk.columns)
    remote_cols = tuple(elem.column.name for elem in fk.elements)
    remote_table = fk.elements[0].column.table.name

    assert local_cols == ("session_id", "tenant_id")
    assert remote_table == "sessions"
    assert remote_cols == ("id", "tenant_id")
    assert fk.ondelete == "CASCADE"
    assert fk.name, "composite FK must be named"

    # No independent single-column session_id -> sessions.id FK remains.
    single_session_fks = [
        c
        for c in fks
        if tuple(col.name for col in c.columns) == ("session_id",)
    ]
    assert single_session_fks == []

    # Column-level ForeignKey objects must also not keep the legacy single FK.
    session_id_col = Message.__table__.c.session_id
    for foreign in session_id_col.foreign_keys:
        target = f"{foreign.column.table.name}.{foreign.column.name}"
        assert target != "sessions.id" or "tenant_id" in {
            col.name for col in foreign.constraint.columns
        }


def test_migration_018_revision_chain() -> None:
    module = _load_migration()
    assert module.revision == "018"
    assert module.down_revision == "017"


def test_migration_018_upgrade_ordering_and_guards() -> None:
    module = _load_migration()
    source = inspect.getsource(module.upgrade)

    # Structural order invariants in source (nullable -> backfill -> NOT NULL -> constraints).
    markers = [
        "add_column",
        "nullable=True",
        "UPDATE messages",
        "sessions.tenant_id",
        "tenant_id IS NULL",
        "alter_column",
        "nullable=False",
        "uq_sessions_id_tenant_id",
        "messages_session_id_fkey",
        "fk_messages_session_tenant",
        "ix_messages_tenant_id",
    ]
    positions = [source.find(marker) for marker in markers]
    assert all(p >= 0 for p in positions), (
        "upgrade() missing required steps: "
        + ", ".join(m for m, p in zip(markers, positions, strict=True) if p < 0)
    )
    assert positions == sorted(positions), "upgrade() step order is incorrect"

    # No silent server default assignment for Message.tenant_id.
    assert "server_default" not in source

    # Execute upgrade against a recording fake op to confirm call sequence.
    calls: list[tuple[Any, ...]] = []
    unowned_count = {"value": 0}

    class _FakeResult:
        def scalar(self) -> int:
            return unowned_count["value"]

    class _FakeBind:
        def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
            calls.append(("execute", str(statement)))
            return _FakeResult()

    class _FakeOp:
        def add_column(self, table_name: str, column: Any) -> None:
            calls.append(("add_column", table_name, column.name, column.nullable))

        def execute(self, sql: Any) -> None:
            calls.append(("op_execute", str(sql)))

        def get_bind(self) -> _FakeBind:
            return _FakeBind()

        def alter_column(self, table_name: str, column_name: str, **kwargs: Any) -> None:
            calls.append(("alter_column", table_name, column_name, kwargs.get("nullable")))

        def create_unique_constraint(
            self, constraint_name: str, table_name: str, columns: list[str], **kwargs: Any
        ) -> None:
            calls.append(("create_unique_constraint", constraint_name, table_name, list(columns)))

        def drop_constraint(
            self, constraint_name: str, table_name: str, **kwargs: Any
        ) -> None:
            calls.append(("drop_constraint", constraint_name, table_name, kwargs.get("type_")))

        def create_foreign_key(
            self,
            constraint_name: str,
            source_table: str,
            referent_table: str,
            local_cols: list[str],
            remote_cols: list[str],
            **kwargs: Any,
        ) -> None:
            calls.append(
                (
                    "create_foreign_key",
                    constraint_name,
                    source_table,
                    referent_table,
                    list(local_cols),
                    list(remote_cols),
                    kwargs.get("ondelete"),
                )
            )

        def create_index(
            self, index_name: str, table_name: str, columns: list[str], **kwargs: Any
        ) -> None:
            calls.append(("create_index", index_name, table_name, list(columns)))

    original_op = module.op
    module.op = _FakeOp()  # type: ignore[assignment]
    try:
        module.upgrade()
    finally:
        module.op = original_op

    op_kinds = [c[0] for c in calls]
    assert op_kinds[0] == "add_column"
    assert calls[0][1] == "messages"
    assert calls[0][2] == "tenant_id"
    assert calls[0][3] is True

    assert "op_execute" in op_kinds
    backfill_idx = op_kinds.index("op_execute")
    guard_idx = op_kinds.index("execute")
    alter_idx = op_kinds.index("alter_column")
    unique_idx = op_kinds.index("create_unique_constraint")
    drop_fk_idx = op_kinds.index("drop_constraint")
    create_fk_idx = op_kinds.index("create_foreign_key")
    index_idx = op_kinds.index("create_index")

    assert backfill_idx < guard_idx < alter_idx < unique_idx
    assert unique_idx < drop_fk_idx < create_fk_idx
    assert create_fk_idx < index_idx or unique_idx < index_idx

    assert calls[alter_idx] == ("alter_column", "messages", "tenant_id", False)
    assert calls[unique_idx][1] == "uq_sessions_id_tenant_id"
    assert calls[drop_fk_idx][1] == "messages_session_id_fkey"
    assert calls[create_fk_idx][1] == "fk_messages_session_tenant"
    assert calls[create_fk_idx][4] == ["session_id", "tenant_id"]
    assert calls[create_fk_idx][5] == ["id", "tenant_id"]
    assert calls[create_fk_idx][6] == "CASCADE"
    assert calls[index_idx][1] == "ix_messages_tenant_id"

    # Guard must fail when unowned rows remain.
    unowned_count["value"] = 2
    module.op = _FakeOp()  # type: ignore[assignment]
    try:
        with pytest.raises((RuntimeError, ValueError)) as exc_info:
            module.upgrade()
        assert "tenant_id" in str(exc_info.value).lower() or "unowned" in str(exc_info.value).lower()
    finally:
        module.op = original_op


def test_migration_018_downgrade_dependency_safe_order() -> None:
    module = _load_migration()
    source = inspect.getsource(module.downgrade)

    markers = [
        "fk_messages_session_tenant",
        "ix_messages_tenant_id",
        "uq_sessions_id_tenant_id",
        "messages_session_id_fkey",
        "drop_column",
    ]
    positions = [source.find(marker) for marker in markers]
    assert all(p >= 0 for p in positions), (
        "downgrade() missing required steps: "
        + ", ".join(m for m, p in zip(markers, positions, strict=True) if p < 0)
    )
    # Composite FK and index must go before column drop; original single FK restored.
    assert positions[0] < positions[4]
    assert positions[1] < positions[4]
    assert positions[2] < positions[4]
    assert "messages_session_id_fkey" in source
    assert positions[3] < positions[4]

    calls: list[tuple[Any, ...]] = []

    class _FakeOp:
        def drop_constraint(
            self, constraint_name: str, table_name: str, **kwargs: Any
        ) -> None:
            calls.append(("drop_constraint", constraint_name, table_name))

        def drop_index(self, index_name: str, **kwargs: Any) -> None:
            calls.append(("drop_index", index_name, kwargs.get("table_name")))

        def create_foreign_key(
            self,
            constraint_name: str,
            source_table: str,
            referent_table: str,
            local_cols: list[str],
            remote_cols: list[str],
            **kwargs: Any,
        ) -> None:
            calls.append(
                (
                    "create_foreign_key",
                    constraint_name,
                    source_table,
                    referent_table,
                    list(local_cols),
                    list(remote_cols),
                    kwargs.get("ondelete"),
                )
            )

        def drop_column(self, table_name: str, column_name: str) -> None:
            calls.append(("drop_column", table_name, column_name))

    original_op = module.op
    module.op = _FakeOp()  # type: ignore[assignment]
    try:
        module.downgrade()
    finally:
        module.op = original_op

    # Dependency-safe: drop composite FK before unique/column; restore single FK; drop column last.
    names = [(c[0], c[1] if len(c) > 1 else None) for c in calls]
    drop_comp_fk = next(i for i, c in enumerate(calls) if c[0] == "drop_constraint" and c[1] == "fk_messages_session_tenant")
    drop_unique = next(i for i, c in enumerate(calls) if c[0] == "drop_constraint" and c[1] == "uq_sessions_id_tenant_id")
    restore_fk = next(i for i, c in enumerate(calls) if c[0] == "create_foreign_key" and c[1] == "messages_session_id_fkey")
    drop_col = next(i for i, c in enumerate(calls) if c[0] == "drop_column")
    drop_idx = next(i for i, c in enumerate(calls) if c[0] == "drop_index")

    assert drop_comp_fk < drop_unique
    assert drop_comp_fk < drop_col
    assert drop_idx < drop_col
    assert restore_fk < drop_col or restore_fk > drop_comp_fk
    assert calls[restore_fk][4] == ["session_id"]
    assert calls[restore_fk][5] == ["id"]
    assert calls[restore_fk][6] == "CASCADE"
    assert calls[drop_col] == ("drop_column", "messages", "tenant_id")
    assert names  # used above; keep lint quiet for intentional structure


def test_persist_ask_messages_sets_tenant_id_on_both_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared write helper must stamp authenticated tenant on user+assistant rows."""
    conversation = importlib.import_module("api.routers.conversation")
    api_app = importlib.import_module("api.app")

    session_uuid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    tenant = "tenant-owned-a"
    added: list[Any] = []

    class _FakeResult:
        def scalar_one_or_none(self) -> uuid.UUID:
            return session_uuid

    class _FakeDb:
        async def __aenter__(self) -> "_FakeDb":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def execute(self, stmt: Any) -> _FakeResult:
            return _FakeResult()

        def add(self, obj: Any) -> None:
            added.append(obj)

        async def commit(self) -> None:
            return None

    monkeypatch.setattr("db.engine.async_session", lambda: _FakeDb())
    monkeypatch.setattr(
        conversation,
        "_app_module",
        lambda: SimpleNamespace(
            _db_retry_after=0.0,
            get_settings=lambda: SimpleNamespace(db_persist_timeout_sec=2.0),
        ),
    )
    # Keep production cooldown attribute clean for other tests.
    api_app._db_retry_after = 0.0

    asyncio.run(
        conversation._persist_ask_messages(
            session_id=str(session_uuid),
            tenant_id=tenant,
            question="user-q",
            answer="assistant-a",
            path="test",
        )
    )

    assert len(added) == 2
    roles = {msg.role for msg in added}
    assert roles == {"user", "assistant"}
    for msg in added:
        assert isinstance(msg, Message)
        assert msg.tenant_id == tenant
        assert msg.session_id == session_uuid
