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
    view_dependencies,
    views,
)
from pgmig._build._core import Guard, Loader
from pgmig._errors import PgmigError
from pgmig._models import DbInfo

# Preconditions run before any loader. Each guard reports every object it finds that
# pgmig cannot process; all findings are collected and reported together, so the user
# sees every problem at once instead of one per re-run.
_GUARDS: tuple[Guard, ...] = (
    unsupported.check,
    invalid_indexes.check,
    view_dependencies.check,
    matview_indexes.check,
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
    materialized_views.load,
    domains.load,
    composite_types.load,
    extensions.load,
)


def build_db_info(dsn: str) -> DbInfo:
    """
    Build the full structure of the given database.
    """
    # Open the connection.
    try:
        conn = psycopg.connect(
            dsn,
            options=(
                # The database is read-only, so we can avoid unnecessary writes.
                "-c default_transaction_read_only=on"
                # REPEATABLE READ takes a single catalog snapshot at the first query and holds it for
                # the whole transaction, so all loaders below see one frozen instant. Without it, each
                # statement gets its own snapshot (READ COMMITTED), and concurrent DDL between loaders
                # could produce a torn view (e.g. a constraint row for a table tables.load never saw).
                " -c default_transaction_isolation=repeatable\\ read"
                # The empty search_path makes introspection independent of the database's own
                # search_path and forces the deparse functions (format_type, pg_get_expr,
                # pg_get_constraintdef, pg_get_indexdef, ...) to fully qualify every name, so the
                # emitted SQL is deterministic and portable regardless of the runner's search_path.
                " -c search_path="
            ),
        )
    except psycopg.Error as error:
        raise PgmigError(f"Could not connect to database: {error}") from error

    with conn:
        # Run every guard first and collect all findings, so a database with several
        # problems reports them together rather than one failure per re-run.
        problems = [finding for guard in _GUARDS for finding in guard(conn)]
        if problems:
            raise PgmigError(
                "pgmig cannot process this database:\n" + "\n".join(f"  - {problem}" for problem in problems)
            )

        db_info = DbInfo(schema_by_name={}, extension_by_name={})
        for load in _LOADERS:
            load(conn, db_info)
    return db_info
