from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import psycopg


@dataclass(frozen=True)
class _ContextData:
    """
    Context data for the current introspection.
    """

    # Connection the introspection runs on.
    conn: psycopg.AsyncConnection[Any]


# Context of the current introspection.
_context: ContextVar[_ContextData] = ContextVar("pgmig_introspection_context")


class _Context:
    """
    Proxy over the context var. Loaders and guards read `context.conn` instead of receiving
    the connection as a parameter. Each introspection runs in its own asyncio task (they are
    launched with asyncio.gather), and contextvars are copied per task, so the source and
    target connections never leak into one another.
    """

    @contextmanager
    def context_scope(self, *, conn: psycopg.AsyncConnection[Any]) -> Iterator[None]:
        token = _context.set(_ContextData(conn=conn))
        try:
            yield
        finally:
            _context.reset(token)

    @property
    def conn(self) -> psycopg.AsyncConnection[Any]:
        return _context.get().conn


context = _Context()
