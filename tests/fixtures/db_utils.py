import hashlib
import re

import tenacity

from pgmig._db import DbConnection

_DSN_PREFIX = "postgresql://pgmig:pgmig@localhost:15432"
_PGBOUNCER_DSN_PREFIX = "postgresql://pgmig:pgmig@localhost:16432"
ADMIN_DB_DSN = f"{_DSN_PREFIX}/postgres"


@tenacity.retry(wait=tenacity.wait_fixed(0.5), stop=tenacity.stop_after_delay(15), reraise=True)
def wait_until_accepting_connections(dsn: str) -> None:
    """
    Block until the given DSN accepts a connection, retrying while it is not ready (e.g.
    waiting for pgbouncer to come up alongside Postgres).
    """
    psycopg.connect(dsn).close()


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


async def recreate_database(db_name: str, admin_conn: DbConnection) -> None:
    """
    Recreate the database.
    """
    # Drop the database, if exists. WITH (FORCE) atomically terminates any
    # lingering backends and drops the database, avoiding the race between a
    # separate pg_terminate_backend call and the drop.
    await admin_conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")

    # Create the database.
    await admin_conn.execute(f"CREATE DATABASE {db_name}")


class PytestDbConnection:
    def __init__(self, db_name: str) -> None:
        # Database name and DSN.
        self.db_name = db_name
        self.dsn = f"{_DSN_PREFIX}/{db_name}"
        self.pgbouncer_dsn = f"{_PGBOUNCER_DSN_PREFIX}/{db_name}"

        # Open a single connection, reused for every query on this database.
        self._conn = self._connect()
