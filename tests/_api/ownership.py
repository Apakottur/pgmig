from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import get_unique_postgres_name


async def ensure_role(gen_setup: GenerateSetup, base: str) -> str:
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
