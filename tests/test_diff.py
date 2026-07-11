from pgmig.diff import diff
from pgmig.model import Schema


def test_identical_empty_schemas_produce_no_changes() -> None:
    assert diff(Schema(), Schema()) == []
