import pytest

from pgmig import generate
from tests.fixtures.generate_setup import GenerateSetup


def test_partitioned_table_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A partitioned table (relkind 'p'), even with a primary key, is not modelled yet.
    Rather than diff only regular tables and return "" (falsely claiming convergence),
    introspection must raise.
    """
    gen_setup.dst.execute("CREATE TABLE events (id integer NOT NULL) PARTITION BY RANGE (id)")
    gen_setup.dst.execute("ALTER TABLE events ADD CONSTRAINT events_pkey PRIMARY KEY (id)")

    with pytest.raises(NotImplementedError, match="partitioned table is not supported"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)
