import pytest

from pgmig import generate
from tests.fixtures.generate_setup import GenerateSetup


def test_composite_type_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A standalone composite type (pg_class relkind 'c') is not modelled yet. Rather than
    diff only the supported kinds and return "" (falsely claiming convergence), it must
    raise.
    """
    gen_setup.dst.execute("CREATE TYPE pair AS (a integer, b integer)")

    with pytest.raises(NotImplementedError, match="composite type is not supported"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)


def test_domain_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A domain (pg_type typtype 'd') is not modelled yet and must raise.
    """
    gen_setup.dst.execute("CREATE DOMAIN positive_int AS integer CHECK (VALUE > 0)")

    with pytest.raises(NotImplementedError, match="domain is not supported"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)


def test_range_type_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A range type (pg_type typtype 'r') is not modelled yet and must raise.
    """
    gen_setup.dst.execute("CREATE TYPE float_range AS RANGE (subtype = float8)")

    with pytest.raises(NotImplementedError, match="range type is not supported"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)
