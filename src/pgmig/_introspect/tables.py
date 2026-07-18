from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._keys import RelationKey
from pgmig._models import Column, Grant, Table


class _GrantRow(_QueryRow):
    grantee: str
    privilege: str
    grantable: bool


class _TableRow(_QueryRow):
    schema_name: str
    table_name: str
    table_comment: str | None
    table_owner: str
    table_grants: list[_GrantRow]
    table_persistence: str  # pg_class.relpersistence: 'p' (permanent) or 'u' (unlogged)
    table_row_security: bool  # pg_class.relrowsecurity: ENABLE ROW LEVEL SECURITY
    table_force_row_security: bool  # pg_class.relforcerowsecurity: FORCE ROW LEVEL SECURITY
    table_replica_identity: str  # pg_class.relreplident: 'd' / 'n' / 'f' / 'i'
    table_replica_identity_index: str | None  # index name when relreplident is 'i', else NULL
    # Column fields are all NULL together for the single phantom row a zero-column table
    # yields through the LEFT JOIN (see tables.sql); a real column row has them all set.
    column_name: str | None
    column_type: str | None
    column_collation: str | None
    column_not_null: bool | None
    column_default: str | None
    generation_expression: str | None
    column_comment: str | None
    column_identity: str | None
    column_generated: str | None
    column_serial_sequence: str | None
    # Identity backing-sequence options; all NULL for a non-identity column.
    identity_start: int | None
    identity_increment: int | None
    identity_min: int | None
    identity_max: int | None
    identity_cache: int | None
    identity_cycle: bool | None
    # Partitioning metadata (per table, repeated on every column row).
    partition_strategy: str | None
    partition_key: str | None
    partition_bound: str | None
    partition_parent_schema: str | None
    partition_parent_name: str | None


async def load() -> None:
    """
    Tables (and their columns, in physical order).
    """
    for table_row in await run_introspection_query("tables.sql", _TableRow):
        schema = context.db_introspection_result.schema_by_name[table_row.schema_name]
        table = schema.table_by_name.get(table_row.table_name)
        if table is None:
            # A partition has both a parent schema and name (the query sets them together).
            partition_parent = (
                RelationKey(table_row.partition_parent_schema, table_row.partition_parent_name)
                if table_row.partition_parent_schema is not None and table_row.partition_parent_name is not None
                else None
            )
            table = Table(
                name=table_row.table_name,
                columns=[],
                comment=table_row.table_comment,
                owner=table_row.table_owner,
                grants=frozenset(
                    Grant(grantee=grant.grantee, privilege=grant.privilege, grantable=grant.grantable)
                    for grant in table_row.table_grants
                ),
                unlogged=table_row.table_persistence == "u",
                row_security=table_row.table_row_security,
                force_row_security=table_row.table_force_row_security,
                replica_identity=table_row.table_replica_identity,
                replica_identity_index=table_row.table_replica_identity_index,
                partition_strategy=table_row.partition_strategy,
                partition_key=table_row.partition_key,
                partition_bound=table_row.partition_bound,
                partition_parent=partition_parent,
                index_by_name={},
                constraint_by_name={},
                foreign_key_by_name={},
                trigger_by_name={},
                policy_by_name={},
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
                collation=table_row.column_collation,
                not_null=table_row.column_not_null,
                default=table_row.column_default,
                comment=table_row.column_comment,
                identity=table_row.column_identity,
                serial_sequence=table_row.column_serial_sequence,
                generated=table_row.column_generated,
                generation_expression=table_row.generation_expression,
                identity_start=table_row.identity_start,
                identity_increment=table_row.identity_increment,
                identity_min=table_row.identity_min,
                identity_max=table_row.identity_max,
                identity_cache=table_row.identity_cache,
                identity_cycle=table_row.identity_cycle,
            )
        )
