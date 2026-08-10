from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
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


@dataclass(frozen=True)
class DbConnInfo:
    """
    Everything needed to reach a single database: the DSN and the role the database plays
    ("source", "target"), which names it in error messages.

    Built once per database and passed around instead of the bare DSN, so a connection and
    the label that makes its errors actionable cannot drift apart at a call site.
    """

    dsn: str
    label: str


class DbConnection:
    """
    DB connection API.
    All DB interaction is done through this class to avoid the DB driver leaking into other modules.
    """

    def __init__(self, *, db_conn_info: DbConnInfo, conn: psycopg.AsyncConnection[Any]) -> None:
        self.db_conn_info = db_conn_info
        self.driver_conn = conn

    @property
    def dsn(self) -> str:
        return self.db_conn_info.dsn

    @classmethod
    @asynccontextmanager
    async def connect(cls, *, db_conn_info: DbConnInfo) -> AsyncIterator[Self]:
        """
        Connection context.
        """
        try:
            conn = await psycopg.AsyncConnection.connect(db_conn_info.dsn, autocommit=True)
        except psycopg.Error as error:
            raise _PgmigError(f"Could not connect to {db_conn_info.label} database: {error}") from error

        async with conn:
            yield cls(db_conn_info=db_conn_info, conn=conn)

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
    async def connect(cls, *, db_conn_info: DbConnInfo) -> AsyncIterator[Self]:
        """
        Read-only connection context.
        """
        async with super().connect(db_conn_info=db_conn_info) as conn:
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
