from pgmig._introspect._core import _QueryRow, _run_query
from pgmig._models import Column, DbInfo, Table


class _TableRow(_QueryRow):
    schema_name: str
    table_name: str
    table_comment: str | None
    table_owner: str
    # Column fields are all NULL together for the single phantom row a zero-column table
    # yields through the LEFT JOIN (see tables.sql); a real column row has them all set.
    column_name: str | None
    column_type: str | None
    column_not_null: bool | None
    column_default: str | None
    generation_expression: str | None
    column_comment: str | None
    column_identity: str | None
    column_generated: str | None
    column_serial_sequence: str | None
    # Partitioning metadata (per table, repeated on every column row).
    partition_strategy: str | None
    partition_key: str | None
    partition_bound: str | None
    partition_parent_schema: str | None
    partition_parent_name: str | None


async def load(db_info: DbInfo) -> None:
    """
    Tables (and their columns, in physical order).
    """
    for table_row in await _run_query("tables.sql", _TableRow):
        schema = db_info.schema_by_name[table_row.schema_name]
        table = schema.table_by_name.get(table_row.table_name)
        if table is None:
            # A partition has both a parent schema and name (the query sets them together).
            partition_parent = (
                (table_row.partition_parent_schema, table_row.partition_parent_name)
                if table_row.partition_parent_schema is not None and table_row.partition_parent_name is not None
                else None
            )
            table = Table(
                name=table_row.table_name,
                columns=[],
                comment=table_row.table_comment,
                owner=table_row.table_owner,
                partition_strategy=table_row.partition_strategy,
                partition_key=table_row.partition_key,
                partition_bound=table_row.partition_bound,
                partition_parent=partition_parent,
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
            or table_row.column_generated is None
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
                generated=table_row.column_generated,
                generation_expression=table_row.generation_expression,
            )
        )
