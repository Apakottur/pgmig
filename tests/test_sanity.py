from pgmig import generate
from tests.harness import GenerateSetup


def test_identical_empty_schemas_generate_no_sql(gen_setup: GenerateSetup) -> None:
    result = generate(source=gen_setup.db_src.dsn, target=gen_setup.db_dst.dsn)
    assert result == ""
