import pytest

from tests._api.generate_setup import GenerateSetup

# NULLS NOT DISTINCT on unique constraints requires Postgres 15+; the syntax does not parse on 14.


async def test_constraint_add_unique_nulls_not_distinct(gen_setup: GenerateSetup) -> None:
    """
    A NULLS NOT DISTINCT unique constraint missing in source -> ADD CONSTRAINT carrying the clause.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("NULLS NOT DISTINCT requires Postgres 15+")
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (email text)"],
        src=[],
        dst=["ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE NULLS NOT DISTINCT (email)"],
        diff=['ALTER TABLE "public"."person" ADD CONSTRAINT "person_email_key" UNIQUE NULLS NOT DISTINCT (email)'],
    )


async def test_constraint_drop_unique_nulls_not_distinct(gen_setup: GenerateSetup) -> None:
    """
    A NULLS NOT DISTINCT unique constraint present in source but missing in target -> DROP CONSTRAINT.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("NULLS NOT DISTINCT requires Postgres 15+")
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE NULLS NOT DISTINCT (email)",
        ],
        dst=["CREATE TABLE person (email text)"],
        diff=['ALTER TABLE "public"."person" DROP CONSTRAINT "person_email_key"'],
    )


async def test_constraint_toggle_nulls_not_distinct(gen_setup: GenerateSetup) -> None:
    """
    Same name, the clause toggled on (distinct in source, not-distinct in target) changes the
    definition -> DROP CONSTRAINT then ADD CONSTRAINT.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("NULLS NOT DISTINCT requires Postgres 15+")
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)",
        ],
        dst=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE NULLS NOT DISTINCT (email)",
        ],
        diff=[
            'ALTER TABLE "public"."person" DROP CONSTRAINT "person_email_key"',
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_email_key" UNIQUE NULLS NOT DISTINCT (email)',
        ],
    )


async def test_constraint_rename_nulls_not_distinct(gen_setup: GenerateSetup) -> None:
    """
    Same NULLS NOT DISTINCT definition on both sides, only the name differs -> RENAME CONSTRAINT.
    The clause is part of pg_get_constraintdef, so the definitions still match for rename detection.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("NULLS NOT DISTINCT requires Postgres 15+")
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_old UNIQUE NULLS NOT DISTINCT (email)",
        ],
        dst=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_new UNIQUE NULLS NOT DISTINCT (email)",
        ],
        diff=['ALTER TABLE "public"."person" RENAME CONSTRAINT "person_email_old" TO "person_email_new"'],
    )


async def test_constraint_nulls_not_distinct_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same name and NULLS NOT DISTINCT definition on both sides -> no migration SQL.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("NULLS NOT DISTINCT requires Postgres 15+")
    await gen_setup.assert_diff(
        both=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE NULLS NOT DISTINCT (email)",
        ],
        src=[],
        dst=[],
        diff=[],
    )
