from typing import Any

import psycopg

from pgmig._introspect._core import _QueryRow, _run_query
from pgmig._models import DbInfo, Extension


class _ExtensionRow(_QueryRow):
    name: str
    version: str
    extension_schema: str
    extension_comment: str | None


async def load(conn: psycopg.AsyncConnection[Any], db_info: DbInfo) -> None:
    """
    Extensions (database-level).
    """
    for ext_row in await _run_query(conn, "extensions.sql", _ExtensionRow):
        db_info.extension_by_name[ext_row.name] = Extension(
            name=ext_row.name,
            version=ext_row.version,
            schema=ext_row.extension_schema,
            comment=ext_row.extension_comment,
        )
