from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._models import DbInfo, Sequence


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


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Sequences (standalone only; sequences owned by a serial/identity column are excluded).
    """
    for seq_row in _run_query(conn, "sequences.sql", _SequenceRow):
        db_info.schema_by_name[seq_row.schema_name].sequence_by_name[seq_row.seq_name] = Sequence(
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
