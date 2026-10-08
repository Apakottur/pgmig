from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement, ctx_iter_object_pairs
from pgmig._diff.indexes import diff_index_statements
from pgmig._keys import RelationKey
from pgmig._models import Index


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of indexes on materialized views (create, drop, rename).

    An index is created after its matview exists, so all statements land in
    Phase.MATVIEW_INDEX_CREATE, which follows Phase.MATVIEW_CREATE where matviews are created --
    the ordering is a phase invariant, independent of generator registration order. A recreated
    matview loses every index; it is therefore diffed against an empty index set so all target
    indexes are created fresh. The shared recreated_matview_keys helper decides which matviews are
    recreated. A dropped matview takes its indexes with it and is skipped.
    """
    # Matviews the matview diff drops and recreates; the same helper the matview diff consumes,
    # so both agree on which matviews are recreated.
    recreated_keys = context.recreated_matview_keys
    for schema_name, _src_views, _dst_views, pairs in ctx_iter_object_pairs(
        lambda schema: schema.materialized_view_by_name
    ):
        for name, src_view, dst_view in pairs:
            # Dropped matview: its indexes are dropped with it.
            if dst_view is None:
                continue

            # A new or recreated matview starts with no indexes, so every target index must be
            # created fresh; otherwise diff against the source.
            if src_view is None or RelationKey(schema_name, name) in recreated_keys:
                src_indexes: dict[str, Index] = {}
            else:
                src_indexes = src_view.index_by_name

            for sql in diff_index_statements(schema_name, src_indexes, dst_view.index_by_name):
                yield Statement(Phase.MATVIEW_INDEX_CREATE, sql)
