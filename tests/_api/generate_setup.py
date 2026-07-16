import pytest

from pgmig import PgmigUnsupportedError, agenerate
from pgmig._db import DbConnection


class GenerateSetup:
    """
    Utility class for testing `generate`.
    """

    def __init__(
        self,
        *,
        src_db_name: str,
        dst_db_name: str,
        src_conn: DbConnection,
        dst_conn: DbConnection,
        pg_major: int,
        unique_key: str,
    ) -> None:
        # Database names.
        self.src_db_name = src_db_name
        self.dst_db_name = dst_db_name

        # Database connections.
        self.src = src_conn
        self.dst = dst_conn

        # Postgres major version.
        self.pg_major = pg_major

        # Unique key for the test session.
        self.unique_key = unique_key

    async def assert_diff(
        self,
        *,
        src: list[str],
        dst: list[str],
        diff: list[str],
        both: list[str] | None = None,
        apply: bool = True,
        index_concurrently: bool = False,
        ignore_owner: bool = False,
    ) -> None:
        """
        Set up both databases, assert the generated migration, then apply and confirm it converges.

        Args:
            src: statements to run on the source database only.
            dst: statements to run on the target database only.
            diff: the expected migration SQL
            both: statements to run on both databases.
            apply: Whether to apply the migration to the source database and confirm it converges.
            index_concurrently: Pass through to `generate` to emit CONCURRENTLY index statements.
            ignore_owner: Pass through to `generate` to suppress ALTER ... OWNER TO statements.
        """
        # Shared setup runs on both DBs, before the side-specific statements.
        src = (both or []) + src
        dst = (both or []) + dst

        # Verify commands. A statement may contain internal newlines/semicolons (e.g. a
        # function body), but must not carry its own trailing terminator -- the helper joins
        # with ";\n" and appends the ";" to each diff statement itself.
        for cmd in src + dst + diff:
            if cmd.endswith(("\n", ";")):
                raise ValueError("Remove trailing newlines and semicolons from the statements to keep tests clean")

        # Execute commands.
        await self.src.execute(";\n".join(src))
        await self.dst.execute(";\n".join(dst))

        # Normalize to the "\n"-joined form that `generate` returns.
        expected_sql = "\n".join([f"{cmd};" for cmd in diff])

        # Generate the migration SQL.
        result = await agenerate(
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
            await self.src.execute(result)
            residual = await agenerate(
                source=self.src.dsn,
                target=self.dst.dsn,
                index_concurrently=index_concurrently,
                ignore_owner=ignore_owner,
            )
            assert residual == "", f"\nMigration did not make source match target.\nResidual diff:\n{residual}"

    async def assert_unsupported(
        self,
        *,
        src: list[str],
        dst: list[str],
        both: list[str] | None = None,
        match: str | None = None,
    ) -> None:
        """
        Wrapper around `assert_diff` that asserts the migration refuses the change with a
        PgmigUnsupportedError (a documented limitation, not a bug).
        """
        with pytest.raises(PgmigUnsupportedError, match=match):
            await self.assert_diff(
                src=src,
                dst=dst,
                both=both,
                diff=[],
                apply=False,
            )
