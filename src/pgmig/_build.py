from pathlib import Path
from typing import Any, TypeVar, cast

import psycopg
from psycopg.rows import class_row
from pydantic import BaseModel
from typing_extensions import LiteralString

from pgmig._models import (
    Column,
    Constraint,
    DbInfo,
    EnumType,
    Extension,
    Function,
    Index,
    Schema,
    Sequence,
    Table,
    Trigger,
)


class _SchemaRow(BaseModel):
    schema_name: str
    schema_comment: str | None


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


class _IndexRow(BaseModel):
    schema_name: str
    table_name: str
    index_name: str
    index_def: str
    index_canonical: str
    index_comment: str | None


class _TriggerRow(BaseModel):
    schema_name: str
    table_name: str
    trigger_name: str
    trigger_def: str
    trigger_canonical: str


class _ConstraintRow(BaseModel):
    schema_name: str
    table_name: str
    con_name: str
    con_def: str
    con_type: str
    con_columns: list[str] | None
    con_comment: str | None


class _SequenceRow(BaseModel):
    schema_name: str
    seq_name: str
    seq_type: str
    seq_start: int
    seq_inc: int
    seq_min: int
    seq_max: int
    seq_cache: int
    seq_cycle: bool
    seq_comment: str | None


class _FunctionRow(BaseModel):
    schema_name: str
    func_name: str
    func_args: str
    func_def: str
    func_rettype: str | None
    func_kind: str
    func_comment: str | None


class _EnumRow(BaseModel):
    schema_name: str
    enum_name: str
    enum_values: list[str]


class _ExtensionRow(BaseModel):
    name: str
    version: str
    extension_schema: str


_RowT = TypeVar("_RowT", bound=BaseModel)


def _run_query(conn: psycopg.Connection[Any], file_name: str, model: type[_RowT]) -> list[_RowT]:
    """
    Load a bundled SQL query from the build_queries directory, run it, and parse each
    row into the given Pydantic model (by SELECT column alias). Validation happens at
    parse time, so a schema/type drift surfaces here rather than silently downstream.
    """
    file_path = Path(__file__).parent.joinpath("build_queries").joinpath(file_name)
    query = cast("LiteralString", file_path.read_text(encoding="utf-8"))  # type: ignore[redundant-cast]
    with conn.cursor(row_factory=class_row(model)) as cur:
        return cur.execute(query).fetchall()


def build_db_info(dsn: str) -> DbInfo:
    """
    Build the full structure of the given database.
    """
    schema_by_name: dict[str, Schema] = {}
    extension_by_name = {}

    # Construct database attributes. Each query's rows are parsed into a typed Pydantic
    # model keyed by SELECT alias, so field access is by name and decoupled from column
    # order in the .sql files.
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn:
        # Schemas (user namespaces, excluding system and extension-owned ones).
        for schema_row in _run_query(conn, "schemas.sql", _SchemaRow):
            schema_by_name[schema_row.schema_name] = Schema(
                name=schema_row.schema_name,
                comment=schema_row.schema_comment,
                table_by_name={},
                sequence_by_name={},
                function_by_signature={},
                enum_by_name={},
            )

        # Tables (and their columns, in physical order).
        for table_row in _run_query(conn, "tables.sql", _TableRow):
            schema = schema_by_name[table_row.schema_name]
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

        # Indexes (standalone only; constraint-backed indexes are excluded).
        for index_row in _run_query(conn, "indexes.sql", _IndexRow):
            table = schema_by_name[index_row.schema_name].table_by_name[index_row.table_name]
            table.index_by_name[index_row.index_name] = Index(
                name=index_row.index_name,
                definition=index_row.index_def,
                canonical=index_row.index_canonical,
                comment=index_row.index_comment,
            )

        # Triggers (user triggers only; internal RI/constraint-backing triggers are excluded).
        for trigger_row in _run_query(conn, "triggers.sql", _TriggerRow):
            table = schema_by_name[trigger_row.schema_name].table_by_name[trigger_row.table_name]
            table.trigger_by_name[trigger_row.trigger_name] = Trigger(
                name=trigger_row.trigger_name,
                definition=trigger_row.trigger_def,
                canonical=trigger_row.trigger_canonical,
            )

        # Constraints (primary key, unique, and check).
        for con_row in _run_query(conn, "constraints.sql", _ConstraintRow):
            constraint = Constraint(
                name=con_row.con_name,
                definition=con_row.con_def,
                contype=con_row.con_type,
                columns=con_row.con_columns or [],
                comment=con_row.con_comment,
            )
            table = schema_by_name[con_row.schema_name].table_by_name[con_row.table_name]
            if constraint.is_foreign_key:
                table.foreign_key_by_name[con_row.con_name] = constraint
            else:
                table.constraint_by_name[con_row.con_name] = constraint

        # Sequences (standalone only; sequences owned by a serial/identity column are excluded).
        for seq_row in _run_query(conn, "sequences.sql", _SequenceRow):
            schema_by_name[seq_row.schema_name].sequence_by_name[seq_row.seq_name] = Sequence(
                name=seq_row.seq_name,
                data_type=seq_row.seq_type,
                start=seq_row.seq_start,
                increment=seq_row.seq_inc,
                min_value=seq_row.seq_min,
                max_value=seq_row.seq_max,
                cache=seq_row.seq_cache,
                cycle=seq_row.seq_cycle,
                comment=seq_row.seq_comment,
            )

        # Functions and procedures (excluding aggregates, window functions, and extension-owned ones).
        for func_row in _run_query(conn, "functions.sql", _FunctionRow):
            signature = f"{func_row.func_name}({func_row.func_args})"
            schema_by_name[func_row.schema_name].function_by_signature[signature] = Function(
                name=func_row.func_name,
                identity_arguments=func_row.func_args,
                definition=func_row.func_def.rstrip(),
                return_type=func_row.func_rettype,
                kind=func_row.func_kind,
                comment=func_row.func_comment,
            )

        # Enum types (user enums only; extension-owned ones are excluded).
        for enum_row in _run_query(conn, "enums.sql", _EnumRow):
            schema_by_name[enum_row.schema_name].enum_by_name[enum_row.enum_name] = EnumType(
                name=enum_row.enum_name, values=enum_row.enum_values
            )

        # Extensions (database-level).
        for ext_row in _run_query(conn, "extensions.sql", _ExtensionRow):
            extension_by_name[ext_row.name] = Extension(
                name=ext_row.name, version=ext_row.version, schema=ext_row.extension_schema
            )

    # Build and return the database info.
    return DbInfo(
        extension_by_name=extension_by_name,
        schema_by_name=schema_by_name,
    )
