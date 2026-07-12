from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._errors import PgmigError
from pgmig._models import DbInfo
from pgmig._sql import qualified


class _InvalidIndexRow(BaseModel):
    schema_name: str
    table_name: str
    index_name: str


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Guard: reject invalid indexes (pg_index.indisvalid = FALSE), the leftover of a
    failed CREATE INDEX CONCURRENTLY. They are indistinguishable from a valid index in
    the deparsed definition, so a diff over them is unreliable (false convergence, or a
    CREATE INDEX that collides with the name the invalid index still holds).
    """
    rows = _run_query(conn, "invalid_indexes.sql", _InvalidIndexRow)
    if rows:
        row = rows[0]
        index = qualified(row.schema_name, row.index_name)
        table = qualified(row.schema_name, row.table_name)
        raise PgmigError(
            f"Invalid index {index} on {table}: a failed CREATE INDEX CONCURRENTLY leaves an invalid index "
            f"behind. Drop it (DROP INDEX {index}) or rebuild it (REINDEX INDEX {index}), then re-run."
        )
