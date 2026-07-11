from pgmig import generate
from tests.utils.db_utils import DbConnection


class GenerateSetup:
    """
    Utility class for testing `generate`.
    """

    def __init__(self, src_conn: DbConnection, dst_conn: DbConnection) -> None:
        self.src = src_conn
        self.dst = dst_conn

    def assert_migration_sql(self, expected: str | list[str], *, apply: bool = True) -> None:
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
        if apply and result:
            self.src.apply(result)
            residual = generate(source=self.src.dsn, target=self.dst.dsn)
            assert residual == "", f"\nMigration did not make source match target.\nResidual diff:\n{residual}"
