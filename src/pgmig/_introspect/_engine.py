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
from pgmig._introspect._core import Guard, Loader, _QueryRow, run_introspection_query
from pgmig._models import DbIntrospectionResult


class _Presence(_QueryRow):
    """
    One boolean per object class saying whether the database contains any of it. Loaders and
    guards for an absent class are skipped, avoiding their (planning-heavy) catalog query.
    """

    has_tables: bool
    has_views: bool
    has_matviews: bool
    has_indexes: bool
    has_constraints: bool
    has_sequences: bool
    has_functions: bool
    has_triggers: bool
    has_enums: bool
    has_domains: bool
    has_composite_types: bool


# Preconditions run before any loader. Each guard reports every object it finds that
# pgmig cannot process; all findings are collected and reported together, so the user
# sees every problem at once instead of one per re-run. Each entry pairs a guard with the
# presence flags gating it; an empty tuple always runs, otherwise it runs when any flag is
# set. `unsupported` scans object kinds outside the presence probe, so it must always run;
# the other two only apply to a class the probe reports, so they skip when it is absent.
_GUARDS: list[tuple[Guard, tuple[str, ...]]] = [
    (unsupported.check, ()),
    (matview_dependencies.check, ("has_matviews",)),
    (invalid_indexes.check, ("has_indexes",)),
]

# Order is dependency-significant: schemas must exist before tables, and tables before
# the objects that attach to them (indexes, constraints, triggers). Extensions are
# database-level and independent. Each entry pairs a loader with the presence flags gating
# it; an empty tuple always runs (schemas and extensions are near-universal and cheap),
# otherwise the loader runs when any listed flag is set. view_column_dependencies spans
# both views and materialized views (relkind 'v' and 'm'), so it is gated on either.
_LOADERS: list[tuple[Loader, tuple[str, ...]]] = [
    (schemas.load, ()),
    (tables.load, ("has_tables",)),
    (indexes.load, ("has_indexes",)),
    (constraints.load, ("has_constraints",)),
    (sequences.load, ("has_sequences",)),
    (functions.load, ("has_functions",)),
    (triggers.load, ("has_triggers",)),
    (enums.load, ("has_enums",)),
    (views.load, ("has_views",)),
    (view_dependencies.load, ("has_views",)),
    (view_column_dependencies.load, ("has_views", "has_matviews")),
    (materialized_views.load, ("has_matviews",)),
    (matview_dependencies.load, ("has_matviews",)),
    (matview_indexes.load, ("has_matviews",)),
    (domains.load, ("has_domains",)),
    (composite_types.load, ("has_composite_types",)),
    (composite_type_dependencies.load, ("has_composite_types",)),
    (extensions.load, ()),
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
            # Probe once for which object classes exist, so absent ones skip their loader.
            presence = (await run_introspection_query("presence.sql", _Presence))[0]

            # Look for any unsupported state.
            all_findings = [
                finding
                for guard, flags in _GUARDS
                if not flags or any(getattr(presence, flag) for flag in flags)
                for finding in await guard()
            ]
            if all_findings:
                message = "pgmig cannot process this database:\n" + "\n".join(
                    f"  - {finding}" for finding in all_findings
                )
                raise PgmigUnsupportedError(message)

            # Run the introspections for the classes the database actually contains.
            for load, flags in _LOADERS:
                if not flags or any(getattr(presence, flag) for flag in flags):
                    await load()

    return db_introspection_result
