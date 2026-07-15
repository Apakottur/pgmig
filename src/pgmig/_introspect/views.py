from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._introspect._core import _run_query
from pgmig._models import DbInfo, View


class _ViewRow(BaseModel):
    schema_name: str
    view_name: str
    view_definition: str
    view_comment: str | None


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Views (user views only; extension-owned ones are excluded).
    """
    for view_row in _run_query(conn, "views.sql", _ViewRow):
        # pg_get_viewdef renders the SELECT with surrounding whitespace and a trailing
        # semicolon; strip both so the stored definition is what follows "AS".
        definition = view_row.view_definition.strip().rstrip(";").strip()
        db_info.schema_by_name[view_row.schema_name].view_by_name[view_row.view_name] = View(
            name=view_row.view_name, definition=definition, comment=view_row.view_comment
        )
