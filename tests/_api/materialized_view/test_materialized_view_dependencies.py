from tests._api.generate_setup import GenerateSetup


def _reads(gen_setup: GenerateSetup, column: str, rel: str, from_ref: str) -> str:
    """
    A matview/view body `SELECT <column> FROM <from_ref>` as pg_get_viewdef renders it: PG
    14/15 qualify the column with the reading relation name, 16+ do not. FROM is always
    schema-qualified (introspection runs with an empty search_path).
    """
    rendered = f"{rel}.{column}" if gen_setup.pg_major in (14, 15) else column
    return f"SELECT {rendered}\n   FROM {from_ref}"


async def test_matview_on_view_create_ordering(gen_setup: GenerateSetup) -> None:
    """
    A matview reading a plain view is created after the view (view in VIEW_CREATE, matview in
    the later MATVIEW_CREATE phase).
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE VIEW v AS SELECT 1 AS x",
            "CREATE MATERIALIZED VIEW m AS SELECT x FROM v",
        ],
        diff=[
            'CREATE VIEW "public"."v" AS SELECT 1 AS x',
            f'CREATE MATERIALIZED VIEW "public"."m" AS {_reads(gen_setup, "x", "v", "public.v")} WITH NO DATA',
        ],
    )


async def test_matview_on_view_drop_ordering(gen_setup: GenerateSetup) -> None:
    """
    A matview reading a plain view is dropped before the view (matview in MATVIEW_DROP, view in
    the later VIEW_DROP phase) -- Postgres refuses to drop a view a matview still reads.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE VIEW v AS SELECT 1 AS x",
            "CREATE MATERIALIZED VIEW m AS SELECT x FROM v",
        ],
        dst=[],
        diff=[
            'DROP MATERIALIZED VIEW "public"."m"',
            'DROP VIEW "public"."v"',
        ],
    )


async def test_matview_on_matview_chain_create_ordering(gen_setup: GenerateSetup) -> None:
    """
    A 3-deep matview chain (a_top -> m_mid -> z_base) is created dependencies-first, regardless
    of name order (the names sort opposite to the dependency order).
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE MATERIALIZED VIEW z_base AS SELECT 1 AS x",
            "CREATE MATERIALIZED VIEW m_mid AS SELECT x FROM z_base",
            "CREATE MATERIALIZED VIEW a_top AS SELECT x FROM m_mid",
        ],
        diff=[
            'CREATE MATERIALIZED VIEW "public"."z_base" AS SELECT 1 AS x WITH NO DATA',
            f'CREATE MATERIALIZED VIEW "public"."m_mid" AS {_reads(gen_setup, "x", "z_base", "public.z_base")}'
            " WITH NO DATA",
            f'CREATE MATERIALIZED VIEW "public"."a_top" AS {_reads(gen_setup, "x", "m_mid", "public.m_mid")}'
            " WITH NO DATA",
        ],
    )


async def test_matview_on_matview_chain_drop_ordering(gen_setup: GenerateSetup) -> None:
    """
    The same 3-deep chain is dropped dependents-first (a_top -> m_mid -> z_base).
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE MATERIALIZED VIEW z_base AS SELECT 1 AS x",
            "CREATE MATERIALIZED VIEW m_mid AS SELECT x FROM z_base",
            "CREATE MATERIALIZED VIEW a_top AS SELECT x FROM m_mid",
        ],
        dst=[],
        diff=[
            'DROP MATERIALIZED VIEW "public"."a_top"',
            'DROP MATERIALIZED VIEW "public"."m_mid"',
            'DROP MATERIALIZED VIEW "public"."z_base"',
        ],
    )


async def test_matview_recreated_when_read_view_definition_changes(gen_setup: GenerateSetup) -> None:
    """
    A view definition change recreates the view, and the matview reading it (and the matview's
    index) must be recreated too, in dependency order.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE VIEW v AS SELECT 1 AS x",
            "CREATE MATERIALIZED VIEW m AS SELECT x FROM v",
            "CREATE INDEX m_x_idx ON m (x)",
        ],
        dst=[
            "CREATE VIEW v AS SELECT 2 AS x",
            "CREATE MATERIALIZED VIEW m AS SELECT x FROM v",
            "CREATE INDEX m_x_idx ON m (x)",
        ],
        diff=[
            'DROP MATERIALIZED VIEW "public"."m"',
            'DROP VIEW "public"."v"',
            'CREATE VIEW "public"."v" AS SELECT 2 AS x',
            f'CREATE MATERIALIZED VIEW "public"."m" AS {_reads(gen_setup, "x", "v", "public.v")} WITH NO DATA',
            "CREATE INDEX m_x_idx ON public.m USING btree (x)",
        ],
    )


async def test_matview_recreate_cascades_through_matview_chain(gen_setup: GenerateSetup) -> None:
    """
    A base matview whose definition changes is recreated, and the matview reading it cascades
    into the recreate set (drop dependents-first, create dependencies-first).
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE MATERIALIZED VIEW base AS SELECT 1 AS x",
            "CREATE MATERIALIZED VIEW derived AS SELECT x FROM base",
        ],
        dst=[
            "CREATE MATERIALIZED VIEW base AS SELECT 2 AS x",
            "CREATE MATERIALIZED VIEW derived AS SELECT x FROM base",
        ],
        diff=[
            'DROP MATERIALIZED VIEW "public"."derived"',
            'DROP MATERIALIZED VIEW "public"."base"',
            'CREATE MATERIALIZED VIEW "public"."base" AS SELECT 2 AS x WITH NO DATA',
            f'CREATE MATERIALIZED VIEW "public"."derived" AS {_reads(gen_setup, "x", "base", "public.base")}'
            " WITH NO DATA",
        ],
    )


async def test_matview_recreate_cascades_through_retyped_column(gen_setup: GenerateSetup) -> None:
    """
    A retyped table column recreates the matview reading it, and that recreate cascades to a
    matview reading the first matview.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE t (id int, val integer)",
            "CREATE MATERIALIZED VIEW base AS SELECT val FROM t",
            "CREATE MATERIALIZED VIEW derived AS SELECT val FROM base",
        ],
        dst=[
            "CREATE TABLE t (id int, val bigint)",
            "CREATE MATERIALIZED VIEW base AS SELECT val FROM t",
            "CREATE MATERIALIZED VIEW derived AS SELECT val FROM base",
        ],
        diff=[
            'DROP MATERIALIZED VIEW "public"."derived"',
            'DROP MATERIALIZED VIEW "public"."base"',
            'ALTER TABLE "public"."t" ALTER COLUMN "val" TYPE bigint USING "val"::bigint',
            f'CREATE MATERIALIZED VIEW "public"."base" AS {_reads(gen_setup, "val", "t", "public.t")} WITH NO DATA',
            f'CREATE MATERIALIZED VIEW "public"."derived" AS {_reads(gen_setup, "val", "base", "public.base")}'
            " WITH NO DATA",
        ],
    )


async def test_view_reads_matview_still_raises(gen_setup: GenerateSetup) -> None:
    """
    A plain view reading a materialized view stays unsupported: the matview is created in a
    later phase than the view, so the view cannot be ordered before its matview dependency.
    """
    await gen_setup.assert_unsupported(
        src=[],
        dst=[
            "CREATE MATERIALIZED VIEW mv AS SELECT 1 AS x",
            "CREATE VIEW v AS SELECT x FROM mv",
        ],
        match="materialized view",
    )
