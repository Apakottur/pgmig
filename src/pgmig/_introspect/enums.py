from typing import Any

import psycopg

from pgmig._introspect._core import _QueryRow, _run_query
from pgmig._models import DbInfo, EnumType


class _EnumRow(_QueryRow):
    schema_name: str
    enum_name: str
    enum_values: list[str]
    enum_comment: str | None


async def load(conn: psycopg.AsyncConnection[Any], db_info: DbInfo) -> None:
    """
    Enum types (user enums only; extension-owned ones are excluded).
    """
    for enum_row in await _run_query(conn, "enums.sql", _EnumRow):
        db_info.schema_by_name[enum_row.schema_name].enum_by_name[enum_row.enum_name] = EnumType(
            name=enum_row.enum_name, values=enum_row.enum_values, comment=enum_row.enum_comment
        )
