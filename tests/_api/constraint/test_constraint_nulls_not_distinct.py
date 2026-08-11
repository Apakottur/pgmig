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
