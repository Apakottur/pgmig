from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, ctx_iter_schema_pairs, retyped_column_readers
from pgmig._diff.indexes import diff_index_statements
from pgmig._models import Index, ViewKey


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of indexes on materialized views (create, drop, rename).

    An index is created after its matview exists, so all statements land in
    Phase.MATVIEW_INDEX_CREATE, which follows Phase.VIEW_CREATE where matviews are created --
    the ordering is a phase invariant, independent of generator registration order. A recreated
    matview loses every index; it is therefore diffed against an empty index set so all target
    indexes are created fresh. A matview is recreated when its definition changed OR it reads a
    column whose type changes (the matview diff drops and recreates it in that case too, even
    though its definition is unchanged). A dropped matview takes its indexes with it and is skipped.
    """
    # Matviews the matview diff recreates because they read a retyped column (definition
    # unchanged). Kept in sync with materialized_views.generate via the shared helper.
    column_readers = retyped_column_readers()
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
            if (
                src_view is None
                or src_view.definition != dst_view.definition
                or ViewKey(schema_name, name) in column_readers
            ):
                src_indexes: dict[str, Index] = {}
            else:
                src_indexes = src_view.index_by_name

            for sql in diff_index_statements(schema_name, src_indexes, dst_view.index_by_name):
                yield Statement(Phase.MATVIEW_INDEX_CREATE, sql)
