from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement
from pgmig._diff._view_kinds import ViewKind, generate_view_kind
from pgmig._models import View


def _create_sql(qualified_name: str, view: View) -> str:
    # security_invoker, security_barrier and check_option (WITH CHECK OPTION) all live in
    # reloptions; emit them verbatim in a WITH (...) clause between the name and AS.
    with_clause = f" WITH ({', '.join(view.options)})" if view.options else ""
    return f"CREATE VIEW {qualified_name}{with_clause} AS {view.definition};"


_KIND = ViewKind(
    keyword="VIEW",
    select=lambda schema: schema.view_by_name,
    dependencies=lambda db_introspection_result: db_introspection_result.view_dependencies,
    recreated=lambda: context().recreated_view_keys,
    create_sql=_create_sql,
    drop_phase=Phase.VIEW_DROP,
    create_phase=Phase.VIEW_CREATE,
)


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of views, ordered by their view-on-view dependencies.

    Creates run in the VIEW_CREATE phase in dependency-first order; drops run in the
    VIEW_DROP phase in dependent-first order. A changed definition (or option set) is a
    drop-and-recreate, and every view that transitively reads a recreated one is dragged into
    the recreate set (see recreated_view_keys) -- Postgres refuses to drop a view another view
    still reads, and the dependents must be rebuilt afterwards.
    """
    return generate_view_kind(_KIND)
