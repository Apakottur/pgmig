from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._sql import qualified

# pg_class.relkind -> the object noun used in the finding message.
_KIND_LABEL = {"v": "view", "m": "materialized view"}


class _ViewDependencyRow(BaseModel):
    dependent_schema: str
    dependent_view: str
    dependent_kind: str
    referenced_schema: str
    referenced_view: str
    referenced_kind: str


def check(conn: psycopg.Connection[Any]) -> list[str]:
    """
    Guard: report a view or materialized view that reads from another view or matview.
    Ordering create/drop across such a dependency needs a topological sort within the shared
    view phases, which is not implemented yet, so the pair is reported rather than emitted in
    a possibly-wrong order.
    """
    findings: list[str] = []
    for row in _run_query(conn, "view_dependencies.sql", _ViewDependencyRow):
        dependent = qualified(row.dependent_schema, row.dependent_view)
        referenced = qualified(row.referenced_schema, row.referenced_view)
        dependent_label = _KIND_LABEL[row.dependent_kind]
        referenced_label = _KIND_LABEL[row.referenced_kind]
        findings.append(
            f"{dependent_label} {dependent} reads from {referenced_label} {referenced}: "
            f"dependencies among views/materialized views are not supported yet"
        )
    return findings
