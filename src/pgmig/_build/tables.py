from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._models import Column, DbInfo, Table


class _TableRow(BaseModel):
    schema_name: str
    table_name: str
    column_name: str
    column_type: str
    column_not_null: bool
    column_default: str | None
    column_comment: str | None
    table_comment: str | None
    column_identity: str
    column_serial_sequence: str | None


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Tables (and their columns, in physical order).
    """
    for table_row in _run_query(conn, "tables.sql", _TableRow):
        schema = db_info.schema_by_name[table_row.schema_name]
        if table_row.table_name not in schema.table_by_name:
            schema.table_by_name[table_row.table_name] = Table(
                name=table_row.table_name,
                columns=[],
                comment=table_row.table_comment,
                index_by_name={},
                constraint_by_name={},
                foreign_key_by_name={},
                trigger_by_name={},
            )
        schema.table_by_name[table_row.table_name].columns.append(
            Column(
                name=table_row.column_name,
                type=table_row.column_type,
                not_null=table_row.column_not_null,
                default=table_row.column_default,
                comment=table_row.column_comment,
                identity=table_row.column_identity,
                serial_sequence=table_row.column_serial_sequence,
            )
        )
