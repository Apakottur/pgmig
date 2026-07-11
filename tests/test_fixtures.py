import psycopg


def test_db_pair_gives_two_distinct_empty_databases(db_pair: tuple[str, str]) -> None:
    src_dsn, tgt_dsn = db_pair
    assert src_dsn != tgt_dsn
    for dsn in (src_dsn, tgt_dsn):
        with psycopg.connect(dsn) as conn:
            assert conn.execute("SELECT 1").fetchone() == (1,)
