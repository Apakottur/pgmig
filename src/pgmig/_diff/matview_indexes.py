from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, ctx_iter_schema_pairs
from pgmig._diff.indexes import diff_index_statements
from pgmig._models import Index


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of indexes on materialized views (create, drop, rename).

    An index is created after its matview exists, so all statements land in
    Phase.VIEW_CREATE (matview creates are emitted earlier in that phase). A changed
    matview definition drops and recreates the matview, which loses every index; a new
    or recreated matview is therefore diffed against an empty index set so all target
    indexes are created fresh. A dropped matview takes its indexes with it and is skipped.
    """
    for schema_name, src_schema, dst_schema in ctx_iter_schema_pairs():
        src_views = src_schema.materialized_view_by_name if src_schema else {}
        dst_views = dst_schema.materialized_view_by_name if dst_schema else {}
        for name in sorted(src_views.keys() | dst_views.keys()):
            dst_view = dst_views.get(name)
            # Dropped matview: its indexes are dropped with it.
            if dst_view is None:
                continue

            src_view = src_views.get(name)
            # A new or recreated (definition-changed) matview starts with no indexes, so
            # every target index must be created fresh; otherwise diff against the source.
            if src_view is None or src_view.definition != dst_view.definition:
                src_indexes: dict[str, Index] = {}
            else:
                src_indexes = src_view.index_by_name

            for sql in diff_index_statements(schema_name, src_indexes, dst_view.index_by_name):
                yield Statement(Phase.VIEW_CREATE, sql)
