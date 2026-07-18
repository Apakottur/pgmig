from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import get_unique_postgres_name


async def _ensure_role(gen_setup: GenerateSetup, base: str) -> str:
    """
    Create a cluster-wide role for the test and return its name.

    Roles are cluster-level (shared by every database in the server), so creating one
    on the source connection makes it visible to the target too. They also outlive the
    per-test DROP/CREATE DATABASE, so a bare CREATE ROLE would collide on the second
    test; DROP ... IF EXISTS first makes it idempotent. The name is namespaced by the
    branch key (like the test databases) so parallel runs on other branches, which share
    this cluster, don't race on the same role.
    """
    name = get_unique_postgres_name(base, gen_setup.unique_key)
    await gen_setup.src.execute(f"DROP ROLE IF EXISTS {name}")
    await gen_setup.src.execute(f"CREATE ROLE {name}")
    return name


async def test_table_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same table both sides owned by different roles, with --include-owner -> ALTER TABLE ...
    OWNER TO target's.
    """
    role_a = await _ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await _ensure_role(gen_setup, "pgmig_owner_b")

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
    role_a = await _ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await _ensure_role(gen_setup, "pgmig_owner_b")

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
    role_a = await _ensure_role(gen_setup, "pgmig_owner_a")
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
