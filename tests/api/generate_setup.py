from psycopg import sql
from typing_extensions import LiteralString

from pgmig import generate
from tests.fixtures.db_utils import DbConnection


class GenerateSetup:
    """
    Utility class for testing `generate`.
    """

    def __init__(self, src_conn: DbConnection, dst_conn: DbConnection) -> None:
        self.src = src_conn
        self.dst = dst_conn

    @property
    def pg_major(self) -> int:
        """
        Get the Postgres major version of the server under test (e.g. 16).
        """
        (row,) = self.src.execute("SHOW server_version_num")
        return int(row[0]) // 10000

    def execute_both(self, query: LiteralString | sql.Composed) -> None:
        """
        Run the same query on both the source and target databases.
        """
        self.src.execute(query)
        self.dst.execute(query)

    def assert_diff(
        self,
        *,
        src: list[str],
        dst: list[str],
        diff: list[str],
        apply: bool = True,
        index_concurrently: bool = False,
        ignore_owner: bool = False,
    ) -> None:
        """
        Set up both databases, assert the generated migration, then apply and confirm it converges.

        Args:
            src: statements to run on the source database.
            dst: statements to run on the target database.
            diff: the expected migration SQL
            apply: Whether to apply the migration to the source database and confirm it converges.
            index_concurrently: Pass through to `generate` to emit CONCURRENTLY index statements.
            ignore_owner: Pass through to `generate` to suppress ALTER ... OWNER TO statements.
        """
        # Verify commands.
        for cmd in src + dst + diff:
            if "\n" in cmd or ";" in cmd:
                raise ValueError("Remove new lines and semicolons from the statements to keep tests clean")

        # Execute commands.
        self.src.execute(";\n".join(src))  # ty: ignore[invalid-argument-type]
        self.dst.execute(";\n".join(dst))  # ty: ignore[invalid-argument-type]

        # Normalize to the "\n"-joined form that `generate` returns.
        expected_sql = "\n".join([f"{cmd};" for cmd in diff])

        # Generate the migration SQL.
        result = generate(
            source=self.src.dsn,
            target=self.dst.dsn,
            index_concurrently=index_concurrently,
            ignore_owner=ignore_owner,
        )

        # Verify the result.
        assert result == expected_sql, f"\nExpected SQL:\n{expected_sql}\nGenerated SQL:\n{result}"

        # Apply the migration to the source and confirm it converges: after applying,
        # source should match target, so a second generate must produce nothing.
        if apply and result:
            self.src.execute(result)  # ty: ignore[invalid-argument-type]
            residual = generate(
                source=self.src.dsn,
                target=self.dst.dsn,
                index_concurrently=index_concurrently,
                ignore_owner=ignore_owner,
            )
            assert residual == "", f"\nMigration did not make source match target.\nResidual diff:\n{residual}"

    def assert_migration_sql(
        self,
        expected: str | list[str],
        *,
        apply: bool = True,
        index_concurrently: bool = False,
        ignore_owner: bool = False,
    ) -> None:
        """
        Assert that the migration SQL generated from the source database to the target database is as expected.

        Args:
            expected: The expected migration SQL, as a string or list of strings.
            apply: Whether to apply the migration to the source database and confirm it converges.
            index_concurrently: Pass through to `generate` to emit CONCURRENTLY index statements.
            ignore_owner: Pass through to `generate` to suppress ALTER ... OWNER TO statements.
        """
        # Multi-statement expectations must be passed as a list, not a "\n"-joined string.
        if isinstance(expected, str) and "\n" in expected:
            raise ValueError("Pass multi-statement expectations as a list of strings, not a '\\n'-joined string.")

        # Normalize to the "\n"-joined form that `generate` returns.
        expected_sql = "\n".join(expected) if isinstance(expected, list) else expected

        # Generate the migration SQL.
        result = generate(
            source=self.src.dsn, target=self.dst.dsn, index_concurrently=index_concurrently, ignore_owner=ignore_owner
        )

        # Verify the result.
        assert result == expected_sql, f"\nExpected SQL:\n{expected_sql}\nGenerated SQL:\n{result}"

        # Apply the migration to the source and confirm it converges: after applying,
        # source should match target, so a second generate must produce nothing.
        # The whole migration is run as one script; individual statements are
        # ";"-terminated and may themselves span multiple lines (e.g. functions),
        # so it must not be split on newlines. CONCURRENTLY statements cannot run in a
        # transaction, but the test connections are autocommit, so they apply directly.
        if apply and result:
            self.src.execute(result)  # ty: ignore[invalid-argument-type]
            residual = generate(
                source=self.src.dsn,
                target=self.dst.dsn,
                index_concurrently=index_concurrently,
                ignore_owner=ignore_owner,
            )
            assert residual == "", f"\nMigration did not make source match target.\nResidual diff:\n{residual}"
