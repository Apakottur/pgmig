from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._introspect._core import _run_query
from pgmig._models import DbInfo, Extension


class _ExtensionRow(BaseModel):
    name: str
    version: str
    extension_schema: str
    extension_comment: str | None


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Extensions (database-level).
    """
    for ext_row in _run_query(conn, "extensions.sql", _ExtensionRow):
        db_info.extension_by_name[ext_row.name] = Extension(
            name=ext_row.name,
            version=ext_row.version,
            schema=ext_row.extension_schema,
            comment=ext_row.extension_comment,
        )
