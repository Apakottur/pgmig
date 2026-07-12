from collections.abc import Iterator

from pgmig._diff._core import Options, Phase, Statement, _diff_comments, _iter_schema_pairs
from pgmig._models import DbInfo, Sequence
from pgmig._sql import comment_on, qualified


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


def _sequence_comment_statements(schema_name: str, src: dict[str, Sequence], dst: dict[str, Sequence]) -> list[str]:
    """
    Emit COMMENT ON SEQUENCE for target sequences whose comment differs from source.
    """
    return _diff_comments(
        src, dst, render=lambda name, sequence: comment_on("SEQUENCE", qualified(schema_name, name), sequence.comment)
    )


def generate(*, source: DbInfo, target: DbInfo, options: Options) -> Iterator[Statement]:
    """
    Generate the migration SQL of standalone sequences. Creates and alters are phased
    before tables (a column default may reference a sequence); drops run after.
    """
    for schema_name, src_schema, dst_schema in _iter_schema_pairs(source, target):
        src_sequences = src_schema.sequence_by_name if src_schema else {}
        dst_sequences = dst_schema.sequence_by_name if dst_schema else {}

        for name in sorted(src_sequences.keys() | dst_sequences.keys()):
            qualified_name = qualified(schema_name, name)
            # Present in target only: create it.
            if name not in src_sequences:
                yield Statement(
                    Phase.SEQUENCE_CREATE, f"CREATE SEQUENCE {qualified_name} {_sequence_tail(dst_sequences[name])};"
                )
            # Present in source only: drop it.
            elif name not in dst_sequences:
                yield Statement(Phase.SEQUENCE_DROP, f"DROP SEQUENCE {qualified_name};")
            # Present in both: alter the parameters that differ.
            else:
                src_seq = src_sequences[name]
                dst_seq = dst_sequences[name]
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
        for sql in _sequence_comment_statements(schema_name, src_sequences, dst_sequences):
            yield Statement(Phase.SEQUENCE_CREATE, sql)
