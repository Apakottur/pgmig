import psycopg

from pgmig.diff import diff
from pgmig.introspect import introspect
from pgmig.render import render


def generate(*, source: str, target: str) -> str:
    with (
        psycopg.connect(source) as source_conn,
        psycopg.connect(target) as target_conn,
    ):
        source_schema = introspect(source_conn)
        target_schema = introspect(target_conn)
    changes = diff(source_schema, target_schema)
    return render(changes)
