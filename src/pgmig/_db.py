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
    async def _open(cls, dsn: str, *, autocommit: bool) -> psycopg.AsyncConnection[Any]:
        """
        Open the underlying driver connection, wrapping any driver error.
        """
        try:
            return await psycopg.AsyncConnection.connect(dsn, autocommit=autocommit)
        except psycopg.Error as error:
            raise _PgmigError(f"Could not connect to database: {error}") from error

    @classmethod
    @asynccontextmanager
    async def connect(cls, *, dsn: str) -> AsyncIterator[Self]:
        """
        Connection context.

        Autocommit is on: this connection runs generated migration SQL, which includes
        statements that cannot run inside a transaction block (e.g. CREATE INDEX
        CONCURRENTLY).
        """
        conn = await cls._open(dsn, autocommit=True)
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

        Autocommit is off so a single REPEATABLE READ transaction spans every introspection
        query: without it each query is its own transaction with its own snapshot, and
        concurrent DDL on a live database could tear the result (an object seen by one loader
        but gone by the next). The transaction opens on the first statement below and is held
        open (never committed) for the connection's lifetime; the read-only flag and empty
        search path apply to it.
        """
        conn = await cls._open(dsn, autocommit=False)
        async with conn:
            # Read-only and REPEATABLE READ must be set before the transaction begins (no
            # statement has run yet), so they govern the snapshot the loaders share.
            await conn.set_read_only(True)
            await conn.set_isolation_level(psycopg.IsolationLevel.REPEATABLE_READ)

            # Empty search path so introspection is independent of the database's own search
            # path: pg_get_*def()/format_type() then emit fully schema-qualified names. This
            # first statement opens the shared transaction.
            await conn.execute("SET search_path = ''")

            yield cls(dsn=dsn, conn=conn)

    async def introspect(self, query: str, response_model: type[_RowT]) -> list[_RowT]:
        """
        Run an introspection query and parse each row into the given model.
        """
        async with self.driver_conn.cursor(row_factory=class_row(response_model)) as cur:
            await cur.execute(query)  # ty: ignore[no-matching-overload]
            return await cur.fetchall()
