from importlib.resources import files
from typing import cast

import psycopg
from typing_extensions import LiteralString

from pgmig._models import Column, Constraint, DbInfo, Extension, Function, Index, Schema, Sequence, Table

_QUERIES = files(__package__).joinpath("build_queries")


def _query(name: str) -> LiteralString:
    """
    Load a bundled SQL query from the build_queries directory.
    """
    # The cast keeps ty happy (execute expects a LiteralString); mypy treats
    # LiteralString as str and would call the cast redundant.
    return cast("LiteralString", _QUERIES.joinpath(name).read_text(encoding="utf-8"))  # type: ignore[redundant-cast]


_SCHEMAS_QUERY = _query("schemas.sql")
_TABLES_QUERY = _query("tables.sql")
_INDEXES_QUERY = _query("indexes.sql")
_CONSTRAINTS_QUERY = _query("constraints.sql")
_SEQUENCES_QUERY = _query("sequences.sql")
_FUNCTIONS_QUERY = _query("functions.sql")
_EXTENSIONS_QUERY = _query("extensions.sql")


def build_db_info(dsn: str) -> DbInfo:
    """
    Build the full structure of the given database.
    """
    schema_by_name: dict[str, Schema] = {}
    extension_by_name = {}

    # Construct database attributes.
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn:
        # Schemas (user namespaces, excluding system and extension-owned ones).
        rows = conn.execute(_SCHEMAS_QUERY).fetchall()
        for (schema_name,) in rows:
            schema_by_name[schema_name] = Schema(
                name=schema_name, table_by_name={}, sequence_by_name={}, function_by_signature={}
            )

        # Tables (and their columns, ordered by name).
        rows = conn.execute(_TABLES_QUERY).fetchall()
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
        ) in rows:
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
        rows = conn.execute(_INDEXES_QUERY).fetchall()
        for schema_name, table_name, index_name, index_def, index_canonical in rows:
            schema_by_name[schema_name].table_by_name[table_name].index_by_name[index_name] = Index(
                name=index_name,
                definition=index_def,
                canonical=index_canonical,
            )

        # Constraints (primary key, unique, and check).
        rows = conn.execute(_CONSTRAINTS_QUERY).fetchall()
        for schema_name, table_name, con_name, con_def, con_type, con_columns in rows:
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
        rows = conn.execute(_SEQUENCES_QUERY).fetchall()
        for schema_name, seq_name, seq_type, seq_start, seq_inc, seq_min, seq_max, seq_cache, seq_cycle in rows:
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
        rows = conn.execute(_FUNCTIONS_QUERY).fetchall()
        for schema_name, func_name, func_args, func_def, func_rettype, func_kind in rows:
            signature = f"{func_name}({func_args})"
            schema_by_name[schema_name].function_by_signature[signature] = Function(
                name=func_name,
                identity_arguments=func_args,
                definition=func_def.rstrip(),
                return_type=func_rettype,
                kind=func_kind,
            )

        # Extensions (database-level).
        rows = conn.execute(_EXTENSIONS_QUERY).fetchall()
        for name, version, schema in rows:
            extension_by_name[name] = Extension(name=name, version=version, schema=schema)

    # Build and return the database info.
    return DbInfo(
        extension_by_name=extension_by_name,
        schema_by_name=schema_by_name,
    )
