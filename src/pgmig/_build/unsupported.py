from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._models import DbInfo

# Human-readable name per unsupported relkind, for the raised message.
_RELKIND_NAMES = {
    "v": "view",
    "m": "materialized view",
    "p": "partitioned table",
    "f": "foreign table",
}


class _UnsupportedRow(BaseModel):
    schema_name: str
    rel_name: str
    rel_kind: str


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Guard: reject relation kinds that are not modelled yet (views, materialized views,
    partitioned tables, foreign tables). Without this, generate() diffs only regular
    tables and returns "" for a database whose whole relations are missing on one side,
    falsely claiming convergence. Consistent with raising on unsupported column changes.
    """
    rows = _run_query(conn, "unsupported.sql", _UnsupportedRow)
    if rows:
        row = rows[0]
        kind = _RELKIND_NAMES.get(row.rel_kind, row.rel_kind)
        raise NotImplementedError(f"{kind} is not supported yet: {row.schema_name}.{row.rel_name}")
