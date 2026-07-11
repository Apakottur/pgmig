from pgmig import generate
from tests.utils.db_utils import DbConnection


class GenerateSetup:
    """
    Utility class for testing `generate`.
    """

    def __init__(self, src_conn: DbConnection, dst_conn: DbConnection) -> None:
        self.src = src_conn
        self.dst = dst_conn

    def assert_migration_sql(self, expected: str) -> None:
        # Generate the migration SQL.
        result = generate(source=self.src.dsn, target=self.dst.dsn)

        # Verify the result.
        assert result == expected
