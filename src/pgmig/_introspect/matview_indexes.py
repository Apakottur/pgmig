from collections.abc import Mapping

from pgmig._introspect.indexes import IndexesLoader, _HasIndexes
from pgmig._models import Schema


class MatviewIndexesLoader(IndexesLoader):
    """
    Indexes on materialized views (standalone; matviews carry no constraint-backed indexes).
    Must run after the views loader so the owning matview exists in the model.

    Its query differs from the table-index one (a matview has no partitioning, primary keys or
    constraint-backed indexes to exclude), but the rows and their storage are the same.
    """

    file_name = "matview_indexes.sql"

    @classmethod
    def get_relations(cls, schema: Schema) -> Mapping[str, _HasIndexes]:
        return schema.materialized_view_by_name
