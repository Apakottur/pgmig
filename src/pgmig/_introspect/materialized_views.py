from typing import Any

import psycopg

from pgmig._introspect.views import _load_views
from pgmig._models import DbInfo, MaterializedView


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Materialized views (user matviews only; extension-owned ones are excluded).
    """
    _load_views(
        conn,
        db_info,
        "materialized_views.sql",
        lambda schema: schema.materialized_view_by_name,
        lambda name, definition, comment: MaterializedView(
            name=name, definition=definition, comment=comment, index_by_name={}
        ),
    )
