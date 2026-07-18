from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement, ctx_iter_object_pairs, diff_comment_statements, owner_statements
from pgmig._diff.grants import grant_statements
from pgmig._keys import ColumnKey
from pgmig._models import Sequence
from pgmig._sql import qualified


def _sequence_tail(sequence: Sequence) -> str:
    """
    Render the parameter tail shared by CREATE SEQUENCE.
    """
    tail = (
        f"AS {sequence.data_type}"
        f" INCREMENT BY {sequence.increment}"
        f" MINVALUE {sequence.min_value}"
        f" MAXVALUE {sequence.max_value}"
        f" START WITH {sequence.start}"
        f" CACHE {sequence.cache}"
    )
    if sequence.cycle:
        tail += " CYCLE"
    return tail


def _persistence_keyword(sequence: Sequence) -> str:
    """
    The "UNLOGGED " keyword (with trailing space) inserted between CREATE and SEQUENCE for an
    unlogged sequence, or "" for a logged one. UNLOGGED sequences are PG15+.
    """
    return "UNLOGGED " if sequence.unlogged else ""


def _alter_statements(schema_name: str, name: str, src_seq: Sequence, dst_seq: Sequence) -> list[str]:
    """
    The ALTER SEQUENCE statements for a sequence present on both sides: the option changes
    (data type, increment, bounds, start, cache, cycle) folded into one ALTER, plus a separate
    ALTER for a persistence flip. SET LOGGED / SET UNLOGGED cannot be combined with the option
    clauses in a single ALTER SEQUENCE, so it is emitted on its own.
    """
    qualified_name = qualified(schema_name, name)
    clauses: list[str] = []
    if src_seq.data_type != dst_seq.data_type:
        clauses.append(f"AS {dst_seq.data_type}")
    if src_seq.increment != dst_seq.increment:
        clauses.append(f"INCREMENT BY {dst_seq.increment}")
    if src_seq.min_value != dst_seq.min_value:
        clauses.append(f"MINVALUE {dst_seq.min_value}")
    if src_seq.max_value != dst_seq.max_value:
        clauses.append(f"MAXVALUE {dst_seq.max_value}")
    if src_seq.start != dst_seq.start:
        clauses.append(f"START WITH {dst_seq.start}")
    if src_seq.cache != dst_seq.cache:
        clauses.append(f"CACHE {dst_seq.cache}")
    if src_seq.cycle != dst_seq.cycle:
        clauses.append("CYCLE" if dst_seq.cycle else "NO CYCLE")
    statements: list[str] = []
    if clauses:
        statements.append(f"ALTER SEQUENCE {qualified_name} {' '.join(clauses)};")
    if src_seq.unlogged != dst_seq.unlogged:
        statements.append(f"ALTER SEQUENCE {qualified_name} {'SET UNLOGGED' if dst_seq.unlogged else 'SET LOGGED'};")
    return statements


def _owned_by_clause(owned_by: ColumnKey | None) -> str:
    """
    Render the OWNED BY target of an ALTER SEQUENCE: the qualified column, or NONE.
    """
    if owned_by is None:
        return "NONE"
    return qualified(owned_by.schema, owned_by.table, owned_by.column)


def _owning_column_survives(owned_by: ColumnKey) -> bool:
    """
    Whether the column an owned sequence is tied to still exists in the target.

    A sequence with a manual OWNED BY is auto-dropped by Postgres when its owning column
    (or the column's table) is dropped. If the column is gone from the target, that cascade
    drops the sequence, so an explicit DROP SEQUENCE would fail "sequence does not exist";
    only emit one when the column survives.
    """
    schema = context.target.schema_by_name.get(owned_by.schema)
    table = schema.table_by_name.get(owned_by.table) if schema else None
    return table is not None and owned_by.column in table.column_by_name


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of standalone sequences. Creates and alters are phased
    before tables (a column default may reference a sequence); drops run after. A manual
    OWNED BY is (re)assigned in a later phase, once its target table/column exists.
    """
    for schema_name, src_sequences, dst_sequences, pairs in ctx_iter_object_pairs(
        lambda schema: schema.sequence_by_name
    ):
        for name, src_seq, dst_seq in pairs:
            qualified_name = qualified(schema_name, name)
            # Present in target only: create it, then assign its OWNED BY after tables exist.
            if src_seq is None:
                dst = dst_sequences[name]
                yield Statement(
                    Phase.SEQUENCE_CREATE,
                    f"CREATE {_persistence_keyword(dst)}SEQUENCE {qualified_name} {_sequence_tail(dst)};",
                )
                if dst.owned_by is not None:
                    yield Statement(
                        Phase.SEQUENCE_OWNED_BY,
                        f"ALTER SEQUENCE {qualified_name} OWNED BY {_owned_by_clause(dst.owned_by)};",
                    )
            # Present in source only: drop it, unless a cascade from its owning column does.
            elif dst_seq is None:
                if src_seq.owned_by is not None and not _owning_column_survives(src_seq.owned_by):
                    continue
                yield Statement(Phase.SEQUENCE_DROP, f"DROP SEQUENCE {qualified_name};")
            # Present in both: alter the options and persistence that differ.
            else:
                for sql in _alter_statements(schema_name, name, src_seq, dst_seq):
                    yield Statement(Phase.SEQUENCE_CREATE, sql)
                for sql in owner_statements("SEQUENCE", qualified_name, src_seq.owner, dst_seq.owner):
                    yield Statement(Phase.SEQUENCE_CREATE, sql)
                # ACL reconciliation, after the sequence exists (GRANT phase runs after every create).
                for sql in grant_statements(
                    "SEQUENCE",
                    qualified_name,
                    src_seq.grants,
                    dst_seq.grants,
                    src_seq.owner,
                    dst_seq.owner,
                    include_named_roles=context.include_grants,
                ):
                    yield Statement(Phase.GRANT, sql)
                # OWNED BY reassignment (added, removed, or retargeted) runs in the later
                # phase so a newly created target table/column is already in place.
                if src_seq.owned_by != dst_seq.owned_by:
                    yield Statement(
                        Phase.SEQUENCE_OWNED_BY,
                        f"ALTER SEQUENCE {qualified_name} OWNED BY {_owned_by_clause(dst_seq.owned_by)};",
                    )

        # Sync comments for target sequences.
        for sql in diff_comment_statements(schema_name, src_sequences, dst_sequences, kind="SEQUENCE"):
            yield Statement(Phase.SEQUENCE_CREATE, sql)
