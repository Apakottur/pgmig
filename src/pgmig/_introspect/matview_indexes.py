from pgmig._introspect._core import IntrospectionQuery
from pgmig._introspect.indexes import _load_indexes


async def load() -> None:
    """
    Indexes on materialized views (standalone; matviews carry no constraint-backed indexes).
    Must run after materialized_views.load so the owning matview exists in the model.
    """
    await _load_indexes(IntrospectionQuery.MATVIEW_INDEXES, lambda schema: schema.materialized_view_by_name)
