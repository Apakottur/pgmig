from pgmig._introspect._core import IntrospectionQuery, run_introspection_query
from pgmig._introspect.indexes import _IndexRow, _load_indexes


def load_rows(rows: list[_IndexRow]) -> None:
    """
    Indexes on materialized views (standalone; matviews carry no constraint-backed indexes).
    Must run after views.load so the owning matview exists in the model.
    """
    _load_indexes(rows, lambda schema: schema.materialized_view_by_name)


async def load() -> None:
    """
    Run the query and load its rows.
    """
    load_rows(await run_introspection_query(IntrospectionQuery.MATVIEW_INDEXES, _IndexRow))
