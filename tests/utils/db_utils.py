from typing import Any, LiteralString

import psycopg
import tenacity
from psycopg import sql

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
            # Disconnect all DB connections.
            conn.execute(
                sql.SQL("SELECT pg_terminate_backend(pid) FROM pg_stat_activity where datname='{0}'").format(
                    self.db_name
                )
            )

            # Drop the database, if exists.
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {0}").format(self.db_name))

            # Create the database.
            conn.execute(sql.SQL("CREATE DATABASE {0}").format(self.db_name))

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

    def reset(self) -> None:
        """
        Reset the database to initial state.
        """
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            # Get all schemas.
            schemas = conn.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'"
            ).fetchall()

            # Drop all schemas.
            for (schema_name,) in schemas:
                conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {0}").format(schema_name))

            # Create the public schema.
            conn.execute("CREATE SCHEMA public")

    def execute(self, query: LiteralString) -> list[tuple[Any, ...]]:
        """
        Execute a SQL statement against this database.
        """
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            # Execute the query.
            result = conn.execute(query)

            # Fetch the results.
            return result.fetchall()
