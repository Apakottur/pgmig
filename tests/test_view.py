import pytest

from pgmig import generate
from tests.fixtures.generate_setup import GenerateSetup


def test_view_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A view (relkind 'v') is not modelled yet. Rather than diff only regular tables and
    return "" (falsely claiming convergence), introspection must raise.
    """
    gen_setup.dst.execute("CREATE VIEW active AS SELECT 1 AS x")

    with pytest.raises(NotImplementedError, match="view is not supported"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)


def test_materialized_view_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A materialized view (relkind 'm'), even with an index on it, is not modelled yet and
    must raise rather than be silently ignored.
    """
    gen_setup.dst.execute("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE INDEX report_x_idx ON report (x)")

    with pytest.raises(NotImplementedError, match="materialized view is not supported"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)
