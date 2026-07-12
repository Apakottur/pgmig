from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._models import DbInfo, Schema


class _SchemaRow(BaseModel):
    schema_name: str
    schema_comment: str | None


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Schemas (user namespaces, excluding system and extension-owned ones).
    """
    for schema_row in _run_query(conn, "schemas.sql", _SchemaRow):
        db_info.schema_by_name[schema_row.schema_name] = Schema(
            name=schema_row.schema_name,
            comment=schema_row.schema_comment,
            table_by_name={},
            sequence_by_name={},
            function_by_signature={},
            enum_by_name={},
            view_by_name={},
            domain_by_name={},
        )
