from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._sql import qualified


class _ViewDependencyRow(BaseModel):
    dependent_schema: str
    dependent_view: str
    referenced_schema: str
    referenced_view: str


def check(conn: psycopg.Connection[Any]) -> list[str]:
    """
    Guard: report a view that reads from another view. Ordering create/drop across such a
    dependency needs a topological sort within the view phases, which is not implemented
    yet, so the pair is reported rather than emitted in a possibly-wrong order.
    """
    findings: list[str] = []
    for row in _run_query(conn, "view_dependencies.sql", _ViewDependencyRow):
        dependent = qualified(row.dependent_schema, row.dependent_view)
        referenced = qualified(row.referenced_schema, row.referenced_view)
        findings.append(
            f"view {dependent} reads from view {referenced}: view-on-view dependencies are not supported yet"
        )
    return findings
