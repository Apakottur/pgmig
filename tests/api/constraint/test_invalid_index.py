import psycopg
import pytest

from pgmig import PgmigError, generate
from tests.api.generate_setup import GenerateSetup


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

    with pytest.raises(PgmigError, match="invalid index"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)


def test_multiple_invalid_indexes_are_all_listed(gen_setup: GenerateSetup) -> None:
    """
    Every invalid index is reported in a single error, not one per re-run.
    """
    for table, index in (("t1", "u1"), ("t2", "u2")):
        gen_setup.src.execute(f"CREATE TABLE {table} (a integer)")
        gen_setup.src.execute(f"INSERT INTO {table} VALUES (1), (1)")
        with pytest.raises(psycopg.errors.UniqueViolation):
            gen_setup.src.execute(f"CREATE UNIQUE INDEX CONCURRENTLY {index} ON {table} (a)")

    with pytest.raises(PgmigError) as excinfo:
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)

    message = str(excinfo.value)
    assert '"public"."u1"' in message
    assert '"public"."u2"' in message
