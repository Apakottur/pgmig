from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._keys import ColumnKey
from pgmig._models import Grant, Sequence


class _GrantRow(_QueryRow):
    grantee: str
    privilege: str
    grantable: bool


class _SequenceRow(_QueryRow):
    schema_name: str
    seq_name: str
    seq_type: str
    seq_start: int
    seq_inc: int
    seq_min: int
    seq_max: int
    seq_cache: int
    seq_cycle: bool
    seq_persistence: str  # pg_class.relpersistence: 'p' (permanent) or 'u' (unlogged)
    seq_comment: str | None
    seq_owner: str
    seq_grants: list[_GrantRow]
    owned_schema: str | None
    owned_table: str | None
    owned_column: str | None


async def load() -> None:
    """
    Sequences (the backing sequence of a serial/identity column is excluded; a manually
    owned sequence is kept, with its OWNED BY target in `owned_by`).
    """
    for seq_row in await run_introspection_query("sequences.sql", _SequenceRow):
        # A manual OWNED BY resolves all three owned_* columns together; a standalone
        # sequence leaves them NULL.
        owned_by: ColumnKey | None = None
        if seq_row.owned_schema is not None and seq_row.owned_table is not None and seq_row.owned_column is not None:
            owned_by = ColumnKey(seq_row.owned_schema, seq_row.owned_table, seq_row.owned_column)
        context.db_introspection_result.schema_by_name[seq_row.schema_name].sequence_by_name[seq_row.seq_name] = (
            Sequence(
                name=seq_row.seq_name,
                data_type=seq_row.seq_type,
                start=seq_row.seq_start,
                increment=seq_row.seq_inc,
                min_value=seq_row.seq_min,
                max_value=seq_row.seq_max,
                cache=seq_row.seq_cache,
                cycle=seq_row.seq_cycle,
                comment=seq_row.seq_comment,
                owner=seq_row.seq_owner,
                grants=frozenset(
                    Grant(grantee=grant.grantee, privilege=grant.privilege, grantable=grant.grantable)
                    for grant in seq_row.seq_grants
                ),
                owned_by=owned_by,
                unlogged=seq_row.seq_persistence == "u",
            )
        )
