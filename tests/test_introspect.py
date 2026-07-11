import psycopg

from pgmig.introspect import introspect
from pgmig.model import Schema


def test_introspect_empty_database_returns_empty_schema(db_pair: tuple[str, str]) -> None:
    src_dsn, _ = db_pair
    with psycopg.connect(src_dsn) as conn:
        assert introspect(conn) == Schema()
