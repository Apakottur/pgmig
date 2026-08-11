import pytest

from tests._api.generate_setup import GenerateSetup

# NULLS NOT DISTINCT on unique indexes requires Postgres 15+; the syntax does not parse on 14.

_IDX_DEF = "CREATE UNIQUE INDEX {name} ON public.person USING btree (email) NULLS NOT DISTINCT"


async def test_index_add_unique_nulls_not_distinct(gen_setup: GenerateSetup) -> None:
    """
    A NULLS NOT DISTINCT unique index missing in source -> CREATE UNIQUE INDEX carrying the clause.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("NULLS NOT DISTINCT requires Postgres 15+")
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (email text)"],
        src=[],
        dst=["CREATE UNIQUE INDEX person_email_idx ON person (email) NULLS NOT DISTINCT"],
        diff=[_IDX_DEF.format(name="person_email_idx")],
    )
