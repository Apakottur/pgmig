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
    range_types,
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


class _IntrospectionPreflight(_QueryRow):
    """
    Results of the introspection preflight query.
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
    has_range_types: bool

    def get_guards(self) -> list[Guard]:
        """
        Get the guards to run before any loader.
        """
        guards: list[Guard] = [unsupported.check]
        if self.has_matviews:
            guards.append(matview_dependencies.check)
        if self.has_indexes:
            guards.append(invalid_indexes.check)
        return guards

    def get_loaders(self) -> list[Loader]:
        """
        Get the loaders to run, in dependency-significant order.
        """
        loaders: list[Loader] = [schemas.load]
        if self.has_tables:
            loaders.append(tables.load)
        if self.has_indexes:
            loaders.append(indexes.load)
        if self.has_constraints:
            loaders.append(constraints.load)
        if self.has_sequences:
            loaders.append(sequences.load)
        if self.has_functions:
            loaders.append(functions.load)
        if self.has_enums:
            loaders.append(enums.load)
        if self.has_views:
            loaders += [views.load, view_dependencies.load]
        # Triggers load after both tables and views: an INSTEAD OF trigger's owner is a view,
        # and the loader routes each trigger onto its table or view, so both must exist first.
        if self.has_triggers:
            loaders.append(triggers.load)
        if self.has_views or self.has_matviews:
            loaders.append(view_column_dependencies.load)
        if self.has_matviews:
            loaders += [materialized_views.load, matview_dependencies.load, matview_indexes.load]
        if self.has_domains:
            loaders.append(domains.load)
        if self.has_composite_types:
            loaders += [composite_types.load, composite_type_dependencies.load]
        if self.has_range_types:
            loaders.append(range_types.load)
        loaders.append(extensions.load)
        return loaders


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
            # Run the preflight query to find out which introspection steps to run.
            preflight_result = await run_introspection_query("preflight.sql", _IntrospectionPreflight)
            preflight = preflight_result[0]

            # Look for any unsupported state.
            all_findings = [finding for guard in preflight.get_guards() for finding in await guard()]
            if all_findings:
                message = "pgmig cannot process this database:\n" + "\n".join(
                    f"  - {finding}" for finding in all_findings
                )
                raise PgmigUnsupportedError(message)

            # Run the introspections for the classes the database actually contains.
            for load in preflight.get_loaders():
                await load()

    return db_introspection_result
