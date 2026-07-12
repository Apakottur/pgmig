from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._models import Column, DbInfo, Table


class _TableRow(BaseModel):
    schema_name: str
    table_name: str
    table_comment: str | None
    # Column fields are all NULL together for the single phantom row a zero-column table
    # yields through the LEFT JOIN (see tables.sql); a real column row has them all set.
    column_name: str | None
    column_type: str | None
    column_not_null: bool | None
    column_default: str | None
    column_comment: str | None
    column_identity: str | None
    column_serial_sequence: str | None


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Tables (and their columns, in physical order).
    """
    for table_row in _run_query(conn, "tables.sql", _TableRow):
        schema = db_info.schema_by_name[table_row.schema_name]
        table = schema.table_by_name.get(table_row.table_name)
        if table is None:
            table = Table(
                name=table_row.table_name,
                columns=[],
                comment=table_row.table_comment,
                index_by_name={},
                constraint_by_name={},
                foreign_key_by_name={},
                trigger_by_name={},
            )
            schema.table_by_name[table_row.table_name] = table
        # A zero-column table's phantom row (all column fields NULL) creates the table
        # above but adds no column.
        if (
            table_row.column_name is None
            or table_row.column_type is None
            or table_row.column_not_null is None
            or table_row.column_identity is None
        ):
            continue
        table.columns.append(
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
