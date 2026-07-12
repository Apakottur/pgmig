
import asyncpg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._models import DbInfo, Index


class _IndexRow(BaseModel):
    schema_name: str
    table_name: str
    index_name: str
    index_def: str
    index_canonical: str
    index_comment: str | None


async def load(conn: asyncpg.Connection, db_info: DbInfo) -> None:
    """
    Indexes (standalone only; constraint-backed indexes are excluded).
    """
    for index_row in await _run_query(conn, "indexes.sql", _IndexRow):
        table = db_info.schema_by_name[index_row.schema_name].table_by_name[index_row.table_name]
        table.index_by_name[index_row.index_name] = Index(
            name=index_row.index_name,
            definition=index_row.index_def,
            canonical=index_row.index_canonical,
            comment=index_row.index_comment,
        )
