import psycopg

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


def build_db_info(dsn: str) -> DbInfo:
    """
    Build the full structure of the given database.
    """
    # Open the connection, surfacing connection failures as a clean PgmigError.
    # An empty search_path makes introspection independent of the database's own
    # search_path and forces the deparse functions (format_type, pg_get_expr,
    # pg_get_constraintdef, pg_get_indexdef, ...) to fully qualify every name, so the
    # emitted SQL is deterministic and portable regardless of the runner's search_path.
    try:
        conn = psycopg.connect(dsn, options="-c default_transaction_read_only=on -c search_path=")
    except psycopg.Error as error:
        raise PgmigError(f"Could not connect to database: {error}") from error

    db_info = DbInfo(schema_by_name={}, extension_by_name={})
    with conn:
        for load in _LOADERS:
            load(conn, db_info)
    return db_info
