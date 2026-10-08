import pytest

import pgmig


async def test_agenerate_connection_error_is_public() -> None:
    """A database that cannot be connected to raises the public PgmigDbConnectionError, a PgmigError."""
    with pytest.raises(pgmig.PgmigDbConnectionError) as excinfo:
        await pgmig.agenerate(source="not-a-dsn", target="not-a-dsn")

    assert isinstance(excinfo.value, pgmig.PgmigError)
    assert excinfo.value.source_error is not None
    assert excinfo.value.target_error is not None
