from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._introspect._core import _run_query
from pgmig._models import ColumnKey, DbInfo, ViewKey


class _ViewColumnDependencyRow(BaseModel):
    view_schema: str
    view_name: str
    table_schema: str
    table_name: str
    column_name: str


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    View-on-column edges: record, for each view or materialized view, the set of table
    columns it reads. The view and matview diffs use these to drop and recreate a (mat)view
    around a change (type change, drop) to a column it depends on, since Postgres refuses to
    alter or drop a column a view or matview reads.
    """
    for row in _run_query(conn, "view_column_dependencies.sql", _ViewColumnDependencyRow):
        view = ViewKey(row.view_schema, row.view_name)
        column = ColumnKey(row.table_schema, row.table_name, row.column_name)
        db_info.view_column_dependencies.setdefault(view, set()).add(column)
