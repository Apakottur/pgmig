from typing import Any
from unittest.mock import MagicMock

import psycopg
import pytest

from pgmig._build._engine import _connect
from pgmig._errors import PgmigError


def test_connect_passes_no_startup_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The introspection connection must configure read-only and isolation at the transaction
    level, never via server-side startup options (-c ...). pgbouncer rejects unknown startup
    parameters ("unsupported startup parameter in options: ...") and would block every
    connection made through it, so passing an `options=` string is a regression.
    """
    captured: dict[str, Any] = {}
    fake_conn = MagicMock()

    def fake_connect(dsn: str, **kwargs: Any) -> MagicMock:
        captured["dsn"] = dsn
        captured["kwargs"] = kwargs
        return fake_conn

    monkeypatch.setattr(psycopg, "connect", fake_connect)

    conn = _connect("postgresql://user@host/db")

    assert conn is fake_conn
    assert captured["dsn"] == "postgresql://user@host/db"
    # No startup options at all -- the pgbouncer-safe contract.
    assert "options" not in captured["kwargs"]
    # Session configured at the transaction level instead.
    assert fake_conn.read_only is True
    assert fake_conn.isolation_level == psycopg.IsolationLevel.REPEATABLE_READ


def test_connect_wraps_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A driver-level connection failure surfaces as a PgmigError, not a raw psycopg error.
    """

    def fake_connect(dsn: str, **kwargs: Any) -> MagicMock:
        raise psycopg.OperationalError("boom")

    monkeypatch.setattr(psycopg, "connect", fake_connect)

    with pytest.raises(PgmigError, match="Could not connect to database"):
        _connect("postgresql://user@host/db")
