from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import (
    Phase,
    Statement,
    collect_relations,
    ctx_iter_schema_pairs,
    diff_comment_statements,
    recreated_view_keys,
    topological_sort,
)
from pgmig._sql import qualified


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of views, ordered by their view-on-view dependencies.

    Creates run in the VIEW_CREATE phase in dependency-first order; drops run in the
    VIEW_DROP phase in dependent-first order. A changed definition (or option set) is a
    drop-and-recreate, and every view that transitively reads a recreated one is dragged into
    the recreate set (see recreated_view_keys) -- Postgres refuses to drop a view another view
    still reads, and the dependents must be rebuilt afterwards.
    """
    source, target = context.source, context.target
    src_views = collect_relations(source, lambda schema: schema.view_by_name)
    dst_views = collect_relations(target, lambda schema: schema.view_by_name)

    recreate = recreated_view_keys()
    drop_only = src_views.keys() - dst_views.keys()
    create_only = dst_views.keys() - src_views.keys()

    # Drops: dependent-first, so reverse the source graph's dependency-first order.
    drops = drop_only | recreate
    for key in reversed(topological_sort(drops, source.view_dependencies)):
        yield Statement(Phase.VIEW_DROP, f"DROP VIEW {qualified(key.schema, key.name)};")

    # Creates: dependency-first over the target graph.
    creates = create_only | recreate
    for key in topological_sort(creates, target.view_dependencies):
        view = dst_views[key]
        # security_invoker, security_barrier and check_option (WITH CHECK OPTION) all live in
        # reloptions; emit them verbatim in a WITH (...) clause between the name and AS.
        with_clause = f" WITH ({', '.join(view.options)})" if view.options else ""
        yield Statement(
            Phase.VIEW_CREATE,
            f"CREATE VIEW {qualified(key.schema, key.name)}{with_clause} AS {view.definition};",
        )

    # Comments, after the views they annotate exist. A recreated view re-emits its comment
    # (the drop reset it), so pass the recreated names per schema.
    for schema_name, src_schema, dst_schema in ctx_iter_schema_pairs():
        src_schema_views = src_schema.view_by_name if src_schema else {}
        dst_schema_views = dst_schema.view_by_name if dst_schema else {}
        recreated_names = {key.name for key in recreate if key.schema == schema_name}
        for sql in diff_comment_statements(
            schema_name, src_schema_views, dst_schema_views, kind="VIEW", recreated=recreated_names
        ):
            yield Statement(Phase.VIEW_CREATE, sql)
