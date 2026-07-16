from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement, ctx_iter_schema_pairs, diff_comment_statements, topological_sort
from pgmig._models import DbIntrospectionResult, View, ViewKey
from pgmig._sql import qualified

_Edges = dict[ViewKey, set[ViewKey]]  # key -> the views it reads from


def _collect_views(db_introspection_result: DbIntrospectionResult) -> dict[ViewKey, View]:
    """
    Flatten every schema's views into one (schema, name) -> View map. View-on-view
    ordering is global because a dependency can cross schemas.
    """
    views: dict[ViewKey, View] = {}
    for schema_name, schema in db_introspection_result.schema_by_name.items():
        for name, view in schema.view_by_name.items():
            views[ViewKey(schema_name, name)] = view
    return views


def _dependents_closure(seeds: set[ViewKey], edges: _Edges) -> set[ViewKey]:
    """
    Every view that transitively reads any view in `seeds`, plus the seeds themselves.
    Used for the recreate cascade: dropping and recreating a view forces every view that
    reads it (directly or through a chain) to be dropped and recreated too.
    """
    reverse: _Edges = {}
    for node, node_deps in edges.items():
        for dep in node_deps:
            reverse.setdefault(dep, set()).add(node)

    result = set(seeds)
    stack = list(seeds)
    while stack:
        current = stack.pop()
        for dependent in reverse.get(current, set()):
            if dependent not in result:
                result.add(dependent)
                stack.append(dependent)
    return result


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of views, ordered by their view-on-view dependencies.

    Creates run in the VIEW_CREATE phase in dependency-first order; drops run in the
    VIEW_DROP phase in dependent-first order. A changed definition is a drop-and-recreate
    (CREATE OR REPLACE VIEW cannot reshape columns); every view that transitively reads a
    recreated view is dragged into the recreate set, since Postgres refuses to drop a view
    another view still reads and the dependents must be rebuilt afterwards.
    """
    source, target = context.source, context.target
    src_views = _collect_views(source)
    dst_views = _collect_views(target)
    src_edges = source.view_dependencies
    dst_edges = target.view_dependencies

    shared = src_views.keys() & dst_views.keys()
    changed = {key for key in shared if src_views[key].definition != dst_views[key].definition}
    # A view reading a table column whose type changes must also be recreated: Postgres
    # refuses ALTER COLUMN ... TYPE while a view reads the column, so the view is dropped in
    # VIEW_DROP (before the TABLE-phase change) and recreated in VIEW_CREATE. A type change
    # leaves the view's definition unchanged, so `changed` above never catches this.
    column_readers = context.retyped_column_readers
    # A recreate resets the view (and its comment); pull in every view that transitively
    # reads a changed one. Restrict to shared views -- a create-only view has nothing to
    # drop, and a drop-only view is already dropped below.
    recreate = _dependents_closure(changed | column_readers, src_edges) & shared

    drop_only = src_views.keys() - dst_views.keys()
    create_only = dst_views.keys() - src_views.keys()

    # Drops: dependent-first, so reverse the source graph's dependency-first order.
    drops = drop_only | recreate
    for key in reversed(topological_sort(drops, src_edges)):
        yield Statement(Phase.VIEW_DROP, f"DROP VIEW {qualified(key.schema, key.name)};")

    # Creates: dependency-first over the target graph.
    creates = create_only | recreate
    for key in topological_sort(creates, dst_edges):
        yield Statement(
            Phase.VIEW_CREATE, f"CREATE VIEW {qualified(key.schema, key.name)} AS {dst_views[key].definition};"
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
