from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._models import DbInfo, EnumType


class _EnumRow(BaseModel):
    schema_name: str
    enum_name: str
    enum_values: list[str]


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Enum types (user enums only; extension-owned ones are excluded).
    """
    for enum_row in _run_query(conn, "enums.sql", _EnumRow):
        db_info.schema_by_name[enum_row.schema_name].enum_by_name[enum_row.enum_name] = EnumType(
            name=enum_row.enum_name, values=enum_row.enum_values
        )
