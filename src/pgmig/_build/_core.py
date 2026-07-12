from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

import psycopg
from psycopg.rows import class_row
from pydantic import BaseModel
from typing_extensions import LiteralString

from pgmig._models import DbInfo

_RowT = TypeVar("_RowT", bound=BaseModel)


def _run_query(conn: psycopg.Connection[Any], file_name: str, model: type[_RowT]) -> list[_RowT]:
    """
    Load a bundled SQL query from the queries directory, run it, and parse each row
    into the given Pydantic model (by SELECT column alias). Validation happens at parse
    time, so a schema/type drift surfaces here rather than silently downstream.
    """
    file_path = Path(__file__).parent.joinpath("queries").joinpath(file_name)
    query = cast("LiteralString", file_path.read_text(encoding="utf-8"))  # type: ignore[redundant-cast]
    with conn.cursor(row_factory=class_row(model)) as cur:
        return cur.execute(query).fetchall()


class Loader(Protocol):
    """
    The shared shape of every object-kind loader: read from the connection and populate
    the DbInfo being assembled. Loaders run in a dependency-significant order (schemas
    and tables before the objects that attach to them).
    """

    def __call__(self, conn: psycopg.Connection[Any], db_info: DbInfo) -> None: ...
