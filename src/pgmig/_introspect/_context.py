from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from pgmig._db import DbConnection
from pgmig._models import DbIntrospectionResult


@dataclass(frozen=True)
class _ContextData:
    """
    Context data for the current introspection.
    """

    # DB connection.
    conn: DbConnection

    # Result being assembled by the loaders.
    db_info: DbIntrospectionResult


# Context of the current introspection.
_context: ContextVar[_ContextData] = ContextVar("pgmig_introspection_context")


class _Context:
    """
    Singleton class for the introspection context.
    """

    @contextmanager
    def context_scope(
        self,
        *,
        conn: DbConnection,
        db_info: DbIntrospectionResult,
    ) -> Iterator[None]:
        token = _context.set(
            _ContextData(
                conn=conn,
                db_info=db_info,
            )
        )
        try:
            yield
        finally:
            _context.reset(token)

    @property
    def conn(self) -> DbConnection:
        return _context.get().conn

    @property
    def db_info(self) -> DbIntrospectionResult:
        return _context.get().db_info


context = _Context()
