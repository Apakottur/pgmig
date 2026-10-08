from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Self, TypeVar

import psycopg
from psycopg.rows import DictRow, dict_row
from pydantic import BaseModel

from pgmig._drivers import DbDriver
from pgmig._errors import PgmigDbDriverError, PgmigInvalidDbDsnError

_RowT = TypeVar("_RowT", bound=BaseModel)


class UniqueViolation(Exception):
    """
    The DB operation failed because of a unique constraint violation.
    """


@dataclass(frozen=True)
class DbConnInfo:
    """
    Information about a single database.
    """

    # The database DSN.
    dsn: str

    # Friendly label, used in error/log messages.
    label: str

    # The driver to connect with.
    driver: DbDriver = DbDriver.AUTO


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
            raise PgmigDbDriverError(
                label=db_conn_info.label,
                driver=db_conn_info.driver,
                # Wrap with a generic exception in case of a DSN parsing error to avoid leaking the DSN.
                driver_error=PgmigInvalidDbDsnError() if isinstance(error, psycopg.ProgrammingError) else error,
            ) from error

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


class PendingIntrospectionQuery:
    """
    An introspection query that was sent and whose rows were not fetched yet.
    """

    def __init__(self, cur: psycopg.AsyncCursor[DictRow]) -> None:
        self._cur = cur

    async def fetch(self, response_model: type[_RowT]) -> list[_RowT]:
        """
        Fetch the query rows, parsing each row into the given model.
        """
        async with self._cur as cur:
            return [response_model(**row) for row in await cur.fetchall()]


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

    @asynccontextmanager
    async def pipeline(self) -> AsyncIterator[None]:
        """
        Pipeline context: the enclosed queries are sent without waiting for the results of the previous ones.
        """
        async with self.driver_conn.pipeline():
            yield

    async def send_introspection_query(self, query: str) -> PendingIntrospectionQuery:
        """
        Send an introspection query, without waiting for its results (when within a pipeline).
        """
        cur = self.driver_conn.cursor(row_factory=dict_row)
        await cur.execute(query)  # ty: ignore[no-matching-overload]
        return PendingIntrospectionQuery(cur)
