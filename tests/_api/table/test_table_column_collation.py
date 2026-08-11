from tests._api.generate_setup import GenerateSetup


async def test_column_create_with_non_default_collation(gen_setup: GenerateSetup) -> None:
    """
    A target-only column with an explicit non-default collation renders COLLATE in the
    CREATE TABLE. The default collation of the type is never emitted (that would break
    idempotency for identical DBs), so only the explicit one shows up here.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=['CREATE TABLE t (c text COLLATE "C")'],
        diff=['CREATE TABLE "public"."t" ("c" text COLLATE "C")'],
    )


async def test_column_collation_changed(gen_setup: GenerateSetup) -> None:
    """
    A collation-only change on a shared column is folded into the type-change path: the type
    is unchanged but (type, collation) differs, so ALTER COLUMN ... TYPE <type> COLLATE "new"
    USING col reapplies it.
    """
    await gen_setup.assert_diff(
        src=['CREATE TABLE t (c text COLLATE "C")'],
        dst=['CREATE TABLE t (c text COLLATE "POSIX")'],
        diff=['ALTER TABLE "public"."t" ALTER COLUMN "c" TYPE text COLLATE "POSIX" USING "c"::text'],
    )


async def test_column_collation_removed_to_default(gen_setup: GenerateSetup) -> None:
    """
    Dropping an explicit collation back to the type default: ALTER COLUMN ... TYPE with no
    COLLATE clause resets the column to the type's default collation.
    """
    await gen_setup.assert_diff(
        src=['CREATE TABLE t (c text COLLATE "C")'],
        dst=["CREATE TABLE t (c text)"],
        diff=['ALTER TABLE "public"."t" ALTER COLUMN "c" TYPE text USING "c"::text'],
    )


async def test_column_unchanged_non_default_collation(gen_setup: GenerateSetup) -> None:
    """
    An identical explicit collation on both sides emits nothing -- introspection must report
    the collation the same way it renders, or an identical DB would spuriously diff.
    """
    await gen_setup.assert_diff(
        both=['CREATE TABLE t (c text COLLATE "C")'],
        src=[],
        dst=[],
        diff=[],
    )
