"""
The psycopg driver, behind the DB connection API in _db.py.
"""

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg import pq
from psycopg.rows import dict_row

from pgmig._errors import PgmigDbDriverError, PgmigInvalidDbDsnError

if TYPE_CHECKING:
    from pgmig._db import DbConnInfo


@asynccontextmanager
async def connect(db_conn_info: "DbConnInfo") -> AsyncGenerator[psycopg.AsyncConnection[Any]]:
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
        yield conn


async def execute(conn: psycopg.AsyncConnection[Any], statement: str) -> list[tuple[Any, ...]]:
    """
    Execute a statement and return the statement results, if any.
    """
    # Execute the statement.
    result = await conn.execute(statement)  # ty: ignore[no-matching-overload]

    # Fetch and return the results, if any.
    if result.description:
        return await result.fetchall()
    return []


async def introspect(
    conn: psycopg.AsyncConnection[Any], queries: Sequence[str], snapshot_setup: Sequence[str]
) -> list[list[dict[str, Any]]]:
    """
    Run the given introspection queries in a single round trip, returning the rows of each one.
    """
    # On the first call, also open the snapshot transaction, in the same round trip as the queries.
    statements = list(queries)
    if conn.info.transaction_status == pq.TransactionStatus.IDLE:
        statements = [*snapshot_setup, *statements]

    async with conn.cursor(row_factory=dict_row) as cur:
        # Run all the statements as one multi-statement execute. Each statement produces its own result set.
        await cur.execute("\n;\n".join(statements))  # ty: ignore[no-matching-overload]

        # Fetch the rows of each query result set. The setup statements return no rows, so their sets are skipped.
        return [await result.fetchall() async for result in cur.results() if result.description is not None]
