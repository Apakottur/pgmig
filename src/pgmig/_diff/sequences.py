from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, ctx_iter_object_pairs, diff_comment_statements
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


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of standalone sequences. Creates and alters are phased
    before tables (a column default may reference a sequence); drops run after.
    """
    for schema_name, src_sequences, dst_sequences, pairs in ctx_iter_object_pairs(
        lambda schema: schema.sequence_by_name
    ):
        for name, src_seq, dst_seq in pairs:
            qualified_name = qualified(schema_name, name)
            # Present in target only: create it.
            if src_seq is None:
                yield Statement(
                    Phase.SEQUENCE_CREATE, f"CREATE SEQUENCE {qualified_name} {_sequence_tail(dst_sequences[name])};"
                )
            # Present in source only: drop it.
            elif dst_seq is None:
                yield Statement(Phase.SEQUENCE_DROP, f"DROP SEQUENCE {qualified_name};")
            # Present in both: alter the parameters that differ.
            else:
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
                if clauses:
                    yield Statement(Phase.SEQUENCE_CREATE, f"ALTER SEQUENCE {qualified_name} {' '.join(clauses)};")

        # Sync comments for target sequences.
        for sql in diff_comment_statements(schema_name, src_sequences, dst_sequences, kind="SEQUENCE"):
            yield Statement(Phase.SEQUENCE_CREATE, sql)
