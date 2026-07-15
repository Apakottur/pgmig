from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import psycopg

# Connection for the current introspection.
_conn: ContextVar[psycopg.AsyncConnection[Any]] = ContextVar("pgmig_introspection_conn")


class _Context:
    """
    Proxy over the introspection context var. Loaders and guards read `context.conn`
    instead of receiving the connection as a parameter. Each introspection runs in its
    own asyncio task (they are launched with asyncio.gather), and contextvars are copied
    per task, so the source and target connections never leak into one another.
    """

    @contextmanager
    def context_scope(self, *, conn: psycopg.AsyncConnection[Any]) -> Iterator[None]:
        token = _conn.set(conn)
        try:
            yield
        finally:
            _conn.reset(token)

    @property
    def conn(self) -> psycopg.AsyncConnection[Any]:
        return _conn.get()


context = _Context()
