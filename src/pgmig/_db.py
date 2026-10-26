from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Self, assert_never

from pgmig._drivers import DbDriver, DriverConnection


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


def _get_driver_connection_class(driver: DbDriver) -> type[DriverConnection]:
    """
    Get the implementation of the given driver.
    """
    match driver.resolved:
        case DbDriver.PSYCOPG:
            from pgmig._psycopg import PsycopgConnection  # noqa: PLC0415

            return PsycopgConnection
        case _:
            assert_never(driver.resolved)


class DbConnection:
    """
    DB connection API.
    All DB interaction is done through this class to avoid the DB driver leaking into other modules.
    """

    def __init__(self, *, db_conn_info: DbConnInfo, conn: DriverConnection) -> None:
        self.db_conn_info = db_conn_info
        self.driver_conn = conn

    @property
    def dsn(self) -> str:
        return self.db_conn_info.dsn

    @classmethod
    @asynccontextmanager
    async def connect(cls, *, db_conn_info: DbConnInfo) -> AsyncGenerator[Self]:
        """
        Connection context.
        """
        async with _get_driver_connection_class(db_conn_info.driver).connect(db_conn_info) as conn:
            yield cls(db_conn_info=db_conn_info, conn=conn)

    async def execute(self, statement: str) -> list[tuple[Any, ...]]:
        """
        Execute a statement and return the statement results, if any.
        """
        return await self.driver_conn.execute(statement)


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
        return await self.driver_conn.introspect(queries, _SNAPSHOT_SETUP)
