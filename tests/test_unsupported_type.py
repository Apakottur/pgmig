import pytest

from pgmig import PgmigError, generate
from tests.fixtures.generate_setup import GenerateSetup


def test_range_type_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A range type (pg_type typtype 'r') is not modelled yet and must raise.
    """
    gen_setup.dst.execute("CREATE TYPE float_range AS RANGE (subtype = float8)")

    with pytest.raises(PgmigError, match=r"range type .* is not supported"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)
