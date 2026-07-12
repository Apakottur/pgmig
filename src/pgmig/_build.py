from pathlib import Path
from typing import Any, cast

import psycopg
from typing_extensions import LiteralString

from pgmig._errors import PgmigError
from pgmig._models import Column, Constraint, DbInfo, Extension, Function, Index, Schema, Sequence, Table


def _run_query(conn: psycopg.Connection[tuple[Any, ...]], file_name: str) -> list[tuple[Any, ...]]:
    """
    Load a bundled SQL query from the build_queries directory, run it, and return all rows.
    """
    file_path = Path(__file__).parent.joinpath("build_queries").joinpath(file_name)
    query = cast("LiteralString", file_path.read_text(encoding="utf-8"))  # type: ignore[redundant-cast]
    return conn.execute(query).fetchall()


def build_db_info(dsn: str) -> DbInfo:
    """
    Build the full structure of the given database.
    """
    schema_by_name: dict[str, Schema] = {}
    extension_by_name = {}

    # Open the connection, surfacing connection failures as a clean PgmigError.
    try:
        conn = psycopg.connect(dsn, options="-c default_transaction_read_only=on")
    except psycopg.Error as error:
        raise PgmigError(f"Could not connect to database: {error}") from error

    # Construct database attributes.
    with conn:
        # Schemas (user namespaces, excluding system and extension-owned ones).
        for (schema_name,) in _run_query(conn, "schemas.sql"):
            schema_by_name[schema_name] = Schema(
                name=schema_name, table_by_name={}, sequence_by_name={}, function_by_signature={}
            )

        # Tables (and their columns, ordered by name).
        for (
            schema_name,
            table_name,
            column_name,
            column_type,
            column_not_null,
            column_default,
            column_comment,
            table_comment,
            column_identity,
            column_serial_sequence,
        ) in _run_query(conn, "tables.sql"):
            if table_name not in schema_by_name[schema_name].table_by_name:
                schema_by_name[schema_name].table_by_name[table_name] = Table(
                    name=table_name,
                    columns=[],
                    comment=table_comment,
                    index_by_name={},
                    constraint_by_name={},
                    foreign_key_by_name={},
                )
            schema_by_name[schema_name].table_by_name[table_name].columns.append(
                Column(
                    name=column_name,
                    type=column_type,
                    not_null=column_not_null,
                    default=column_default,
                    comment=column_comment,
                    identity=column_identity,
                    serial_sequence=column_serial_sequence,
                )
            )

        # Indexes (standalone only; constraint-backed indexes are excluded).
        for schema_name, table_name, index_name, index_def, index_canonical in _run_query(conn, "indexes.sql"):
            schema_by_name[schema_name].table_by_name[table_name].index_by_name[index_name] = Index(
                name=index_name,
                definition=index_def,
                canonical=index_canonical,
            )

        # Constraints (primary key, unique, and check).
        for schema_name, table_name, con_name, con_def, con_type, con_columns in _run_query(conn, "constraints.sql"):
            constraint = Constraint(
                name=con_name,
                definition=con_def,
                contype=con_type,
                columns=con_columns or [],
            )
            table = schema_by_name[schema_name].table_by_name[table_name]
            if constraint.is_foreign_key:
                table.foreign_key_by_name[con_name] = constraint
            else:
                table.constraint_by_name[con_name] = constraint

        # Sequences (standalone only; sequences owned by a serial/identity column are excluded).
        for (
            schema_name,
            seq_name,
            seq_type,
            seq_start,
            seq_inc,
            seq_min,
            seq_max,
            seq_cache,
            seq_cycle,
        ) in _run_query(conn, "sequences.sql"):
            schema_by_name[schema_name].sequence_by_name[seq_name] = Sequence(
                name=seq_name,
                data_type=seq_type,
                start=seq_start,
                increment=seq_inc,
                min_value=seq_min,
                max_value=seq_max,
                cache=seq_cache,
                cycle=seq_cycle,
            )

        # Functions and procedures (excluding aggregates, window functions, and extension-owned ones).
        for schema_name, func_name, func_args, func_def, func_rettype, func_kind in _run_query(conn, "functions.sql"):
            signature = f"{func_name}({func_args})"
            schema_by_name[schema_name].function_by_signature[signature] = Function(
                name=func_name,
                identity_arguments=func_args,
                definition=func_def.rstrip(),
                return_type=func_rettype,
                kind=func_kind,
            )

        # Extensions (database-level).
        for name, version, schema in _run_query(conn, "extensions.sql"):
            extension_by_name[name] = Extension(name=name, version=version, schema=schema)

    # Build and return the database info.
    return DbInfo(
        extension_by_name=extension_by_name,
        schema_by_name=schema_by_name,
    )
