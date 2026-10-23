from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement
from pgmig._diff._view_kinds import ViewKind, generate_view_kind
from pgmig._models import MaterializedView


def _create_sql(qualified_name: str, matview: MaterializedView) -> str:
    return f"CREATE MATERIALIZED VIEW {qualified_name} AS {matview.definition} WITH NO DATA;"


_KIND = ViewKind(
    keyword="MATERIALIZED VIEW",
    select=lambda schema: schema.materialized_view_by_name,
    dependencies=lambda db_introspection_result: db_introspection_result.matview_dependencies,
    recreated=lambda: context().recreated_matview_keys,
    create_sql=_create_sql,
    drop_phase=Phase.MATVIEW_DROP,
    create_phase=Phase.MATVIEW_CREATE,
)


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of materialized views, ordered by their dependencies.

    Creates run in MATVIEW_CREATE (after VIEW_CREATE, so any plain view a matview reads already
    exists) in dependency-first order; drops run in MATVIEW_DROP (before VIEW_DROP, so a matview
    is gone before the view it reads) in dependent-first order. Matview-on-view ordering is thus
    a phase invariant; matview-on-matview ordering is the topological sort here. Creates use
    WITH NO DATA (the matview is unpopulated and the user runs REFRESH themselves).

    A changed definition is a drop-and-recreate (there is no CREATE OR REPLACE MATERIALIZED
    VIEW); so is reading a retyped table column, or reading a view/matview that is itself
    recreated. recreated_matview_keys is the single source of truth for that decision, shared
    with the matview-index differ so both agree on which matviews are recreated.
    """
    return generate_view_kind(_KIND)
