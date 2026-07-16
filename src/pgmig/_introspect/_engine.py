import json

import asyncpg

from pgmig._errors import PgmigUnsupportedError, _PgmigError
from pgmig._introspect import (
    composite_types,
    constraints,
    domains,
    enums,
    extensions,
    functions,
    indexes,
    invalid_indexes,
    materialized_views,
    matview_indexes,
    schemas,
    sequences,
    tables,
    triggers,
    unsupported,
    view_column_dependencies,
    view_dependencies,
    views,
)
from pgmig._introspect._context import context
from pgmig._introspect._core import Guard, Loader
from pgmig._models import DbIntrospectionResult

# Preconditions run before any loader. Each guard reports every object it finds that
# pgmig cannot process; all findings are collected and reported together, so the user
# sees every problem at once instead of one per re-run.
_UNSUPPORTED_GUARDS: tuple[Guard, ...] = (
    unsupported.check,
    view_dependencies.check,
    invalid_indexes.check,
)

# Order is dependency-significant: schemas must exist before tables, and tables before
# the objects that attach to them (indexes, constraints, triggers). Extensions are
# database-level and independent.
_LOADERS: tuple[Loader, ...] = (
    schemas.load,
    tables.load,
    indexes.load,
    constraints.load,
    sequences.load,
    functions.load,
    triggers.load,
    enums.load,
    views.load,
    view_dependencies.load,
    view_column_dependencies.load,
    materialized_views.load,
    matview_indexes.load,
    domains.load,
    composite_types.load,
    extensions.load,
)


async def _connect(dsn: str) -> asyncpg.Connection:
    """
    Create the introspection connection.
    """
    try:
        conn = await asyncpg.connect(dsn)
    except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as error:
        raise _PgmigError(f"Could not connect to database: {error}") from error

    # asyncpg returns json/jsonb as raw text by default; decode so queries that build nested
    # jsonb objects (domains, composite types, functions) parse straight into their models.
    for type_name in ("json", "jsonb"):
        await conn.set_type_codec(
            type_name, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    # Force all subsequent transactions to be read-only.
    await conn.execute("SET default_transaction_read_only = on")

    # Use REPEATABLE READ so that all introspection is done on a single snapshot of the database.
    await conn.execute("SET default_transaction_isolation = 'repeatable read'")

    # Return the connection.
    return conn


async def introspect_db(dsn: str) -> DbIntrospectionResult:
    """
    Build the full structure of the given database.
    """
    db_introspection_result = DbIntrospectionResult(
        schema_by_name={}, extension_by_name={}, view_dependencies={}, view_column_dependencies={}
    )
    conn = await _connect(dsn)
    try:
        with context.context_scope(conn=conn, db_introspection_result=db_introspection_result):
            # REPEATABLE READ transaction so all introspection reads a single snapshot.
            async with conn.transaction():
                # Use an empty search path to make introspection independent of the database's own search path.
                await conn.execute("SET LOCAL search_path = ''")

                # Get all the unsupported findings.
                all_findings = [finding for guard in _UNSUPPORTED_GUARDS for finding in await guard()]
                if all_findings:
                    message = "pgmig cannot process this database:\n" + "\n".join(
                        f"  - {finding}" for finding in all_findings
                    )
                    raise PgmigUnsupportedError(message)

                for load in _LOADERS:
                    await load()
    finally:
        await conn.close()
    return db_introspection_result
