from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypeVar, cast

import psycopg
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

    def __init__(self, *, dsn: str, conn: psycopg.AsyncConnection[Any]) -> None:
        self.dsn = dsn
        self.driver_conn = conn

    @classmethod
    @asynccontextmanager
    async def connect(cls, *, dsn: str) -> AsyncIterator[Self]:
        """
        Connection context.
        """
        try:
            conn = await psycopg.AsyncConnection.connect(dsn)
        except psycopg.Error as error:
            raise _PgmigError(f"Could not connect to database: {error}") from error

        async with conn:
            yield cls(dsn=dsn, conn=conn)

    async def execute(self, statement: str) -> psycopg.AsyncCursor[Any]:
        """
        Execute a statement that returns no rows.
        """
        try:
            return await self.driver_conn.execute(cast("LiteralString", statement))
        except psycopg.errors.UniqueViolation as error:
            raise UniqueViolation(str(error)) from error


class DbReadOnlyConnection(DbConnection):
    """
    DB connection API for read-only operations.
    """

    @classmethod
    @asynccontextmanager
    async def connect(cls, dsn: str) -> AsyncIterator[Self]:
        """
        Read-only connection context.
        """
        async with super().connect(dsn=dsn) as conn:
            # Force all subsequent transactions to be read-only.
            await conn.driver_conn.set_read_only(True)

            # Use REPEATABLE READ so that all introspection is done on a single snapshot of the database.
            await conn.driver_conn.set_isolation_level(psycopg.IsolationLevel.REPEATABLE_READ)

            yield conn

    async def introspect(self, query: str, response_model: type[_RowT]) -> list[_RowT]:
        """
        Run introspection query and parse each row into the given model.
        """
        # Execute the query.
        cursor = await self.execute(query)

        # Fetch the results.
        result = await cursor.fetchall()

        # Parse the results.
        return [response_model.model_validate(row) for row in result]
