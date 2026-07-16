import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal, TypeVar, cast

import asyncpg
import psycopg
from psycopg.rows import class_row
from pydantic import BaseModel
from typing_extensions import Self

from pgmig._errors import _PgmigError

_RowT = TypeVar("_RowT", bound=BaseModel)

# The database driver to use. psycopg is the default: it is the faster driver for pgmig's
# introspection workload and is what the base package installs. asyncpg is an opt-in extra.
Driver = Literal["psycopg", "asyncpg"]
DEFAULT_DRIVER: Driver = "psycopg"


class UniqueViolation(Exception):
    """
    The DB operation failed because of a unique constraint violation.
    """


class DbConnection:
    """
    DB connection API.
    All DB interaction is done through this class to avoid the DB driver leaking into other modules.
    """

    def __init__(self, *, dsn: str, driver: Driver, conn: Any) -> None:
        self.dsn = dsn
        self.driver = driver
        self.driver_conn = conn

    @classmethod
    @asynccontextmanager
    async def connect(cls, *, dsn: str, driver: Driver = DEFAULT_DRIVER) -> AsyncIterator[Self]:
        """
        Connection context.
        """
        match driver:
            case "psycopg":
                try:
                    conn = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
                except psycopg.Error as error:
                    raise _PgmigError(f"Could not connect to database: {error}") from error

                async with conn:
                    yield cls(dsn=dsn, driver=driver, conn=conn)

            case "asyncpg":
                try:
                    conn = await asyncpg.connect(dsn)
                except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as error:
                    raise _PgmigError(f"Could not connect to database: {error}") from error

                # asyncpg returns json/jsonb as raw text by default; decode so queries that build
                # nested jsonb objects (domains, composite types, functions) parse into their models.
                for type_name in ("json", "jsonb"):
                    await conn.set_type_codec(type_name, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

                try:
                    yield cls(dsn=dsn, driver=driver, conn=conn)
                finally:
                    await conn.close()

    async def execute(self, statement: str) -> list[tuple[Any, ...]]:
        """
        Execute a statement and return the statement results, if any.
        """
        # An empty statement is a no-op. psycopg tolerates it; asyncpg raises on an empty query.
        if not statement.strip():
            return []

        match self.driver:
            case "psycopg":
                try:
                    result = await self.driver_conn.execute(statement)
                except psycopg.errors.UniqueViolation as error:
                    raise UniqueViolation(str(error)) from error

                if result.description:
                    return cast("list[tuple[Any, ...]]", await result.fetchall())
                return []

            case "asyncpg":
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
    async def connect(cls, *, dsn: str, driver: Driver = DEFAULT_DRIVER) -> AsyncIterator[Self]:
        """
        Read-only connection context.
        """
        async with super().connect(dsn=dsn, driver=driver) as conn:
            match driver:
                case "psycopg":
                    # Force all subsequent transactions to be read-only.
                    await conn.driver_conn.set_read_only(True)

                    # Use REPEATABLE READ so all introspection reads a single snapshot of the database.
                    await conn.driver_conn.set_isolation_level(psycopg.IsolationLevel.REPEATABLE_READ)

                case "asyncpg":
                    await conn.driver_conn.execute("SET default_transaction_read_only = on")
                    await conn.driver_conn.execute("SET default_transaction_isolation = 'repeatable read'")

            # Use an empty search path so introspection is independent of the database's own search
            # path: pg_get_*def()/format_type() then emit fully schema-qualified names.
            await conn.execute("SET search_path = ''")

            yield conn

    async def introspect(self, query: str, response_model: type[_RowT]) -> list[_RowT]:
        """
        Run an introspection query and parse each row into the given model.
        """
        match self.driver:
            case "psycopg":
                async with self.driver_conn.cursor(row_factory=class_row(response_model)) as cur:
                    await cur.execute(query)
                    return cast("list[_RowT]", await cur.fetchall())

            case "asyncpg":
                records = await self.driver_conn.fetch(query)
                return [response_model(**record) for record in records]
