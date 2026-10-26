"""
The asyncpg driver, behind the DB connection API in _db.py.

asyncpg is an optional extra, so _db.py imports this module only when the driver is selected.
"""

import json
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import asyncpg

from pgmig._errors import PgmigDbDriverError, PgmigInvalidDbDsnError

if TYPE_CHECKING:
    from pgmig._db import DbConnInfo


@asynccontextmanager
async def connect(db_conn_info: "DbConnInfo") -> AsyncGenerator[asyncpg.Connection]:
    """
    Connection context.
    """
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
        yield conn
    finally:
        await conn.close()


async def execute(conn: asyncpg.Connection, statement: str) -> list[tuple[Any, ...]]:
    """
    Execute a statement and return the statement results, if any.
    """
    # An empty statement is a no-op. asyncpg raises on an empty query.
    if not statement.strip():
        return []

    # asyncpg splits protocols: fetch() (extended) returns rows but forbids multiple
    # statements and commands that cannot run in a transaction; execute() (simple) allows
    # those but returns no rows. Reads are always single SELECT-likes; everything else is DDL.
    is_read = statement.lstrip().upper().startswith(("SELECT", "WITH", "SHOW", "VALUES", "TABLE"))
    if is_read:
        records = await conn.fetch(statement)
        return [tuple(record) for record in records]
    await conn.execute(statement)
    return []


async def introspect(
    conn: asyncpg.Connection, queries: Sequence[str], snapshot_setup: Sequence[str]
) -> list[list[dict[str, Any]]]:
    """
    Run the given introspection queries, returning the rows of each one.
    """
    # On the first call, open the snapshot transaction. execute() uses the simple protocol, which allows
    # multiple statements in one round trip.
    if not conn.is_in_transaction():
        await conn.execute(";\n".join(snapshot_setup))

    # fetch() uses the extended protocol, which returns rows but runs a single statement, so each query is
    # its own round trip.
    return [[dict(record) for record in await conn.fetch(query)] for query in queries]
