from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._introspect._core import _run_query
from pgmig._sql import qualified


class _InvalidIndexRow(BaseModel):
    schema_name: str
    table_name: str
    index_name: str


def check(conn: psycopg.Connection[Any]) -> list[str]:
    """
    Guard: report invalid indexes (pg_index.indisvalid = FALSE). An invalid index is
    indistinguishable from a valid one in its deparsed definition, so a diff over it is
    unreliable (false convergence, or a CREATE INDEX that collides with the name the
    invalid index still holds). The cause is not certain from the catalog, so the finding
    only suggests the most common one (a failed CREATE INDEX CONCURRENTLY).
    """
    findings: list[str] = []
    for row in _run_query(conn, "invalid_indexes.sql", _InvalidIndexRow):
        index = qualified(row.schema_name, row.index_name)
        table = qualified(row.schema_name, row.table_name)
        findings.append(
            f"invalid index {index} on {table} cannot be used (it may be a leftover of a failed "
            f"CREATE INDEX CONCURRENTLY); drop it (DROP INDEX {index}) or rebuild it (REINDEX INDEX {index})"
        )
    return findings
