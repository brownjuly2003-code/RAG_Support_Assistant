"""Transparent pgcrypto helpers for SQLAlchemy models."""
from __future__ import annotations

from typing import Any

from sqlalchemy import String, Text, bindparam, cast, func, literal_column
from sqlalchemy.sql.elements import ClauseElement, ColumnElement
from sqlalchemy.types import LargeBinary, TypeDecorator

from config.settings import get_settings

_PGCRYPTO_OPTIONS = "cipher-algo=aes256,compress-algo=0"


def _get_encryption_key() -> str:
    secret = getattr(get_settings(), "db_encryption_key", None)
    if secret is None:
        raise RuntimeError("DB encryption key is not configured")
    if hasattr(secret, "get_secret_value"):
        key = secret.get_secret_value()
    else:
        key = str(secret)
    if not key:
        raise RuntimeError("DB encryption key is empty")
    return key


def encrypt(plaintext: ClauseElement) -> ColumnElement[Any]:
    return func.pgp_sym_encrypt(
        cast(plaintext, Text()),
        bindparam(
            "db_encryption_key",
            callable_=_get_encryption_key,
            type_=String(),
            unique=True,
        ),
        literal_column(f"'{_PGCRYPTO_OPTIONS}'"),
    )


def decrypt(ciphertext: ClauseElement) -> ColumnElement[Any]:
    return func.pgp_sym_decrypt(
        ciphertext,
        bindparam(
            "db_encryption_key",
            callable_=_get_encryption_key,
            type_=String(),
            unique=True,
        ),
    )


class EncryptedText(TypeDecorator):
    impl = LargeBinary
    cache_ok = True

    def bind_expression(self, bindvalue: ClauseElement) -> ColumnElement[Any]:
        return encrypt(bindvalue)

    def column_expression(self, col: ClauseElement) -> ColumnElement[Any]:
        return decrypt(col)
