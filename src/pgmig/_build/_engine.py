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
from pgmig._errors import _PgmigError, PgmigUnsupportedChangeError
from pgmig._models import DbInfo

# Preconditions run before any loader. Each guard reports every object it finds that
# pgmig cannot process; all findings are collected and reported together, so the user
# sees every problem at once instead of one per re-run.
#
# Guards are split by what their findings mean. An unsupported guard reports a documented
# limitation (an object kind pgmig does not model yet) and raises UnsupportedChangeError.
# An error guard reports a hard precondition the user must fix (e.g. a leftover invalid
# index) -- not a limitation -- and raises the plain PgmigError.
_UNSUPPORTED_GUARDS: tuple[Guard, ...] = (
    unsupported.check,
    view_dependencies.check,
)
_ERROR_GUARDS: tuple[Guard, ...] = (invalid_indexes.check,)

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
    Open the introspection connection and configure the session at the transaction level.

    We should never use server-side startup options (-c ...): pgbouncer rejects unknown startup
    parameters ("unsupported startup parameter in options: ...") and would block every
    connection made through it.
    """
    try:
        conn = psycopg.connect(dsn)
    except psycopg.Error as error:
        raise _PgmigError(f"Could not connect to database: {error}") from error

    # Force all subsequent transactions to be read-only.
    conn.read_only = True

    # Use REPEATABLE READ so that all introspection is done on a single snapshot of the database.
    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    return conn


def build_db_info(dsn: str) -> DbInfo:
    """
    Build the full structure of the given database.
    """
    conn = _connect(dsn)

    with conn:
        # Use an empty search path to make introspection independent of the database's own search path.
        conn.execute("SET LOCAL search_path = ''")

        # Run every guard first and collect all findings, so a database with several
        # problems reports them together rather than one failure per re-run.
        error_problems = [finding for guard in _ERROR_GUARDS for finding in guard(conn)]
        unsupported_problems = [finding for guard in _UNSUPPORTED_GUARDS for finding in guard(conn)]
        problems = error_problems + unsupported_problems
        if problems:
            message = "pgmig cannot process this database:\n" + "\n".join(f"  - {problem}" for problem in problems)
            # A hard precondition error takes precedence: it is not a limitation, so the
            # combined report surfaces as a plain PgmigError. A database whose only problems
            # are unsupported objects raises the more specific UnsupportedChangeError.
            if error_problems:
                raise _PgmigError(message)
            raise PgmigUnsupportedChangeError(message)

        db_info = DbInfo(
            schema_by_name={}, extension_by_name={}, view_dependencies={}, view_column_dependencies={}
        )
        for load in _LOADERS:
            load(conn, db_info)
    return db_info
