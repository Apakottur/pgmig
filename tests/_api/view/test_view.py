from tests._api.generate_setup import GenerateSetup


def test_view_create(gen_setup: GenerateSetup) -> None:
    """
    View present in target but missing in source -> CREATE VIEW.
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE VIEW active AS SELECT 1 AS x"],
        diff=['CREATE VIEW "public"."active" AS SELECT 1 AS x'],
    )


def test_view_drop(gen_setup: GenerateSetup) -> None:
    """
    View present in source but missing in target -> DROP VIEW.
    """
    gen_setup.assert_diff(
        src=["CREATE VIEW active AS SELECT 1 AS x"],
        dst=[],
        diff=['DROP VIEW "public"."active"'],
    )


def test_view_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical view on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        both=["CREATE VIEW active AS SELECT 1 AS x"],
        src=[],
        dst=[],
        diff=[],
    )


def test_view_definition_change(gen_setup: GenerateSetup) -> None:
    """
    A changed view definition -> drop and recreate.
    """
    gen_setup.assert_diff(
        src=["CREATE VIEW active AS SELECT 1 AS x"],
        dst=["CREATE VIEW active AS SELECT 2 AS x"],
        diff=[
            'DROP VIEW "public"."active"',
            'CREATE VIEW "public"."active" AS SELECT 2 AS x',
        ],
    )


def test_view_comment(gen_setup: GenerateSetup) -> None:
    """
    A view comment is synced with COMMENT ON VIEW.
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE VIEW active AS SELECT 1 AS x", "COMMENT ON VIEW active IS 'hi'"],
        diff=[
            'CREATE VIEW "public"."active" AS SELECT 1 AS x',
            'COMMENT ON VIEW "public"."active" IS \'hi\'',
        ],
    )
