from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_view_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same view both sides owned by different roles, with --include-owner -> ALTER VIEW ...
    OWNER TO target's.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE VIEW v AS SELECT 1 AS x"],
        src=[f"ALTER VIEW v OWNER TO {role_a}"],
        dst=[f"ALTER VIEW v OWNER TO {role_b}"],
        diff=[f'ALTER VIEW "public"."v" OWNER TO "{role_b}"'],
        include_owner=True,
    )


async def test_view_owner_ignored_by_default(gen_setup: GenerateSetup) -> None:
    """
    Owners differ, but ownership is not reconciled by default (no --include-owner).
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE VIEW v AS SELECT 1 AS x"],
        src=[f"ALTER VIEW v OWNER TO {role_a}"],
        dst=[f"ALTER VIEW v OWNER TO {role_b}"],
        diff=[],
    )
