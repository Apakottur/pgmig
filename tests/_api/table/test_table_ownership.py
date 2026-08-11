from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_table_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same table both sides owned by different roles, with --include-owner -> ALTER TABLE ...
    OWNER TO target's.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_a}",
        ],
        dst=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_b}",
        ],
        diff=[f'ALTER TABLE "public"."person" OWNER TO "{role_b}"'],
        include_owner=True,
    )


async def test_table_owner_ignored_by_default(gen_setup: GenerateSetup) -> None:
    """
    Owners differ, but ownership is not reconciled by default (no --include-owner), so no
    ALTER TABLE ... OWNER TO is emitted.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_a}",
        ],
        dst=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_b}",
        ],
        diff=[],
    )


async def test_table_owner_unchanged_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same table and same owner on both sides, with --include-owner -> no migration SQL.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_a}",
        ],
        dst=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_a}",
        ],
        diff=[],
        include_owner=True,
    )
