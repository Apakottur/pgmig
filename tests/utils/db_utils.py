from typing import Any

import psycopg
import tenacity
from psycopg import sql
from typing_extensions import LiteralString

_DSN_PREFIX = "postgresql://pgmig:pgmig@localhost:55432"
_ADMIN_DB_NAME = "postgres"
_ADMIN_DSN = f"{_DSN_PREFIX}/{_ADMIN_DB_NAME}"


class DbConnection:
    def __init__(self, db_name: str) -> None:
        self.db_name = db_name
        self.dsn = f"{_DSN_PREFIX}/{db_name}"

        # Recreate the database (if not admin DB).
        if db_name != _ADMIN_DB_NAME:
            self._recreate_database()

        # Wait for the database to be ready.
        self._wait_for_conn()

    def _recreate_database(self) -> None:
        with psycopg.connect(_ADMIN_DSN, autocommit=True) as conn:
            # Drop the database, if exists. WITH (FORCE) atomically terminates any
            # lingering backends and drops the database, avoiding the race between a
            # separate pg_terminate_backend call and the drop.
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {db_name} WITH (FORCE)").format(db_name=sql.Identifier(self.db_name))
            )

            # Create the database.
            conn.execute(sql.SQL("CREATE DATABASE {db_name}").format(db_name=sql.Identifier(self.db_name)))

    @tenacity.retry(
        wait=tenacity.wait_fixed(0.5),
        stop=tenacity.stop_after_delay(10),
        reraise=True,
    )
    def _wait_for_conn(self) -> None:
        """
        Wait until a DB connection can be established.
        """
        result = self.execute("SELECT 1")
        assert result == [(1,)]

    def execute(self, query: LiteralString | sql.Composed) -> list[tuple[Any, ...]]:
        """
        Execute a SQL statement against this database.
        """
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            # Execute the query.
            result = conn.execute(query)

            # Fetch query results.
            if result.description is None:
                return []
            else:
                return result.fetchall()
