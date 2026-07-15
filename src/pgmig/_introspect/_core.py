from pathlib import Path
from typing import Protocol, TypeVar, cast

from psycopg.rows import class_row
from pydantic import BaseModel, ConfigDict
from typing_extensions import LiteralString

from pgmig._introspect._context import context


class _QueryRow(BaseModel):
    """
    Base for every model parsed from a bundled SQL query -- a top-level row, or a nested
    jsonb object a query builds.
    """

    model_config = ConfigDict(
        # Ensure queries dont fetch unused columns.
        extra="forbid",
    )


class Loader(Protocol):
    """
    The shared shape of every object-kind loader: read from the introspection connection and
    populate the result being assembled on the context. Loaders run in a dependency-significant
    order (schemas and tables before the objects that attach to them).
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


_RowT = TypeVar("_RowT", bound=_QueryRow)


async def run_introspection_query(file_name: str, model: type[_RowT]) -> list[_RowT]:
    """
    Load a bundled SQL query from the queries directory, run it on the current introspection
    connection, and parse each row into the given Pydantic model (by SELECT column alias).
    Validation happens at parse time, so a schema/type drift surfaces here rather than
    silently downstream.
    """
    file_path = Path(__file__).parent.joinpath("queries").joinpath(file_name)
    query = cast("LiteralString", file_path.read_text(encoding="utf-8"))  # type: ignore[redundant-cast]
    async with context.conn.cursor(row_factory=class_row(model)) as cur:
        await cur.execute(query)
        return await cur.fetchall()
