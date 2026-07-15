from tests._api.generate_setup import GenerateSetup


def test_schema_create(gen_setup: GenerateSetup) -> None:
    """
    Schema present in target but missing in source -> CREATE SCHEMA.
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE SCHEMA banana"],
        diff=['CREATE SCHEMA "banana"'],
    )


def test_schema_drop(gen_setup: GenerateSetup) -> None:
    """
    Schema present in source but missing in target -> DROP SCHEMA.
    """
    gen_setup.assert_diff(
        src=["CREATE SCHEMA banana"],
        dst=[],
        diff=['DROP SCHEMA "banana"'],
    )


def test_schema_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to a schema present on both sides -> COMMENT ON SCHEMA.
    """
    gen_setup.assert_diff(
        src=["CREATE SCHEMA store"],
        dst=["CREATE SCHEMA store", "COMMENT ON SCHEMA store IS 'the store'"],
        diff=["COMMENT ON SCHEMA \"store\" IS 'the store'"],
    )
