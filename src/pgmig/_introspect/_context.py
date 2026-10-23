from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from pgmig._db import DbReadOnlyConnection
from pgmig._models import DbIntrospectionResult


@dataclass(frozen=True)
class ContextData:
    """
    Context data for the current introspection.
    """

    # DB connection.
    conn: DbReadOnlyConnection

    # Result being assembled by the loaders.
    db_introspection_result: DbIntrospectionResult

    # Schemas to exclude from the diff entirely.
    ignore_schemas: frozenset[str]


# Context of the current introspection.
_context: ContextVar[ContextData] = ContextVar("pgmig_introspection_context")


@contextmanager
def context_scope(data: ContextData) -> Generator[None]:
    """
    Run the enclosed introspection with the given context data.
    """
    token = _context.set(data)
    try:
        yield
    finally:
        _context.reset(token)


def context() -> ContextData:
    """
    The context data of the current introspection.
    """
    return _context.get()
