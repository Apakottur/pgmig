from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_enum_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same enum type both sides owned by different roles -> ALTER TYPE ... OWNER TO target's.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE TYPE e AS ENUM ('a', 'b')"],
        src=[f"ALTER TYPE e OWNER TO {role_a}"],
        dst=[f"ALTER TYPE e OWNER TO {role_b}"],
        diff=[f'ALTER TYPE "public"."e" OWNER TO "{role_b}"'],
        include_owner=True,
    )


async def test_composite_type_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same composite type both sides owned by different roles -> ALTER TYPE ... OWNER TO target's.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE TYPE c AS (x integer)"],
        src=[f"ALTER TYPE c OWNER TO {role_a}"],
        dst=[f"ALTER TYPE c OWNER TO {role_b}"],
        diff=[f'ALTER TYPE "public"."c" OWNER TO "{role_b}"'],
        include_owner=True,
    )


async def test_domain_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same domain both sides owned by different roles -> ALTER DOMAIN ... OWNER TO target's.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE DOMAIN d AS integer"],
        src=[f"ALTER DOMAIN d OWNER TO {role_a}"],
        dst=[f"ALTER DOMAIN d OWNER TO {role_b}"],
        diff=[f'ALTER DOMAIN "public"."d" OWNER TO "{role_b}"'],
        include_owner=True,
    )


async def test_range_type_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same range type both sides owned by different roles -> ALTER TYPE ... OWNER TO target's.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE TYPE r AS RANGE (SUBTYPE = integer)"],
        src=[f"ALTER TYPE r OWNER TO {role_a}"],
        dst=[f"ALTER TYPE r OWNER TO {role_b}"],
        diff=[f'ALTER TYPE "public"."r" OWNER TO "{role_b}"'],
        include_owner=True,
    )
