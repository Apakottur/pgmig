from functools import lru_cache
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

from pgmig._introspect._context import context

# Static introspection queries dir.
_QUERIES_DIR = Path(__file__).parent / "queries"


@lru_cache
def _read_query(file_name: str) -> str:
    return (_QUERIES_DIR / file_name).read_text(encoding="utf-8")


class _IntrospectionRow(BaseModel):
    """
    Base for every model parsed from a bundled SQL query -- a top-level row, or a nested
    jsonb object a query builds.
    """

    model_config = ConfigDict(
        # Ensure queries dont fetch unused columns.
        extra="forbid",
    )


class _IntrospectionRowWithSchema(_IntrospectionRow):
    """
    Base for every top-level row that carries a required schema in `schema_name` -- the schema an
    object belongs to. A shared base so that schema-bearing rows can be told apart from the rest
    (dependency rows carry a pair of schemas, a few carry none).
    """

    schema_name: str


class Loader(Protocol):
    """
    The shared shape of every object-kind loader: read from the connection and populate
    the DB introspection result being assembled. Loaders run in a dependency-significant order (schemas
    and tables before the objects that attach to them).
    """

    async def __call__(self) -> None: ...


class Guard(Protocol):
    """
    A precondition check run before any loader: return a human-readable finding for each
    object the database contains that pgmig cannot process (an unsupported kind, an
    invalid index). An empty list means the guard passed. Findings from every guard are
    collected and reported together so the user sees all problems at once.
    """

    async def __call__(self) -> list[str]: ...


_RowT = TypeVar("_RowT", bound=_IntrospectionRow)


async def run_introspection_query(file_name: str, model: type[_RowT]) -> list[_RowT]:
    """
    Run the introspection query, parsing each row into the given model.
    """
    return await context.conn.introspect(_read_query(file_name), model)
