from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._models import Sequence


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
    seq_comment: str | None


def load() -> None:
    """
    Sequences (standalone only; sequences owned by a serial/identity column are excluded).
    """
    for seq_row in run_introspection_query("sequences.sql", _SequenceRow):
        context.db_info.schema_by_name[seq_row.schema_name].sequence_by_name[seq_row.seq_name] = Sequence(
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
