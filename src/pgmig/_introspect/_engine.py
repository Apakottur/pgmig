from pgmig._db import DbReadOnlyConnection
from pgmig._errors import PgmigUnsupportedError
from pgmig._introspect import (
    composite_type_dependencies,
    composite_types,
    constraints,
    domains,
    enums,
    extensions,
    functions,
    indexes,
    invalid_indexes,
    materialized_views,
    matview_dependencies,
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
_UNSUPPORTED_GUARDS: list[Guard] = [
    unsupported.check,
    matview_dependencies.check,
    invalid_indexes.check,
]

# Order is dependency-significant: schemas must exist before tables, and tables before
# the objects that attach to them (indexes, constraints, triggers). Extensions are
# database-level and independent.
_LOADERS: list[Loader] = [
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
    matview_dependencies.load,
    matview_indexes.load,
    domains.load,
    composite_types.load,
    composite_type_dependencies.load,
    extensions.load,
]


async def introspect_db(dsn: str) -> DbIntrospectionResult:
    """
    Build the full structure of the given database.
    """
    db_introspection_result = DbIntrospectionResult(
        schema_by_name={},
        extension_by_name={},
        view_dependencies={},
        matview_dependencies={},
        view_column_dependencies={},
        composite_type_dependencies={},
    )

    async with DbReadOnlyConnection.connect(dsn=dsn) as conn:
        # Run within the introspection context.
        with context.context_scope(
            conn=conn,
            db_introspection_result=db_introspection_result,
        ):
            # Run all the introspection on a single snapshot.
            async with conn.snapshot():  # pragma: no branch
                # Look for any unsupported state.
                all_findings = [finding for guard in _UNSUPPORTED_GUARDS for finding in await guard()]
                if all_findings:
                    message = "pgmig cannot process this database:\n" + "\n".join(
                        f"  - {finding}" for finding in all_findings
                    )
                    raise PgmigUnsupportedError(message)

                # Run all the introspections.
                for load in _LOADERS:
                    await load()

    return db_introspection_result
