import hashlib
import re

import tenacity

from pgmig._db import DbConnection

_DSN_PREFIX = "postgresql://pgmig:pgmig@localhost:15432"
_PGBOUNCER_DSN_PREFIX = "postgresql://pgmig:pgmig@localhost:16432"


# Postgres truncates identifiers past this length, which would silently collapse
# distinct long branch names to the same database name.
_MAX_IDENTIFIER_LEN = 63


def get_unique_postgres_name(base: str, key: str) -> str:
    """
    Build a valid, unique Postgres entity name from a base and a free-form key(e.g. a git branch name).
    Useful for developing on multiple branches in parallel.
    """
    # Simple name - cleaned key and base.
    slug = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    name = f"{base}_{slug}"

    # Name is short - use as is.
    if len(name) <= _MAX_IDENTIFIER_LEN:
        return name

    # Name is long - hash the slug.
    digest = hashlib.sha256(slug.encode()).hexdigest()[:8]
    # Reserve room for: base + "_" + truncated_slug + "_" + digest.
    slug_len = _MAX_IDENTIFIER_LEN - len(base) - len(digest) - 2
    slug_trunc = slug[:slug_len].rstrip("_")
    return f"{base}_{slug_trunc}_{digest}"


def get_dsn(db_name: str, *, pgbouncer: bool = False) -> str:
    """
    Get the DSN for a database.
    """
    if pgbouncer:
        return f"{_PGBOUNCER_DSN_PREFIX}/{db_name}"
    else:
        return f"{_DSN_PREFIX}/{db_name}"


@tenacity.retry(
    wait=tenacity.wait_fixed(0.5),
    stop=tenacity.stop_after_delay(10),
    reraise=True,
)
async def wait_for_db_connection(*, dsn: str) -> None:
    """
    Wait for a database to be ready to accept connections.
    """
    async with DbConnection.connect(dsn=dsn):
        pass


async def recreate_database(admin_conn: DbConnection, db_name: str) -> None:
    """
    Recreate a database.
    """
    # Drop the database, if exists. WITH (FORCE) atomically terminates any
    # lingering backends and drops the database, avoiding the race between a
    # separate pg_terminate_backend call and the drop.
    await admin_conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")

    # Create the database.
    await admin_conn.execute(f"CREATE DATABASE {db_name}")
