from collections.abc import Iterator

from pgmig._diff._core import Context, Phase, Statement, _diff_comments, _iter_schema_pairs
from pgmig._errors import PgmigError
from pgmig._models import DbInfo, View, ViewKey
from pgmig._sql import comment_on, qualified

_Edges = dict[ViewKey, set[ViewKey]]  # key -> the views it reads from


def _collect_views(db_info: DbInfo) -> dict[ViewKey, View]:
    """
    Flatten every schema's views into one (schema, name) -> View map. View-on-view
    ordering is global because a dependency can cross schemas.
    """
    views: dict[ViewKey, View] = {}
    for schema_name, schema in db_info.schema_by_name.items():
        for name, view in schema.view_by_name.items():
            views[ViewKey((schema_name, name))] = view
    return views


def _topological_order(nodes: set[ViewKey], edges: _Edges) -> list[ViewKey]:
    """
    Order `nodes` dependencies-first: a view appears after every view it reads that is
    also in `nodes` (edges to views outside the set are ignored). Ties break by sorted
    key so the output is deterministic. A cycle -- which Postgres does not permit between
    views -- raises rather than silently dropping nodes.
    """
    deps = {node: {dep for dep in edges.get(node, set()) if dep in nodes} for node in nodes}
    dependents: dict[ViewKey, set[ViewKey]] = {node: set() for node in nodes}
    for node, node_deps in deps.items():
        for dep in node_deps:
            dependents[dep].add(node)

    ready = sorted(node for node, node_deps in deps.items() if not node_deps)
    order: list[ViewKey] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for dependent in sorted(dependents[node]):
            deps[dependent].discard(node)
            if not deps[dependent]:
                ready.append(dependent)
        ready.sort()

    if len(order) != len(nodes):
        cyclic = sorted(node for node in nodes if node not in set(order))
        raise PgmigError(f"view dependency cycle detected among: {', '.join(qualified(*node) for node in cyclic)}")
    return order


def _comment_statements(schema_name: str, src: dict[str, View], dst: dict[str, View], recreated: set[str]) -> list[str]:
    """
    COMMENT ON VIEW for target views whose comment differs from source. A recreated view
    always re-emits (the drop-and-recreate reset its comment).
    """
    return _diff_comments(
        src,
        dst,
        render=lambda name, view: comment_on("VIEW", qualified(schema_name, name), view.comment),
        recreated=recreated,
    )


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


def generate(ctx: Context) -> Iterator[Statement]:
    """
    Generate the migration SQL of views, ordered by their view-on-view dependencies.

    Creates run in the VIEW_CREATE phase in dependency-first order; drops run in the
    VIEW_DROP phase in dependent-first order. A changed definition is a drop-and-recreate
    (CREATE OR REPLACE VIEW cannot reshape columns); every view that transitively reads a
    recreated view is dragged into the recreate set, since Postgres refuses to drop a view
    another view still reads and the dependents must be rebuilt afterwards.
    """
    src_views = _collect_views(ctx.source)
    dst_views = _collect_views(ctx.target)
    src_edges = ctx.source.view_dependency_edges
    dst_edges = ctx.target.view_dependency_edges

    shared = src_views.keys() & dst_views.keys()
    changed = {key for key in shared if src_views[key].definition != dst_views[key].definition}
    # A recreate resets the view (and its comment); pull in every view that transitively
    # reads a changed one. Restrict to shared views -- a create-only view has nothing to
    # drop, and a drop-only view is already dropped below.
    recreate = _dependents_closure(changed, src_edges) & shared

    drop_only = src_views.keys() - dst_views.keys()
    create_only = dst_views.keys() - src_views.keys()

    # Drops: dependent-first, so reverse the source graph's dependency-first order.
    drops = drop_only | recreate
    for key in reversed(_topological_order(drops, src_edges)):
        yield Statement(Phase.VIEW_DROP, f"DROP VIEW {qualified(*key)};")

    # Creates: dependency-first over the target graph.
    creates = create_only | recreate
    for key in _topological_order(creates, dst_edges):
        yield Statement(Phase.VIEW_CREATE, f"CREATE VIEW {qualified(*key)} AS {dst_views[key].definition};")

    # Comments, after the views they annotate exist. A recreated view re-emits its comment
    # (the drop reset it), so pass the recreated names per schema.
    for schema_name, src_schema, dst_schema in _iter_schema_pairs(ctx.source, ctx.target):
        src_schema_views = src_schema.view_by_name if src_schema else {}
        dst_schema_views = dst_schema.view_by_name if dst_schema else {}
        recreated_names = {name for (schema, name) in recreate if schema == schema_name}
        for sql in _comment_statements(schema_name, src_schema_views, dst_schema_views, recreated_names):
            yield Statement(Phase.VIEW_CREATE, sql)
