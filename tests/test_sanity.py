from pgmig import generate


def test_identical_empty_schemas_generate_no_sql(db_pair: tuple[str, str]) -> None:
    src_dsn, tgt_dsn = db_pair
    assert generate(source=src_dsn, target=tgt_dsn) == ""
