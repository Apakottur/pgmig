from psycopg import sql
from typing_extensions import LiteralString

from pgmig import generate
from tests.utils.db_utils import DbConnection


class GenerateSetup:
    """
    Utility class for testing `generate`.
    """

    def __init__(self, src_conn: DbConnection, dst_conn: DbConnection) -> None:
        self.src = src_conn
        self.dst = dst_conn

    def execute_both(self, query: LiteralString | sql.Composed) -> None:
        """
        Run the same query on both the source and target databases.
        """
        self.src.execute(query)
        self.dst.execute(query)

    def assert_migration_sql(self, expected: str | list[str], *, apply: bool = True) -> None:
        """
        Assert that the migration SQL generated from the source database to the target database is as expected.

        Args:
            expected: The expected migration SQL, as a string or list of strings.
            apply: Whether to apply the migration to the source database and confirm it converges.
        """
        # Multi-statement expectations must be passed as a list, not a "\n"-joined string.
        if isinstance(expected, str) and "\n" in expected:
            raise ValueError("Pass multi-statement expectations as a list of strings, not a '\\n'-joined string.")

        # Normalize to the "\n"-joined form that `generate` returns.
        expected_sql = "\n".join(expected) if isinstance(expected, list) else expected

        # Generate the migration SQL.
        result = generate(source=self.src.dsn, target=self.dst.dsn)

        # Verify the result.
        assert result == expected_sql, f"\nExpected SQL:\n{expected_sql}\nGenerated SQL:\n{result}"

        # Apply the migration to the source and confirm it converges: after applying,
        # source should match target, so a second generate must produce nothing.
        # The whole migration is run as one script; individual statements are
        # ";"-terminated and may themselves span multiple lines (e.g. functions),
        # so it must not be split on newlines.
        if apply and result:
            self.src.execute(result)  # ty: ignore[invalid-argument-type]
            residual = generate(source=self.src.dsn, target=self.dst.dsn)
            assert residual == "", f"\nMigration did not make source match target.\nResidual diff:\n{residual}"
