import hashlib
import re
from typing import Any

import psycopg
import tenacity
from psycopg import sql
from typing_extensions import LiteralString

_DSN_PREFIX = "postgresql://pgmig:pgmig@localhost:15432"
_PGBOUNCER_DSN_PREFIX = "postgresql://pgmig:pgmig@localhost:16432"
_ADMIN_DB_NAME = "postgres"


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


class DbConnection:
    def __init__(self, db_name: str, admin_conn: "DbConnection | None" = None) -> None:
        # Database name and DSN.
        self.db_name = db_name
        self.dsn = f"{_DSN_PREFIX}/{db_name}"
        self.pgbouncer_dsn = f"{_PGBOUNCER_DSN_PREFIX}/{db_name}"

        # Admin connection.
        self._admin_conn = admin_conn

        # Recreate the database (if not admin DB).
        if db_name != _ADMIN_DB_NAME:
            self._recreate_database()

        # Open a single connection, reused for every query on this database.
        self._conn = self._connect()

    def _recreate_database(self) -> None:
        """
        Recreate the database.
        """
        assert self._admin_conn is not None

        # Drop the database, if exists. WITH (FORCE) atomically terminates any
        # lingering backends and drops the database, avoiding the race between a
        # separate pg_terminate_backend call and the drop.
        self._admin_conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {db_name} WITH (FORCE)").format(db_name=sql.Identifier(self.db_name))
        )

        # Create the database.
        self._admin_conn.execute(sql.SQL("CREATE DATABASE {db_name}").format(db_name=sql.Identifier(self.db_name)))

    @tenacity.retry(
        wait=tenacity.wait_fixed(0.5),
        stop=tenacity.stop_after_delay(10),
        reraise=True,
    )
    def _connect(self) -> psycopg.Connection:
        """
        Open a connection, retrying until the database is ready to accept them.
        """
        return psycopg.connect(self.dsn, autocommit=True)

    def close(self) -> None:
        """
        Close the connection.
        """
        self._conn.close()

    def execute(self, query: LiteralString | sql.Composed) -> list[tuple[Any, ...]]:
        """
        Execute a SQL statement against this database on the reused connection.
        """
        result = self._conn.execute(query)

        # Fetch query results.
        if result.description is None:
            return []
        else:
            return result.fetchall()
