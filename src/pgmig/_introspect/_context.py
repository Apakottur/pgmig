from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pgmig._db import DbReadOnlyConnection, PendingIntrospectionQuery
from pgmig._models import DbIntrospectionResult

if TYPE_CHECKING:
    from pgmig._introspect._core import IntrospectionQuery


@dataclass(frozen=True)
class _ContextData:
    """
    Context data for the current introspection.
    """

    # DB connection.
    conn: DbReadOnlyConnection

    # Result being assembled by the loaders.
    db_introspection_result: DbIntrospectionResult

    # Schemas to exclude from the diff entirely.
    ignore_schemas: frozenset[str]

    # Introspection queries that were sent and whose rows were not fetched yet.
    pending_queries: "dict[IntrospectionQuery, PendingIntrospectionQuery]" = field(default_factory=dict)


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
        conn: DbReadOnlyConnection,
        db_introspection_result: DbIntrospectionResult,
        ignore_schemas: frozenset[str],
    ) -> Iterator[None]:
        token = _context.set(
            _ContextData(
                conn=conn,
                db_introspection_result=db_introspection_result,
                ignore_schemas=ignore_schemas,
            )
        )
        try:
            yield
        finally:
            _context.reset(token)

    @property
    def conn(self) -> DbReadOnlyConnection:
        return _context.get().conn

    @property
    def db_introspection_result(self) -> DbIntrospectionResult:
        return _context.get().db_introspection_result

    @property
    def ignore_schemas(self) -> frozenset[str]:
        return _context.get().ignore_schemas

    @property
    def pending_queries(self) -> "dict[IntrospectionQuery, PendingIntrospectionQuery]":
        return _context.get().pending_queries


context = _Context()
