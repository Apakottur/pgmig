from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, ctx_iter_schema_pairs, recreated_matview_keys
from pgmig._diff.indexes import diff_index_statements
from pgmig._models import Index, ViewKey


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of indexes on materialized views (create, drop, rename).

    An index is created after its matview exists, so all statements land in
    Phase.MATVIEW_INDEX_CREATE, which follows Phase.VIEW_CREATE where matviews are created --
    the ordering is a phase invariant, independent of generator registration order. A recreated
    matview loses every index; it is therefore diffed against an empty index set so all target
    indexes are created fresh. The shared recreated_matview_keys helper decides which matviews are
    recreated. A dropped matview takes its indexes with it and is skipped.
    """
    # Matviews the matview diff drops and recreates; the same helper the matview diff consumes,
    # so both agree on which matviews are recreated.
    recreated_keys = recreated_matview_keys()
    for schema_name, src_schema, dst_schema in ctx_iter_schema_pairs():
        src_views = src_schema.materialized_view_by_name if src_schema else {}
        dst_views = dst_schema.materialized_view_by_name if dst_schema else {}
        for name in sorted(src_views.keys() | dst_views.keys()):
            dst_view = dst_views.get(name)
            # Dropped matview: its indexes are dropped with it.
            if dst_view is None:
                continue

            src_view = src_views.get(name)
            # A new or recreated matview starts with no indexes, so every target index must be
            # created fresh; otherwise diff against the source.
            if src_view is None or ViewKey(schema_name, name) in recreated_keys:
                src_indexes: dict[str, Index] = {}
            else:
                src_indexes = src_view.index_by_name

            for sql in diff_index_statements(schema_name, src_indexes, dst_view.index_by_name):
                yield Statement(Phase.MATVIEW_INDEX_CREATE, sql)
