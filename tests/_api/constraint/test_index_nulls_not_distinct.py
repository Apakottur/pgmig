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


async def test_index_drop_unique_nulls_not_distinct(gen_setup: GenerateSetup) -> None:
    """
    A NULLS NOT DISTINCT unique index present in source but missing in target -> DROP INDEX.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("NULLS NOT DISTINCT requires Postgres 15+")
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (email text)",
            "CREATE UNIQUE INDEX person_email_idx ON person (email) NULLS NOT DISTINCT",
        ],
        dst=["CREATE TABLE person (email text)"],
        diff=['DROP INDEX "public"."person_email_idx"'],
    )


async def test_index_toggle_nulls_not_distinct(gen_setup: GenerateSetup) -> None:
    """
    Same name, the clause toggled on (distinct in source, not-distinct in target) changes the
    definition -> DROP INDEX then CREATE INDEX.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("NULLS NOT DISTINCT requires Postgres 15+")
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (email text)",
            "CREATE UNIQUE INDEX person_email_idx ON person (email)",
        ],
        dst=[
            "CREATE TABLE person (email text)",
            "CREATE UNIQUE INDEX person_email_idx ON person (email) NULLS NOT DISTINCT",
        ],
        diff=[
            'DROP INDEX "public"."person_email_idx"',
            _IDX_DEF.format(name="person_email_idx"),
        ],
    )


async def test_index_rename_nulls_not_distinct(gen_setup: GenerateSetup) -> None:
    """
    Same NULLS NOT DISTINCT definition on both sides, only the name differs -> ALTER INDEX RENAME.
    The clause is part of pg_get_indexdef, so the canonical forms still match for rename detection.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("NULLS NOT DISTINCT requires Postgres 15+")
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (email text)",
            "CREATE UNIQUE INDEX person_email_old ON person (email) NULLS NOT DISTINCT",
        ],
        dst=[
            "CREATE TABLE person (email text)",
            "CREATE UNIQUE INDEX person_email_new ON person (email) NULLS NOT DISTINCT",
        ],
        diff=['ALTER INDEX "public"."person_email_old" RENAME TO "person_email_new"'],
    )


async def test_index_nulls_not_distinct_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same name and NULLS NOT DISTINCT definition on both sides -> no migration SQL.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("NULLS NOT DISTINCT requires Postgres 15+")
    await gen_setup.assert_diff(
        both=[
            "CREATE TABLE person (email text)",
            "CREATE UNIQUE INDEX person_email_idx ON person (email) NULLS NOT DISTINCT",
        ],
        src=[],
        dst=[],
        diff=[],
    )
