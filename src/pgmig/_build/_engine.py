import asyncio

import asyncpg

from pgmig._build import (
    constraints,
    enums,
    extensions,
    functions,
    indexes,
    schemas,
    sequences,
    tables,
    triggers,
    unsupported,
)
from pgmig._build._core import Loader
from pgmig._errors import PgmigError
from pgmig._models import DbInfo

# Order is dependency-significant: schemas must exist before tables, and tables before
# the objects that attach to them (indexes, constraints, triggers). Extensions are
# database-level and independent. The unsupported-relkind guard runs first so a
# relation that is not modelled yet (view, materialized view, partitioned or foreign
# table) raises before any partial introspection.
_LOADERS: tuple[Loader, ...] = (
    unsupported.load,
    schemas.load,
    tables.load,
    indexes.load,
    constraints.load,
    sequences.load,
    functions.load,
    triggers.load,
    enums.load,
    extensions.load,
)


async def _build_db_info(dsn: str) -> DbInfo:
    """
    Build the full structure of the given database (async core).
    """
    # Open the connection, surfacing connection failures as a clean PgmigError.
    try:
        conn = await asyncpg.connect(dsn, server_settings={"default_transaction_read_only": "on"})
    except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as error:
        raise PgmigError(f"Could not connect to database: {error}") from error

    db_info = DbInfo(schema_by_name={}, extension_by_name={})
    try:
        for load in _LOADERS:
            await load(conn, db_info)
    finally:
        await conn.close()
    return db_info


def build_db_info(dsn: str) -> DbInfo:
    """
    Build the full structure of the given database.
    """
    return asyncio.run(_build_db_info(dsn))
