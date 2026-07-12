from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._models import DbInfo

# Human-readable name per unsupported kind (pg_class relkind or pg_type typtype), for
# the raised message.
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


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Guard: reject object kinds that are not modelled yet (views, materialized views,
    partitioned tables, foreign tables, composite types, domains, range types). Without
    this, generate() diffs only the supported kinds and returns "" for a database whose
    whole objects are missing on one side, falsely claiming convergence. Consistent with
    raising on unsupported column changes.
    """
    rows = _run_query(conn, "unsupported.sql", _UnsupportedRow)
    if rows:
        row = rows[0]
        kind = _KIND_NAMES.get(row.kind, row.kind)
        raise NotImplementedError(f"{kind} is not supported yet: {row.schema_name}.{row.obj_name}")
