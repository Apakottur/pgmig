from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypeVar, cast, overload

import psycopg
from psycopg.rows import class_row
from pydantic import BaseModel
from typing_extensions import LiteralString, Self

from pgmig._errors import _PgmigError

_RowT = TypeVar("_RowT", bound=BaseModel)


class UniqueViolation(Exception):
    """
    The DB operation failed because of a unique constraint violation.
    """


class DbConnection:
    """
    DB connection API.
    All DB interaction is done through this class to avoid the DB driver leaking into other modules.
    """

    def __init__(self, conn: psycopg.AsyncConnection[Any]) -> None:
        self._conn = conn

    @classmethod
    @asynccontextmanager
    async def connect(cls, dsn: str) -> AsyncIterator[Self]:
        """
        Open a connection suitable for introspection: read-only, on a single REPEATABLE READ
        snapshot. Connection failures surface as a _PgmigError.
        """
        try:
            conn = await psycopg.AsyncConnection.connect(dsn)
        except psycopg.Error as error:
            raise _PgmigError(f"Could not connect to database: {error}") from error

        async with conn:
            # Force all subsequent transactions to be read-only.
            await conn.set_read_only(True)

            # Use REPEATABLE READ so that all introspection is done on a single snapshot of the database.
            await conn.set_isolation_level(psycopg.IsolationLevel.REPEATABLE_READ)

            yield cls(conn)

    async def introspect(self, query: str, response_model: type[_RowT]) -> list[_RowT]:
        """
        Run introspection query and parse each row into the given model.
        """
        async with self._conn.cursor(row_factory=class_row(response_model)) as cur:
            try:
                await cur.execute(cast("LiteralString", query))
            except psycopg.errors.UniqueViolation as error:
                raise UniqueViolation(str(error)) from error
            return await cur.fetchall()

    async def execute(self, statement: str) -> None:
        """
        Execute a statement that returns no rows.
        """
        try:
            await self._conn.execute(cast("LiteralString", statement))
        except psycopg.errors.UniqueViolation as error:
            raise UniqueViolation(str(error)) from error
