from collections.abc import Sequence

from pgmig._db import DbConnInfo, DbReadOnlyConnection
from pgmig._errors import PgmigUnsupportedError
from pgmig._introspect._context import ContextData, context_scope
from pgmig._introspect._core import IntrospectionQuery, run_introspection_queries
from pgmig._introspect.preflight import PreflightRow
from pgmig._models import DbIntrospectionResult


def _get_guards(preflight: PreflightRow) -> list[IntrospectionQuery]:
    """
    Get the guard queries to run before any loader.
    """
    guards = [IntrospectionQuery.UNSUPPORTED]
    if preflight.has_matviews:
        guards.append(IntrospectionQuery.MATVIEW_DEPENDENCIES)
    if preflight.has_indexes:
        guards.append(IntrospectionQuery.INVALID_INDEXES)
    return guards


def _get_loaders(preflight: PreflightRow) -> list[IntrospectionQuery]:
    """
    Get the loader queries to run, in dependency-significant order.
    """
    loaders = [IntrospectionQuery.SCHEMAS]
    if preflight.has_tables:
        loaders.append(IntrospectionQuery.TABLES)
    if preflight.has_indexes:
        loaders.append(IntrospectionQuery.INDEXES)
    if preflight.has_constraints:
        loaders.append(IntrospectionQuery.CONSTRAINTS)
    if preflight.has_sequences:
        loaders.append(IntrospectionQuery.SEQUENCES)
    if preflight.has_functions:
        loaders.append(IntrospectionQuery.FUNCTIONS)
    if preflight.has_enums:
        loaders.append(IntrospectionQuery.ENUMS)
        # Enum-on-column edges: only meaningful when there are also tables to depend on it.
        if preflight.has_tables:
            loaders.append(IntrospectionQuery.ENUM_DEPENDENCIES)
    # One query loads both views and matviews, so it runs when either kind is present.
    if preflight.has_views or preflight.has_matviews:
        loaders.append(IntrospectionQuery.VIEWS)
    if preflight.has_views:
        loaders.append(IntrospectionQuery.VIEW_DEPENDENCIES)
    # Triggers load after both tables and views: an INSTEAD OF trigger's owner is a view,
    # and the loader routes each trigger onto its table or view, so both must exist first.
    if preflight.has_triggers:
        loaders.append(IntrospectionQuery.TRIGGERS)
    # Policies attach to tables, so their loader runs after the tables one.
    if preflight.has_policies:
        loaders.append(IntrospectionQuery.POLICIES)
    if preflight.has_views or preflight.has_matviews:
        loaders.append(IntrospectionQuery.VIEW_COLUMN_DEPENDENCIES)
    if preflight.has_matviews:
        loaders.append(IntrospectionQuery.MATVIEW_INDEXES)
    if preflight.has_domains:
        loaders.append(IntrospectionQuery.DOMAINS)
    if preflight.has_composite_types:
        loaders += [IntrospectionQuery.COMPOSITE_TYPES, IntrospectionQuery.COMPOSITE_TYPE_DEPENDENCIES]
    if preflight.has_range_types:
        loaders.append(IntrospectionQuery.RANGE_TYPES)
    loaders.append(IntrospectionQuery.EXTENSIONS)
    loaders.append(IntrospectionQuery.DEFAULT_PRIVILEGES)
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
                [connections] = await run_introspection_queries([IntrospectionQuery.SCHEMA_CONNECTIONS])
                if connections:
                    message = (
                        "pgmig cannot ignore a schema that is connected to a kept schema "
                        "(the migration would fail at apply):\n"
                        + "\n".join(f"  - {finding}" for finding in connections)
                    )
                    raise PgmigUnsupportedError(message)

            # Run the preflight query to find out which introspection queries to run.
            [preflight] = await run_introspection_queries([IntrospectionQuery.PREFLIGHT])

            # Look for any unsupported objects.
            all_findings = [
                finding for findings in await run_introspection_queries(_get_guards(preflight)) for finding in findings
            ]
            if all_findings:
                message = "pgmig cannot process this database:\n" + "\n".join(
                    f"  - {finding}" for finding in all_findings
                )
                raise PgmigUnsupportedError(message)

            # Run the introspections for the classes the database actually contains.
            await run_introspection_queries(_get_loaders(preflight))

    return db_introspection_result
