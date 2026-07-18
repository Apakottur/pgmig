from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_materialized_view_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same matview both sides owned by different roles, with --include-owner -> ALTER
    MATERIALIZED VIEW ... OWNER TO.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW m AS SELECT 1 AS x"],
        src=[f"ALTER MATERIALIZED VIEW m OWNER TO {role_a}"],
        dst=[f"ALTER MATERIALIZED VIEW m OWNER TO {role_b}"],
        diff=[f'ALTER MATERIALIZED VIEW "public"."m" OWNER TO "{role_b}"'],
        include_owner=True,
    )
