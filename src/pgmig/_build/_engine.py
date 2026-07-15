from typing import Any

import psycopg

from pgmig._build import (
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
from pgmig._build._core import Guard, Loader
from pgmig._errors import _PgmigError, PgmigUnsupportedError
from pgmig._models import DbInfo

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


def _connect(dsn: str) -> psycopg.Connection[Any]:
    """
    Create the introspection connection.
    """
    try:
        conn = psycopg.connect(dsn)
    except psycopg.Error as error:
        raise _PgmigError(f"Could not connect to database: {error}") from error

    # Force all subsequent transactions to be read-only.
    conn.read_only = True

    # Use REPEATABLE READ so that all introspection is done on a single snapshot of the database.
    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ

    # Return the connection.
    return conn


def build_db_info(dsn: str) -> DbInfo:
    """
    Build the full structure of the given database.
    """
    with  _connect(dsn) as conn:
        # Use an empty search path to make introspection independent of the database's own search path.
        conn.execute("SET LOCAL search_path = ''")

        # Get all the unsupported findings.
        all_findings = [finding for guard in _UNSUPPORTED_GUARDS for finding in guard(conn)]
        if all_findings:
            message = "pgmig cannot process this database:\n" + "\n".join(f"  - {finding}" for finding in all_findings)
            raise PgmigUnsupportedError(message)

        db_info = DbInfo(
            schema_by_name={}, extension_by_name={}, view_dependencies={}, view_column_dependencies={},


        )
        for load in _LOADERS:
            load(conn, db_info)
    return db_info
