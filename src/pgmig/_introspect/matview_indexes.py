from pgmig._introspect.indexes import IndexRow, _load_indexes


def load_rows(rows: list[IndexRow]) -> None:
    """
    Indexes on materialized views (standalone; matviews carry no constraint-backed indexes).
    Must run after views.load so the owning matview exists in the model.
    """
    _load_indexes(rows, lambda schema: schema.materialized_view_by_name)
