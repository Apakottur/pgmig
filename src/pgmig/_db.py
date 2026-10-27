from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import Any, Self, assert_never

from pgmig._drivers import DbConnInfo, DbDriver, DriverConnection
from pgmig._errors import PgmigApiError


def _get_driver_connection_class(driver: DbDriver) -> type[DriverConnection]:
    """
    Get the implementation of the given driver.
    """
    match driver.resolved:
        case DbDriver.PSYCOPG:  # pragma: psycopg-only
            from pgmig._psycopg import PsycopgConnection  # noqa: PLC0415

            return PsycopgConnection
        case DbDriver.ASYNCPG:  # pragma: asyncpg-only
            # asyncpg is an optional extra, so it may not be installed.
            try:
                from pgmig._asyncpg import AsyncpgConnection  # noqa: PLC0415
            except ModuleNotFoundError as error:
                raise PgmigApiError("The asyncpg driver is not installed. Install the pgmig[asyncpg] extra.") from error

            return AsyncpgConnection
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

# Ends the snapshot transaction, executed after the last introspection query.
# The transaction is read-only, so there is nothing to commit.
_SNAPSHOT_TEARDOWN = ("ROLLBACK",)


class DbReadOnlyConnection(DbConnection):
    """
    DB connection API for read-only operations.

    The introspection queries run in a single snapshot transaction, opened by the first introspect() call and ended
    by the introspect() call that passes end_snapshot, or when the connection context exits.
    """

    async def introspect(self, queries: Sequence[str], *, end_snapshot: bool = False) -> list[list[dict[str, Any]]]:
        """
        Run the given introspection queries, returning the rows of each one.
        With end_snapshot, also end the snapshot transaction once the queries ran, so that it does not sit idle (and
        trip the server's idle_in_transaction_session_timeout) while their rows are processed.
        """
        return await self.driver_conn.introspect(queries, _SNAPSHOT_SETUP, _SNAPSHOT_TEARDOWN if end_snapshot else ())
