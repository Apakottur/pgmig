from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._models import DbInfo, ViewKey


class _ViewDependencyRow(BaseModel):
    dependent_schema: str
    dependent_view: str
    referenced_schema: str
    referenced_view: str


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    View-on-view edges: record, for each view that reads another view, the set of views
    it reads from. The view diff uses these to topologically order CREATE (dependencies
    first) and DROP (dependents first) within the view phases.
    """
    for row in _run_query(conn, "view_dependencies.sql", _ViewDependencyRow):
        dependent = ViewKey((row.dependent_schema, row.dependent_view))
        referenced = ViewKey((row.referenced_schema, row.referenced_view))
        db_info.view_dependency_edges.setdefault(dependent, set()).add(referenced)
