from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, IntrospectionRowWithSchema, run_introspection_query
from pgmig._models import MaterializedView, View


class _ViewRow(IntrospectionRowWithSchema):
    relkind: str  # pg_class.relkind: 'v' view, 'm' materialized view
    view_name: str
    view_definition: str
    view_comment: str | None
    view_options: list[str] | None  # pg_class.reloptions; NULL when the view has none
    view_owner: str


async def load() -> None:
    """
    Views and materialized views (user ones only; extension-owned ones are excluded). Their
    rows share one query; the relkind routes each onto the schema's view or matview mapping.
    """
    for row in await run_introspection_query(IntrospectionQuery.VIEWS, _ViewRow):
        schema = context.db_introspection_result.schema_by_name[row.schema_name]
        # pg_get_viewdef renders the SELECT with surrounding whitespace and a trailing
        # semicolon; strip both so the stored definition is what follows "AS".
        definition = row.view_definition.strip().rstrip(";").strip()
        if row.relkind == "m":
            # A matview's reloptions are storage params (fillfactor, autovacuum_*), not the
            # view-only security/check options; they are not part of the model, so drop them.
            schema.materialized_view_by_name[row.view_name] = MaterializedView(
                name=row.view_name,
                definition=definition,
                comment=row.view_comment,
                owner=row.view_owner,
            )
        else:
            # reloptions come back in creation order; sort so comparison is order-independent.
            # trigger_by_name starts empty; the trigger loader (which runs after views) routes
            # each INSTEAD OF trigger row onto its view.
            schema.view_by_name[row.view_name] = View(
                name=row.view_name,
                definition=definition,
                comment=row.view_comment,
                options=tuple(sorted(row.view_options or [])),
                owner=row.view_owner,
            )
