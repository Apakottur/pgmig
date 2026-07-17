from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import psycopg
from psycopg.rows import class_row
from pydantic import BaseModel
from typing_extensions import Self

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
            conn = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
        except psycopg.Error as error:
            raise _PgmigError(f"Could not connect to database: {error}") from error

        async with conn:
            yield cls(dsn=dsn, conn=conn)

    async def execute(self, statement: str) -> list[tuple[Any, ...]]:
        """
        Execute a statement and return the statement results, if any.
        """
        # Execute the statement.
        try:
            result = await self.driver_conn.execute(statement)  # ty: ignore[no-matching-overload]
        except psycopg.errors.UniqueViolation as error:
            raise UniqueViolation(str(error)) from error

        # Fetch and return the results, if any.
        if result.description:
            return await result.fetchall()
        return []


class DbReadOnlyConnection(DbConnection):
    """
    DB connection API for read-only operations.
    """

    @classmethod
    @asynccontextmanager
    async def connect(cls, *, dsn: str) -> AsyncIterator[Self]:
        """
        Read-only connection context.
        """
        async with super().connect(dsn=dsn) as conn:
            # Force all subsequent transactions to be read-only.
            await conn.driver_conn.set_read_only(True)

            # Use REPEATABLE READ so that the enclosed reads are done on a single consistent snapshot of the database.
            await conn.driver_conn.set_isolation_level(psycopg.IsolationLevel.REPEATABLE_READ)

            # Use an empty search path so introspection is independent of the database's own search path.
            await conn.driver_conn.execute("SET search_path = ''")

            # Run the enclosed reads inside a single transaction to guarantee a consistent snapshot of the database.
            async with conn.driver_conn.transaction():
                yield conn

    async def introspect(self, query: str, response_model: type[_RowT]) -> list[_RowT]:
        """
        Run an introspection query and parse each row into the given model.
        """
        async with self.driver_conn.cursor(row_factory=class_row(response_model)) as cur:
            await cur.execute(query)  # ty: ignore[no-matching-overload]
            return await cur.fetchall()
