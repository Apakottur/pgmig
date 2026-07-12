from pathlib import Path
from typing import Protocol, TypeVar

import asyncpg
from pydantic import BaseModel

from pgmig._models import DbInfo

_RowT = TypeVar("_RowT", bound=BaseModel)


async def _run_query(conn: asyncpg.Connection, file_name: str, model: type[_RowT]) -> list[_RowT]:
    """
    Load a bundled SQL query from the queries directory, run it, and parse each row
    into the given Pydantic model (by SELECT column alias). Validation happens at parse
    time, so a schema/type drift surfaces here rather than silently downstream.
    """
    file_path = Path(__file__).parent.joinpath("queries").joinpath(file_name)
    query = file_path.read_text(encoding="utf-8")
    records = await conn.fetch(query)
    return [model(**dict(record)) for record in records]


class Loader(Protocol):
    """
    The shared shape of every object-kind loader: read from the connection and populate
    the DbInfo being assembled. Loaders run in a dependency-significant order (schemas
    and tables before the objects that attach to them).
    """

    async def __call__(self, conn: asyncpg.Connection, db_info: DbInfo) -> None: ...
