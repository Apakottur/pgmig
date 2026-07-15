from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._introspect._core import _run_query
from pgmig._models import CompositeField, CompositeType, DbInfo


class _CompositeFieldRow(BaseModel):
    name: str
    type: str


class _CompositeTypeRow(BaseModel):
    schema_name: str
    type_name: str
    type_comment: str | None
    fields: list[_CompositeFieldRow]


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Standalone composite types (user types only; extension-owned ones are excluded).
    """
    for row in _run_query(conn, "composite_types.sql", _CompositeTypeRow):
        fields = [CompositeField(name=field.name, type=field.type) for field in row.fields]
        db_info.schema_by_name[row.schema_name].composite_type_by_name[row.type_name] = CompositeType(
            name=row.type_name, fields=fields, comment=row.type_comment
        )
