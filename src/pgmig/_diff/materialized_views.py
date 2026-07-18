from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import (
    Phase,
    Statement,
    collect_relations,
    ctx_iter_schema_pairs,
    diff_comment_statements,
    owner_statements,
    recreated_matview_keys,
    topological_sort,
)
from pgmig._keys import RelationKey
from pgmig._sql import qualified


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
    source, target = context.source, context.target
    src_matviews = collect_relations(source, lambda schema: schema.materialized_view_by_name, RelationKey)
    dst_matviews = collect_relations(target, lambda schema: schema.materialized_view_by_name, RelationKey)

    recreate = recreated_matview_keys()
    drop_only = src_matviews.keys() - dst_matviews.keys()
    create_only = dst_matviews.keys() - src_matviews.keys()

    # Drops: dependent-first, so reverse the source graph's dependency-first order.
    drops = drop_only | recreate
    for key in reversed(topological_sort(drops, source.matview_dependencies)):
        yield Statement(Phase.MATVIEW_DROP, f"DROP MATERIALIZED VIEW {qualified(key.schema, key.name)};")

    # Creates: dependency-first over the target graph.
    creates = create_only | recreate
    for key in topological_sort(creates, target.matview_dependencies):
        matview = dst_matviews[key]
        yield Statement(
            Phase.MATVIEW_CREATE,
            f"CREATE MATERIALIZED VIEW {qualified(key.schema, key.name)} AS {matview.definition} WITH NO DATA;",
        )

    # Ownership, for a matview present unchanged on both sides. A recreated matview is skipped:
    # its rebuilt instance is owned by the migration runner and reconciles on a later run.
    for key in sorted(src_matviews.keys() & dst_matviews.keys(), key=lambda k: (k.schema, k.name)):
        if key in recreate:
            continue
        for sql in owner_statements(
            "MATERIALIZED VIEW", qualified(key.schema, key.name), src_matviews[key].owner, dst_matviews[key].owner
        ):
            yield Statement(Phase.MATVIEW_CREATE, sql)

    # Comments, after the matviews they annotate exist. A recreated matview re-emits its comment
    # (the drop reset it), so pass the recreated names per schema.
    for schema_name, src_schema, dst_schema in ctx_iter_schema_pairs():
        src_schema_matviews = src_schema.materialized_view_by_name if src_schema else {}
        dst_schema_matviews = dst_schema.materialized_view_by_name if dst_schema else {}
        recreated_names = {key.name for key in recreate if key.schema == schema_name}
        for sql in diff_comment_statements(
            schema_name, src_schema_matviews, dst_schema_matviews, kind="MATERIALIZED VIEW", recreated=recreated_names
        ):
            yield Statement(Phase.MATVIEW_CREATE, sql)
