import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Self, TypeVar, cast

import asyncpg
import psycopg
from psycopg.rows import class_row
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
    async def connect(cls, *, db_conn_info: DbConnInfo) -> AsyncIterator[Self]:
        """
        Connection context.
        """
        match db_conn_info.driver.resolved:
            case DbDriver.PSYCOPG:
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
            case _:
                try:
                    asyncpg_conn = await asyncpg.connect(db_conn_info.dsn)
                except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as error:
                    raise PgmigDbDriverError(
                        label=db_conn_info.label, driver=db_conn_info.driver, driver_error=error
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
            case DbDriver.PSYCOPG:
                try:
                    result = await self.driver_conn.execute(statement)
                except psycopg.errors.UniqueViolation as error:
                    raise UniqueViolation(str(error)) from error

                if result.description:
                    return cast("list[tuple[Any, ...]]", await result.fetchall())
                return []

            # asyncpg.
            case _:
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
            match conn.driver:
                case DbDriver.PSYCOPG:
                    # Force all subsequent transactions to be read-only.
                    await conn.driver_conn.set_read_only(True)

                    # Use REPEATABLE READ so all introspection reads a single snapshot of the database.
                    await conn.driver_conn.set_isolation_level(psycopg.IsolationLevel.REPEATABLE_READ)

                # asyncpg, which has no setters for either and takes them as statements.
                case _:
                    await conn.driver_conn.execute("SET default_transaction_read_only = on")
                    await conn.driver_conn.execute("SET default_transaction_isolation = 'repeatable read'")

            # Use an empty search path so introspection is independent of the database's own search
            # path: pg_get_*def()/format_type() then emit fully schema-qualified names.
            await conn.execute("SET search_path = ''")

            # Run the enclosed reads inside a single transaction to guarantee a consistent snapshot of the database.
            async with conn.driver_conn.transaction():
                yield conn

    async def introspect(self, query: str, response_model: type[_RowT]) -> list[_RowT]:
        """
        Run an introspection query and parse each row into the given model.
        """
        match self.driver:
            case DbDriver.PSYCOPG:
                async with self.driver_conn.cursor(row_factory=class_row(response_model)) as cur:
                    await cur.execute(query)
                    return cast("list[_RowT]", await cur.fetchall())

            # asyncpg.
            case _:
                records = await self.driver_conn.fetch(query)
                return [response_model(**record) for record in records]
