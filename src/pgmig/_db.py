import json
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Self, cast

import asyncpg
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

    def __init__(self, *, db_conn_info: DbConnInfo, conn: Any) -> None:
        self.db_conn_info = db_conn_info
        self.driver_conn = conn

    @property
    def dsn(self) -> str:
        return self.db_conn_info.dsn

    @property
    def driver(self) -> DbDriver:
        return self.db_conn_info.driver.resolved

    @classmethod
    @asynccontextmanager
    async def connect(cls, *, db_conn_info: DbConnInfo) -> AsyncGenerator[Self]:
        """
        Connection context.
        """
        match db_conn_info.driver.resolved:
            case DbDriver.PSYCOPG:  # pragma: psycopg-only
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

            # asyncpg. Spelled as the fallback so that the match cannot fall through.
            case _:  # pragma: asyncpg-only
                try:
                    asyncpg_conn = await asyncpg.connect(db_conn_info.dsn)
                except (ValueError, OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as error:
                    raise PgmigDbDriverError(
                        label=db_conn_info.label,
                        driver=db_conn_info.driver,
                        # Wrap with a generic exception in case of a DSN parsing error to avoid leaking the DSN.
                        # asyncpg raises a ValueError for some malformed fields, such as a non-numeric port.
                        driver_error=PgmigInvalidDbDsnError()
                        if isinstance(error, (ValueError, asyncpg.ClientConfigurationError))
                        else error,
                    ) from error

                # asyncpg returns json/jsonb as raw text by default; decode so queries that build
                # nested jsonb objects (domains, composite types, functions) parse into their models.
                for type_name in ("json", "jsonb"):
                    await asyncpg_conn.set_type_codec(
                        type_name, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
                    )

                try:
                    yield cls(db_conn_info=db_conn_info, conn=asyncpg_conn)
                finally:
                    await asyncpg_conn.close()

    async def execute(self, statement: str) -> list[tuple[Any, ...]]:
        """
        Execute a statement and return the statement results, if any.
        """
        # An empty statement is a no-op. psycopg tolerates it; asyncpg raises on an empty query.
        if not statement.strip():
            return []

        match self.driver:
            case DbDriver.PSYCOPG:  # pragma: psycopg-only
                try:
                    result = await self.driver_conn.execute(statement)
                except psycopg.errors.UniqueViolation as error:
                    raise UniqueViolation(str(error)) from error

                if result.description:
                    return cast("list[tuple[Any, ...]]", await result.fetchall())
                return []

            # asyncpg.
            case _:  # pragma: asyncpg-only
                # asyncpg splits protocols: fetch() (extended) returns rows but forbids multiple
                # statements and commands that cannot run in a transaction; execute() (simple) allows
                # those but returns no rows. Reads are always single SELECT-likes; everything else is DDL.
                is_read = statement.lstrip().upper().startswith(("SELECT", "WITH", "SHOW", "VALUES", "TABLE"))
                try:
                    if is_read:
                        records = await self.driver_conn.fetch(statement)
                        return [tuple(record) for record in records]
                    await self.driver_conn.execute(statement)
                except asyncpg.UniqueViolationError as error:
                    raise UniqueViolation(str(error)) from error
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
        match self.driver:
            case DbDriver.PSYCOPG:  # pragma: psycopg-only
                # On the first call, also open the snapshot transaction, in the same round trip as the queries.
                statements = list(queries)
                if self.driver_conn.info.transaction_status == pq.TransactionStatus.IDLE:
                    statements = [*_SNAPSHOT_SETUP, *statements]

                async with self.driver_conn.cursor(row_factory=dict_row) as cur:
                    # Run all the statements as one multi-statement execute. Each statement produces its own result
                    # set.
                    await cur.execute("\n;\n".join(statements))

                    # Fetch the rows of each query result set. The setup statements return no rows, so their sets
                    # are skipped.
                    return [await result.fetchall() async for result in cur.results() if result.description is not None]

            # asyncpg.
            case _:  # pragma: asyncpg-only
                # On the first call, open the snapshot transaction. execute() uses the simple protocol, which allows
                # multiple statements in one round trip.
                if not self.driver_conn.is_in_transaction():
                    await self.driver_conn.execute(";\n".join(_SNAPSHOT_SETUP))

                # fetch() uses the extended protocol, which returns rows but runs a single statement, so each query is
                # its own round trip.
                return [[dict(record) for record in await self.driver_conn.fetch(query)] for query in queries]
