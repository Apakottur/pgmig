from tests._api.generate_setup import GenerateSetup


def test_table_create(gen_setup: GenerateSetup) -> None:
    """
    Table present in target but missing in source -> CREATE TABLE.
    """
   await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE person (name text)"],
        diff=['CREATE TABLE "public"."person" ("name" text)'],
    )


def test_table_create_with_quote_in_name(gen_setup: GenerateSetup) -> None:
    """
    A table (and column) whose name contains a double quote is quoted correctly:
    the embedded quote is doubled, so the emitted DDL is valid and converges.
    """
   await gen_setup.assert_diff(
        src=[],
        dst=['CREATE TABLE "we""ird" ("c""ol" text)'],
        diff=['CREATE TABLE "public"."we""ird" ("c""ol" text)'],
    )


def test_table_drop(gen_setup: GenerateSetup) -> None:
    """
    Table present in source but missing in target -> DROP TABLE.
    """
   await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=[],
        diff=['DROP TABLE "public"."person"'],
    )


def test_table_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical table on both sides -> no migration SQL.
    """
   await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=["CREATE TABLE person (name text)"],
        diff=[],
    )


def test_table_create_zero_columns(gen_setup: GenerateSetup) -> None:
    """
    A table with no columns still has a pg_class row; it must be introspected (via the
    LEFT JOIN to pg_attribute) and created, not silently invisible.
    """
   await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE marker ()"],
        diff=['CREATE TABLE "public"."marker" ()'],
    )
