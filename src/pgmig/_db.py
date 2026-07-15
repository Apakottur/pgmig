from types import TracebackType
from typing import Any, TypeVar, cast

import psycopg
from psycopg.rows import class_row
from pydantic import BaseModel
from typing_extensions import LiteralString, Self

from pgmig._errors import _PgmigError

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class DbConnection:
    """
    Async wrapper around a psycopg connection. This is the only module in pgmig that imports
    psycopg; every other module talks to the database through this class, so swapping the
    driver (e.g. to asyncpg) is confined here.
    """

    def __init__(self, conn: psycopg.AsyncConnection[Any]) -> None:
        self._conn = conn

    @classmethod
    async def connect(cls, dsn: str) -> Self:
        """
        Open a connection suitable for introspection: read-only, on a single REPEATABLE READ
        snapshot. Connection failures surface as a _PgmigError.
        """
        try:
            conn = await psycopg.AsyncConnection.connect(dsn)
        except psycopg.Error as error:
            raise _PgmigError(f"Could not connect to database: {error}") from error

        # Force all subsequent transactions to be read-only.
        await conn.set_read_only(True)

        # Use REPEATABLE READ so that all introspection is done on a single snapshot of the database.
        await conn.set_isolation_level(psycopg.IsolationLevel.REPEATABLE_READ)

        return cls(conn)

    async def __aenter__(self) -> Self:
        # Delegates to the underlying connection: opens a transaction, and on exit commits
        # (or rolls back on error) and closes the connection.
        await self._conn.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._conn.__aexit__(exc_type, exc, tb)

    async def execute(self, statement: str) -> None:
        """
        Run a statement that returns no rows (e.g. a session SET).
        """
        await self._conn.execute(cast("LiteralString", statement))

    async def fetch_models(self, query: str, model: type[_ModelT]) -> list[_ModelT]:
        """
        Run a query and parse each row into the given Pydantic model (by SELECT column alias).
        Validation happens at parse time, so a schema/type drift surfaces here rather than
        silently downstream.
        """
        async with self._conn.cursor(row_factory=class_row(model)) as cur:
            await cur.execute(cast("LiteralString", query))
            return await cur.fetchall()
