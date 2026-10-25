from collections.abc import Sequence
from typing import Any

from pgmig._db import DbConnInfo, DbReadOnlyConnection
from pgmig._errors import PgmigUnsupportedError
from pgmig._introspect import (
    composite_type_dependencies,
    composite_types,
    constraints,
    default_privileges,
    domains,
    enum_dependencies,
    enums,
    event_triggers,
    extensions,
    functions,
    indexes,
    invalid_indexes,
    matview_dependencies,
    matview_indexes,
    policies,
    range_types,
    schema_connections,
    schemas,
    sequences,
    tables,
    triggers,
    unsupported,
    view_column_dependencies,
    view_dependencies,
    views,
)
from pgmig._introspect._context import ContextData, context_scope
from pgmig._introspect._core import Guard, Loader, run_introspection_queries, run_introspection_query
from pgmig._introspect.preflight import PreflightQuery, PreflightRow
from pgmig._models import DbIntrospectionResult


def _get_guards(preflight: PreflightRow) -> list[type[Guard[Any]]]:
    """
    Get the guards to run before any loader.
    """
    guards: list[type[Guard[Any]]] = [unsupported.UnsupportedGuard]
    if preflight.has_matviews:
        guards.append(matview_dependencies.MatviewDependenciesGuard)
    if preflight.has_indexes:
        guards.append(invalid_indexes.InvalidIndexesGuard)
    return guards


def _get_loaders(preflight: PreflightRow) -> list[type[Loader[Any]]]:
    """
    Get the loaders to run, in dependency-significant order.
    """
    loaders: list[type[Loader[Any]]] = [schemas.SchemasLoader]
    if preflight.has_tables:
        loaders.append(tables.TablesLoader)
    if preflight.has_indexes:
        loaders.append(indexes.IndexesLoader)
    if preflight.has_constraints:
        loaders.append(constraints.ConstraintsLoader)
    if preflight.has_sequences:
        loaders.append(sequences.SequencesLoader)
    if preflight.has_functions:
        loaders.append(functions.FunctionsLoader)
    if preflight.has_enums:
        loaders.append(enums.EnumsLoader)
        # Enum-on-column edges: only meaningful when there are also tables to depend on it.
        if preflight.has_tables:
            loaders.append(enum_dependencies.EnumDependenciesLoader)
    # One query loads both views and matviews, so it runs when either kind is present.
    if preflight.has_views or preflight.has_matviews:
        loaders.append(views.ViewsLoader)
    if preflight.has_views:
        loaders.append(view_dependencies.ViewDependenciesLoader)
    # Triggers load after both tables and views: an INSTEAD OF trigger's owner is a view,
    # and the loader routes each trigger onto its table or view, so both must exist first.
    if preflight.has_triggers:
        loaders.append(triggers.TriggersLoader)
    if preflight.has_event_triggers:
        loaders.append(event_triggers.EventTriggersLoader)
    # Policies attach to tables, so their loader runs after the tables loader.
    if preflight.has_policies:
        loaders.append(policies.PoliciesLoader)
    if preflight.has_views or preflight.has_matviews:
        loaders.append(view_column_dependencies.ViewColumnDependenciesLoader)
    if preflight.has_matviews:
        loaders.append(matview_indexes.MatviewIndexesLoader)
    if preflight.has_domains:
        loaders.append(domains.DomainsLoader)
    if preflight.has_composite_types:
        loaders += [
            composite_types.CompositeTypesLoader,
            composite_type_dependencies.CompositeTypeDependenciesLoader,
        ]
    if preflight.has_range_types:
        loaders.append(range_types.RangeTypesLoader)
    loaders.append(extensions.ExtensionsLoader)
    loaders.append(default_privileges.DefaultPrivilegesLoader)
    return loaders


async def introspect_db(*, db_conn_info: DbConnInfo, ignore_schemas: Sequence[str] = ()) -> DbIntrospectionResult:
    """
    Run the database introspection for the given database.

    Returns the full introspection result.
    """
    # Initialize the introspection result.
    db_introspection_result = DbIntrospectionResult()

    async with DbReadOnlyConnection.connect(db_conn_info=db_conn_info) as conn:
        # Run within the introspection context.
        data = ContextData(
            conn=conn, db_introspection_result=db_introspection_result, ignore_schemas=frozenset(ignore_schemas)
        )
        with context_scope(data):
            # Verify that the ignored schemas are isolated from the kept ones.
            if ignore_schemas:
                connections = await run_introspection_query(schema_connections.SchemaConnectionsGuard)
                if connections:
                    message = (
                        "pgmig cannot ignore a schema that is connected to a kept schema "
                        "(the migration would fail at apply):\n"
                        + "\n".join(f"  - {finding}" for finding in connections)
                    )
                    raise PgmigUnsupportedError(message)

            # Run the preflight query to find out which introspection steps to run.
            preflight = await run_introspection_query(PreflightQuery)

            # Look for any unsupported objects, running the guards as one batch.
            all_findings = []
            for findings in await run_introspection_queries(_get_guards(preflight)):
                all_findings += findings
            if all_findings:
                message = "pgmig cannot process this database:\n" + "\n".join(
                    f"  - {finding}" for finding in all_findings
                )
                raise PgmigUnsupportedError(message)

            # Run the introspections for the classes the database actually contains, as one batch.
            await run_introspection_queries(_get_loaders(preflight))

    return db_introspection_result
