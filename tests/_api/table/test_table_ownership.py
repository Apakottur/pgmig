from psycopg import sql

from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import _KEY, get_unique_db_name


def _ensure_role(gen_setup: GenerateSetup, base: str) -> str:
    """
    Create a cluster-wide role for the test and return its name.

    Roles are cluster-level (shared by every database in the server), so creating one
    on the source connection makes it visible to the target too. They also outlive the
    per-test DROP/CREATE DATABASE, so a bare CREATE ROLE would collide on the second
    test; DROP ... IF EXISTS first makes it idempotent. The name is namespaced by the
    branch key (like the test databases) so parallel runs on other branches, which share
    this cluster, don't race on the same role.
    """
    name = get_unique_db_name(base, _KEY)
    gen_setup.src.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(name)))
    gen_setup.src.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(name)))
    return name


def test_table_owner_changed(gen_setup: GenerateSetup) -> None:
    """
    Same table both sides owned by different roles -> ALTER TABLE ... OWNER TO target's.
    """
    role_a = _ensure_role(gen_setup, "pgmig_owner_a")
    role_b = _ensure_role(gen_setup, "pgmig_owner_b")

    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_a}",
        ],
        dst=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_b}",
        ],
        diff=[f'ALTER TABLE "public"."person" OWNER TO "{role_b}"'],
    )


def test_table_owner_ignored(gen_setup: GenerateSetup) -> None:
    """
    Owners differ, but --ignore-owner suppresses the ALTER TABLE ... OWNER TO entirely.
    """
    role_a = _ensure_role(gen_setup, "pgmig_owner_a")
    role_b = _ensure_role(gen_setup, "pgmig_owner_b")

    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_a}",
        ],
        dst=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_b}",
        ],
        diff=[],
        ignore_owner=True,
    )


def test_table_owner_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same table and same owner on both sides -> no migration SQL.
    """
    role_a = _ensure_role(gen_setup, "pgmig_owner_a")
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_a}",
        ],
        dst=[
            "CREATE TABLE person (name text)",
            f"ALTER TABLE person OWNER TO {role_a}",
        ],
        diff=[],
    )
