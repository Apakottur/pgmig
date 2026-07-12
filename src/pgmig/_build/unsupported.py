from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._sql import qualified

# Human-readable name per unsupported kind (pg_class relkind or pg_type typtype), for
# the reported finding.
_KIND_NAMES = {
    "v": "view",
    "m": "materialized view",
    "p": "partitioned table",
    "f": "foreign table",
    "c": "composite type",
    "d": "domain",
    "r": "range type",
}


class _UnsupportedRow(BaseModel):
    schema_name: str
    obj_name: str
    kind: str


def check(conn: psycopg.Connection[Any]) -> list[str]:
    """
    Guard: report object kinds that are not modelled yet (views, materialized views,
    partitioned tables, foreign tables, composite types, domains, range types). Without
    this, generate() diffs only the supported kinds and returns "" for a database whose
    whole objects are missing on one side, falsely claiming convergence.
    """
    rows = _run_query(conn, "unsupported.sql", _UnsupportedRow)
    return [
        f"{_KIND_NAMES.get(row.kind, row.kind)} {qualified(row.schema_name, row.obj_name)} is not supported yet"
        for row in rows
    ]
