from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._sql import qualified

# Human-readable name per unsupported kind (pg_class relkind, pg_type typtype,
# pg_constraint contype, or pg_proc prokind), for the reported finding. The codes are
# distinct across those catalogs for the kinds we report, so one flat map is unambiguous.
_KIND_NAMES = {
    "f": "foreign table",
    "r": "range type",
    "x": "exclusion constraint",
    "a": "aggregate",
    "w": "window function",
}


class _UnsupportedRow(BaseModel):
    schema_name: str
    obj_name: str
    kind: str


def check(conn: psycopg.Connection[Any]) -> list[str]:
    """
    Guard: report object kinds that are not modelled yet (foreign tables, range types,
    exclusion constraints, aggregate/window functions). Without this, generate() diffs
    only the supported kinds and returns "" for a database whose whole objects are missing
    on one side, falsely claiming convergence.
    """
    rows = _run_query(conn, "unsupported.sql", _UnsupportedRow)
    return [
        f"{_KIND_NAMES.get(row.kind, row.kind)} {qualified(row.schema_name, row.obj_name)} is not supported yet"
        for row in rows
    ]
