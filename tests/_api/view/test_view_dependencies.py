from tests._api.generate_setup import GenerateSetup


async def test_view_on_view_create_ordering(gen_setup: GenerateSetup) -> None:
    """
    A view that reads another view is created after the view it reads.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE VIEW base AS SELECT 1 AS x", "CREATE VIEW derived AS SELECT x FROM base"],
        diff=[
            'CREATE VIEW "public"."base" AS SELECT 1 AS x',
            f'CREATE VIEW "public"."derived" AS {gen_setup.select_body("x", "base", "public.base")}',
        ],
    )


async def test_view_on_view_drop_ordering(gen_setup: GenerateSetup) -> None:
    """
    A view that reads another view is dropped before the view it reads.
    """
    await gen_setup.assert_diff(
        src=["CREATE VIEW base AS SELECT 1 AS x", "CREATE VIEW derived AS SELECT x FROM base"],
        dst=[],
        diff=[
            'DROP VIEW "public"."derived"',
            'DROP VIEW "public"."base"',
        ],
    )


async def test_view_on_view_definition_change_cascades(gen_setup: GenerateSetup) -> None:
    """
    Changing the base view's definition drops and recreates it; the dependent view, though
    its own definition is unchanged, is dragged into the recreate (Postgres will not drop a
    view another view still reads). Drops go dependent-first, creates dependency-first.
    """
    await gen_setup.assert_diff(
        both=["CREATE VIEW base AS SELECT 1 AS x", "CREATE VIEW derived AS SELECT x FROM base"],
        src=[],
        dst=["CREATE OR REPLACE VIEW base AS SELECT 2 AS x"],
        diff=[
            'DROP VIEW "public"."derived"',
            'DROP VIEW "public"."base"',
            'CREATE VIEW "public"."base" AS SELECT 2 AS x',
            f'CREATE VIEW "public"."derived" AS {gen_setup.select_body("x", "base", "public.base")}',
        ],
    )


async def test_view_on_view_transitive_cascade(gen_setup: GenerateSetup) -> None:
    """
    A chain a <- b <- c: changing a recreates all three, ordered by the full dependency
    chain (drops c, b, a; creates a, b, c).
    """
    await gen_setup.assert_diff(
        both=[
            "CREATE VIEW a AS SELECT 1 AS x",
            "CREATE VIEW b AS SELECT x FROM a",
            "CREATE VIEW c AS SELECT x FROM b",
        ],
        src=[],
        dst=["CREATE OR REPLACE VIEW a AS SELECT 2 AS x"],
        diff=[
            'DROP VIEW "public"."c"',
            'DROP VIEW "public"."b"',
            'DROP VIEW "public"."a"',
            'CREATE VIEW "public"."a" AS SELECT 2 AS x',
            f'CREATE VIEW "public"."b" AS {gen_setup.select_body("x", "a", "public.a")}',
            f'CREATE VIEW "public"."c" AS {gen_setup.select_body("x", "b", "public.b")}',
        ],
    )


async def test_view_on_view_cross_schema(gen_setup: GenerateSetup) -> None:
    """
    A view-on-view dependency across schemas is ordered globally: the referenced view in
    one schema is created before the dependent view in another.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE SCHEMA a",
            "CREATE SCHEMA b",
            "CREATE VIEW a.base AS SELECT 1 AS x",
            "CREATE VIEW b.derived AS SELECT x FROM a.base",
        ],
        diff=[
            'CREATE SCHEMA "a"',
            'CREATE SCHEMA "b"',
            'CREATE VIEW "a"."base" AS SELECT 1 AS x',
            f'CREATE VIEW "b"."derived" AS {gen_setup.select_body("x", "base", "a.base")}',
        ],
    )


async def test_view_on_view_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical view-on-view chains on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=["CREATE VIEW base AS SELECT 1 AS x", "CREATE VIEW derived AS SELECT x FROM base"],
        src=[],
        dst=[],
        diff=[],
    )
