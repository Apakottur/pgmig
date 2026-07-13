from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._sql import qualified


class _MatviewIndexRow(BaseModel):
    schema_name: str
    view_name: str
    index_name: str


def check(conn: psycopg.Connection[Any]) -> list[str]:
    """
    Guard: report an index on a materialized view. The basic matview cut does not model
    such indexes, and a definition change drops and recreates the matview, which would
    silently lose them, so they are reported rather than discarded.
    """
    findings: list[str] = []
    for row in _run_query(conn, "matview_indexes.sql", _MatviewIndexRow):
        matview = qualified(row.schema_name, row.view_name)
        findings.append(
            f"index {row.index_name} on materialized view {matview} is not supported yet"
        )
    return findings
