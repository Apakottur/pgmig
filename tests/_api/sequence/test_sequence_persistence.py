import pytest

from tests._api.generate_setup import GenerateSetup

# UNLOGGED sequences require Postgres 15+; the CREATE/ALTER syntax does not parse on 14.
_SEQ = "AS integer INCREMENT BY 1 MINVALUE 1 MAXVALUE 100 START WITH 1 CACHE 1"


async def test_create_unlogged_sequence(gen_setup: GenerateSetup) -> None:
    """
    An UNLOGGED sequence missing in source -> CREATE UNLOGGED SEQUENCE (the keyword must be
    emitted or the sequence is created logged and never converges).
    """
    if gen_setup.pg_major < 15:
        pytest.skip("UNLOGGED sequences require Postgres 15+")
    await gen_setup.assert_diff(
        src=[],
        dst=[f"CREATE UNLOGGED SEQUENCE counter {_SEQ}"],
        diff=[f'CREATE UNLOGGED SEQUENCE "public"."counter" {_SEQ}'],
    )


async def test_flip_logged_to_unlogged(gen_setup: GenerateSetup) -> None:
    """
    Same sequence, logged in source and unlogged in target -> ALTER SEQUENCE ... SET UNLOGGED.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("UNLOGGED sequences require Postgres 15+")
    await gen_setup.assert_diff(
        src=[f"CREATE SEQUENCE counter {_SEQ}"],
        dst=[f"CREATE UNLOGGED SEQUENCE counter {_SEQ}"],
        diff=['ALTER SEQUENCE "public"."counter" SET UNLOGGED'],
    )


async def test_flip_unlogged_to_logged(gen_setup: GenerateSetup) -> None:
    """
    Same sequence, unlogged in source and logged in target -> ALTER SEQUENCE ... SET LOGGED.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("UNLOGGED sequences require Postgres 15+")
    await gen_setup.assert_diff(
        src=[f"CREATE UNLOGGED SEQUENCE counter {_SEQ}"],
        dst=[f"CREATE SEQUENCE counter {_SEQ}"],
        diff=['ALTER SEQUENCE "public"."counter" SET LOGGED'],
    )


async def test_persistence_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same sequence, unlogged on both sides -> no migration SQL.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("UNLOGGED sequences require Postgres 15+")
    await gen_setup.assert_diff(
        both=[f"CREATE UNLOGGED SEQUENCE counter {_SEQ}"],
        src=[],
        dst=[],
        diff=[],
    )
