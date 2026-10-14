from pgmig._introspect._core import Loader
from pgmig._introspect.indexes import _IndexRow, _load_indexes


class MatviewIndexesLoader(Loader[_IndexRow]):
    """
    Indexes on materialized views (standalone; matviews carry no constraint-backed indexes).
    Must run after the views loader so the owning matview exists in the model.
    """

    file_name = "matview_indexes.sql"
    model = _IndexRow

    def process_rows(self, rows: list[_IndexRow]) -> None:
        _load_indexes(rows, lambda schema: schema.materialized_view_by_name)
