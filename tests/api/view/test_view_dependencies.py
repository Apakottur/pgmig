from tests.api.generate_setup import GenerateSetup


def _view_body(gen_setup: GenerateSetup, table: str, from_ref: str) -> str:
    """
    Get the view body, depending on the Postgres major version.
    """
    match gen_setup.pg_major:
        case 14 | 15:
            column = f"{table}.x"
        case _:
            column = "x"
    return f"SELECT {column}\n   FROM {from_ref}"


def test_view_on_view_create_ordering(gen_setup: GenerateSetup) -> None:
    """
    A view that reads another view is created after the view it reads.
    """
    gen_setup.dst.execute("CREATE VIEW base AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE VIEW derived AS SELECT x FROM base")

    gen_setup.assert_migration_sql(
        [
            'CREATE VIEW "public"."base" AS SELECT 1 AS x;',
            f'CREATE VIEW "public"."derived" AS {_view_body(gen_setup, "base", "public.base")};',
        ]
    )


def test_view_on_view_drop_ordering(gen_setup: GenerateSetup) -> None:
    """
    A view that reads another view is dropped before the view it reads.
    """
    gen_setup.assert_diff(
        src=["CREATE VIEW base AS SELECT 1 AS x", "CREATE VIEW derived AS SELECT x FROM base"],
        dst=[],
        diff=[
            'DROP VIEW "public"."derived"',
            'DROP VIEW "public"."base"',
        ],
    )


def test_view_on_view_definition_change_cascades(gen_setup: GenerateSetup) -> None:
    """
    Changing the base view's definition drops and recreates it; the dependent view, though
    its own definition is unchanged, is dragged into the recreate (Postgres will not drop a
    view another view still reads). Drops go dependent-first, creates dependency-first.
    """
    gen_setup.execute_both("CREATE VIEW base AS SELECT 1 AS x")
    gen_setup.execute_both("CREATE VIEW derived AS SELECT x FROM base")
    gen_setup.dst.execute("CREATE OR REPLACE VIEW base AS SELECT 2 AS x")

    gen_setup.assert_migration_sql(
        [
            'DROP VIEW "public"."derived";',
            'DROP VIEW "public"."base";',
            'CREATE VIEW "public"."base" AS SELECT 2 AS x;',
            f'CREATE VIEW "public"."derived" AS {_view_body(gen_setup, "base", "public.base")};',
        ]
    )


def test_view_on_view_transitive_cascade(gen_setup: GenerateSetup) -> None:
    """
    A chain a <- b <- c: changing a recreates all three, ordered by the full dependency
    chain (drops c, b, a; creates a, b, c).
    """
    gen_setup.execute_both("CREATE VIEW a AS SELECT 1 AS x")
    gen_setup.execute_both("CREATE VIEW b AS SELECT x FROM a")
    gen_setup.execute_both("CREATE VIEW c AS SELECT x FROM b")
    gen_setup.dst.execute("CREATE OR REPLACE VIEW a AS SELECT 2 AS x")

    gen_setup.assert_migration_sql(
        [
            'DROP VIEW "public"."c";',
            'DROP VIEW "public"."b";',
            'DROP VIEW "public"."a";',
            'CREATE VIEW "public"."a" AS SELECT 2 AS x;',
            f'CREATE VIEW "public"."b" AS {_view_body(gen_setup, "a", "public.a")};',
            f'CREATE VIEW "public"."c" AS {_view_body(gen_setup, "b", "public.b")};',
        ]
    )


def test_view_on_view_cross_schema(gen_setup: GenerateSetup) -> None:
    """
    A view-on-view dependency across schemas is ordered globally: the referenced view in
    one schema is created before the dependent view in another.
    """
    gen_setup.dst.execute("CREATE SCHEMA a")
    gen_setup.dst.execute("CREATE SCHEMA b")
    gen_setup.dst.execute("CREATE VIEW a.base AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE VIEW b.derived AS SELECT x FROM a.base")

    gen_setup.assert_migration_sql(
        [
            'CREATE SCHEMA "a";',
            'CREATE SCHEMA "b";',
            'CREATE VIEW "a"."base" AS SELECT 1 AS x;',
            f'CREATE VIEW "b"."derived" AS {_view_body(gen_setup, "base", "a.base")};',
        ]
    )


def test_view_on_view_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical view-on-view chains on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        both=["CREATE VIEW base AS SELECT 1 AS x", "CREATE VIEW derived AS SELECT x FROM base"],
        src=[],
        dst=[],
        diff=[],
    )
