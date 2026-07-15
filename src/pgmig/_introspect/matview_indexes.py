from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, _run_query
from pgmig._models import Index


class _MatviewIndexRow(_QueryRow):
    schema_name: str
    view_name: str
    index_name: str
    index_def: str
    index_canonical: str
    index_comment: str | None


async def load() -> None:
    """
    Indexes on materialized views (standalone; matviews carry no constraint-backed indexes).
    Must run after materialized_views.load so the owning matview exists in the model.
    """
    for row in await _run_query("matview_indexes.sql", _MatviewIndexRow):
        matview = context.db_info.schema_by_name[row.schema_name].materialized_view_by_name[row.view_name]
        matview.index_by_name[row.index_name] = Index(
            name=row.index_name,
            definition=row.index_def,
            canonical=row.index_canonical,
            comment=row.index_comment,
        )
