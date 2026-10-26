from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal, Self, assert_never

import psycopg

from pgmig import _psycopg
from pgmig._drivers import DbDriver


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
    Each driver's implementation lives in its own module, and every method dispatches on the driver.
    """

    def __init__(self, *, db_conn_info: DbConnInfo, conn: psycopg.AsyncConnection[Any]) -> None:
        self.db_conn_info = db_conn_info
        self.driver_conn = conn

    @property
    def dsn(self) -> str:
        return self.db_conn_info.dsn

    @property
    def driver(self) -> Literal[DbDriver.PSYCOPG]:
        return self.db_conn_info.driver.resolved

    @classmethod
    @asynccontextmanager
    async def connect(cls, *, db_conn_info: DbConnInfo) -> AsyncGenerator[Self]:
        """
        Connection context.
        """
        match db_conn_info.driver.resolved:
            case DbDriver.PSYCOPG:
                async with _psycopg.connect(db_conn_info) as conn:
                    yield cls(db_conn_info=db_conn_info, conn=conn)
            case _:
                assert_never(db_conn_info.driver.resolved)

    async def execute(self, statement: str) -> list[tuple[Any, ...]]:
        """
        Execute a statement and return the statement results, if any.
        """
        match self.driver:
            case DbDriver.PSYCOPG:
                return await _psycopg.execute(self.driver_conn, statement)
            case _:
                assert_never(self.driver)


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
        Run the given introspection queries, returning the rows of each one.
        """
        match self.driver:
            case DbDriver.PSYCOPG:
                return await _psycopg.introspect(self.driver_conn, queries, _SNAPSHOT_SETUP)
            case _:
                assert_never(self.driver)
