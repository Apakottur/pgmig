"""
The asyncpg driver, behind the DB connection API in _db.py.
"""

import json
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import Any, Self

import asyncpg

from pgmig._drivers import DbConnInfo, DriverConnection
from pgmig._errors import PgmigDbDriverError, PgmigInvalidDbDsnError


class AsyncpgConnection(DriverConnection):
    """
    A connection through asyncpg.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn

    @classmethod
    @asynccontextmanager
    async def connect(cls, db_conn_info: DbConnInfo) -> AsyncGenerator[Self]:
        try:
            conn = await asyncpg.connect(db_conn_info.dsn)
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
            await conn.set_type_codec(type_name, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

        try:
            yield cls(conn)
        finally:
            await conn.close()

    async def execute(self, statement: str) -> list[tuple[Any, ...]]:
        # An empty statement is a no-op. asyncpg raises on an empty query.
        if not statement.strip():
            return []

        # asyncpg splits protocols: fetch() (extended) returns rows but forbids multiple
        # statements and commands that cannot run in a transaction; execute() (simple) allows
        # those but returns no rows. Reads are always single SELECT-likes; everything else is DDL.
        is_read = statement.lstrip().upper().startswith(("SELECT", "WITH", "SHOW", "VALUES", "TABLE"))
        if is_read:
            records = await self.conn.fetch(statement)
            return [tuple(record) for record in records]
        await self.conn.execute(statement)
        return []

    async def introspect(
        self, queries: Sequence[str], snapshot_setup: Sequence[str], snapshot_teardown: Sequence[str]
    ) -> list[list[dict[str, Any]]]:
        # On the first call, open the snapshot transaction. execute() uses the simple protocol, which allows
        # multiple statements in one round trip.
        if not self.conn.is_in_transaction():
            await self.conn.execute(";\n".join(snapshot_setup))

        # fetch() uses the extended protocol, which returns rows but runs a single statement, so each query is
        # its own round trip.
        rows_per_query = [[dict(record) for record in await self.conn.fetch(query)] for query in queries]

        # End the snapshot transaction, if asked to.
        if snapshot_teardown:
            await self.conn.execute(";\n".join(snapshot_teardown))

        return rows_per_query
