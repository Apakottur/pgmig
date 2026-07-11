from pgmig.model import Schema


def test_empty_schemas_are_equal() -> None:
    assert Schema() == Schema()
