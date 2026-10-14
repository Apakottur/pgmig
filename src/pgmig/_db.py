from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Self

import psycopg
from psycopg import pq
from psycopg.rows import dict_row

from pgmig._drivers import DbDriver
from pgmig._errors import PgmigDbDriverError, PgmigInvalidDbDsnError


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


# Opens the transaction all the introspection queries run in, executed in order before the first query.
_SNAPSHOT_SETUP = (
    # A read-only REPEATABLE READ transaction, so that all the reads are done on a single consistent snapshot.
    "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY",
    # An empty search path, so that introspection is independent of the database's own search path.
    # SET LOCAL scopes it to the transaction, so it also holds behind a transaction-pooling pgbouncer.
    "SET LOCAL search_path = ''",
)


class DbReadOnlyConnection(DbConnection):
    """
    DB connection API for read-only operations.

    The introspection queries run in a single snapshot transaction, opened by the first introspect() call and ended
    (committed, or rolled back on error) when the connection context exits.
    """

    async def introspect(self, queries: Sequence[str]) -> list[list[dict[str, Any]]]:
        """
        Run the given introspection queries in a single round trip, returning the rows of each one.
        """
        # On the first call, open the snapshot transaction in the same round trip as the queries.
        setup = _SNAPSHOT_SETUP if self.driver_conn.info.transaction_status == pq.TransactionStatus.IDLE else ()

        async with self.driver_conn.cursor(row_factory=dict_row) as cur:
            # Run all the statements as one multi-statement execute. Each statement produces its own result set.
            await cur.execute("\n;\n".join([*setup, *queries]))  # ty: ignore[no-matching-overload]

            # Skip the result sets of the setup statements, and fetch the rows of each query result set.
            results = cur.results()
            for _ in setup:
                await anext(results)
            return [await result.fetchall() async for result in results]
