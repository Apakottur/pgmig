import pytest

from pgmig import generate
from tests.api.generate_setup import GenerateSetup


def test_composite_type_create(gen_setup: GenerateSetup) -> None:
    """
    Composite type present in target but missing in source -> CREATE TYPE.
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE TYPE pair AS (a integer, b integer)"],
        diff=['CREATE TYPE "public"."pair" AS ("a" integer, "b" integer)'],
    )


def test_composite_type_drop(gen_setup: GenerateSetup) -> None:
    """
    Composite type present in source but missing in target -> DROP TYPE.
    """
    gen_setup.assert_diff(
        src=["CREATE TYPE pair AS (a integer, b integer)"],
        dst=[],
        diff=['DROP TYPE "public"."pair"'],
    )


def test_composite_type_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical composite type on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        both=["CREATE TYPE pair AS (a integer, b integer)"],
        src=[],
        dst=[],
        diff=[],
    )


def test_composite_type_field_change_raises(gen_setup: GenerateSetup) -> None:
    """
    A field-level change on a type present in both sides is not supported yet (ALTER TYPE
    deferred) -> NotImplementedError.
    """
    gen_setup.src.execute("CREATE TYPE pair AS (a integer, b integer)")
    gen_setup.dst.execute("CREATE TYPE pair AS (a integer, b bigint)")

    with pytest.raises(NotImplementedError, match="Composite type field change is not supported"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)


def test_composite_type_comment(gen_setup: GenerateSetup) -> None:
    """
    A composite type comment is synced with COMMENT ON TYPE.
    """
    gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TYPE pair AS (a integer, b integer)",
            "COMMENT ON TYPE pair IS 'hi'",
        ],
        diff=[
            'CREATE TYPE "public"."pair" AS ("a" integer, "b" integer)',
            'COMMENT ON TYPE "public"."pair" IS \'hi\'',
        ],
    )
