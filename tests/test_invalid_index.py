import psycopg
import pytest

from pgmig import PgmigError, generate
from tests.fixtures.generate_setup import GenerateSetup


def test_invalid_index_is_rejected(gen_setup: GenerateSetup) -> None:
    """
    An invalid index (a leftover of a failed CREATE INDEX CONCURRENTLY) makes the diff
    unreliable, so introspection must refuse it with a clear PgmigError.
    """
    gen_setup.src.execute("CREATE TABLE t (a integer)")
    gen_setup.src.execute("INSERT INTO t VALUES (1), (1)")

    # A unique index built concurrently over duplicate rows fails and leaves an invalid
    # index behind.
    with pytest.raises(psycopg.errors.UniqueViolation):
        gen_setup.src.execute("CREATE UNIQUE INDEX CONCURRENTLY u ON t (a)")

    with pytest.raises(PgmigError, match="Invalid index"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)
