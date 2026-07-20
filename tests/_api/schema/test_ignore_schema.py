import pytest

from pgmig import PgmigUnsupportedError, agenerate
from pgmig._db import UniqueViolation
from tests._api.generate_setup import GenerateSetup
from tests._api.schema.test_extension import _get_installable_extension

# Every object kind, all inside one schema, with rich within-schema wiring (a table with a
# primary key, check, index, RLS policy and trigger; a sequence, enum, domain, composite type,
# range type, function, view, materialized view + its index, and a schema-scoped default
# privilege). Ignoring the schema must drop all of it -- exercising every loader's filter and
# proving the attach-loaders (index/constraint/trigger/policy/matview-index) don't KeyError when
# their parent was filtered out.
_ALL_KINDS = [
    "CREATE SCHEMA ext",
    "CREATE SEQUENCE ext.seq",
    "CREATE TYPE ext.mood AS ENUM ('happy', 'sad')",
    "CREATE DOMAIN ext.positive AS integer CHECK (VALUE > 0)",
    "CREATE TYPE ext.pair AS (a integer, b integer)",
    "CREATE TYPE ext.int_range AS RANGE (SUBTYPE = integer)",
    "CREATE FUNCTION ext.trig_fn() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END;$$",
    "CREATE TABLE ext.t (id integer PRIMARY KEY, m ext.mood, n integer DEFAULT nextval('ext.seq'), CHECK (n >= 0))",
    "CREATE INDEX ext_t_n_idx ON ext.t (n)",
    "CREATE TRIGGER ext_t_trig BEFORE INSERT ON ext.t FOR EACH ROW EXECUTE FUNCTION ext.trig_fn()",
    "ALTER TABLE ext.t ENABLE ROW LEVEL SECURITY",
    "CREATE POLICY ext_t_pol ON ext.t USING (true)",
    "CREATE VIEW ext.v AS SELECT id FROM ext.t",
    "CREATE MATERIALIZED VIEW ext.mv AS SELECT id FROM ext.t",
    "CREATE INDEX ext_mv_idx ON ext.mv (id)",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA ext GRANT SELECT ON TABLES TO PUBLIC",
]


async def test_ignore_schema_suppresses_every_object_kind(gen_setup: GenerateSetup) -> None:
    """
    One schema holding every object kind, all present only on the target: ignoring it yields an
    empty diff -- nothing in it is loaded, and no attach-loader KeyErrors on a filtered parent.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=_ALL_KINDS,
        diff=[],
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_suppresses_extension(gen_setup: GenerateSetup) -> None:
    """
    An extension installed into an ignored schema is excluded.
    """
    ext = await _get_installable_extension(gen_setup.src)
    await gen_setup.assert_diff(
        both=["CREATE SCHEMA ext"],
        src=[],
        dst=[f"CREATE EXTENSION {ext.name} SCHEMA ext"],
        diff=[],
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_suppresses_create(gen_setup: GenerateSetup) -> None:
    """
    A schema (and its objects) present only on the target is normally created; with
    --ignore-schema it is excluded entirely -- no CREATE SCHEMA, no objects inside it.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE SCHEMA ext", "CREATE TABLE ext.t (n integer)", "CREATE SEQUENCE ext.s"],
        diff=[],
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_suppresses_drop(gen_setup: GenerateSetup) -> None:
    """
    A schema present only on the source is normally dropped; with --ignore-schema it is left
    alone -- no DROP of the schema or its objects.
    """
    await gen_setup.assert_diff(
        src=["CREATE SCHEMA ext", "CREATE TABLE ext.t (n integer)"],
        dst=[],
        diff=[],
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_ignores_object_drift(gen_setup: GenerateSetup) -> None:
    """
    Differences in objects inside an ignored schema (present on both sides) produce no diff.
    """
    await gen_setup.assert_diff(
        both=["CREATE SCHEMA ext"],
        src=["CREATE TABLE ext.t (n integer)"],
        dst=["CREATE TABLE ext.t (n integer, extra text)", "CREATE VIEW ext.v AS SELECT 1 AS x"],
        diff=[],
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_leaves_other_schemas(gen_setup: GenerateSetup) -> None:
    """
    Only the named schema is ignored: drift in other schemas is still diffed normally.
    """
    await gen_setup.assert_diff(
        both=["CREATE SCHEMA ext"],
        src=[],
        dst=[
            "CREATE TABLE ext.ignored (n integer)",
            "CREATE TABLE public.kept (n integer)",
        ],
        diff=['CREATE TABLE "public"."kept" ("n" integer)'],
        ignore_schemas=["ext"],
    )


async def test_ignore_multiple_schemas(gen_setup: GenerateSetup) -> None:
    """
    Every schema in the list is ignored.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE SCHEMA a",
            "CREATE TABLE a.t (n integer)",
            "CREATE SCHEMA b",
            "CREATE TABLE b.t (n integer)",
        ],
        diff=[],
        ignore_schemas=["a", "b"],
    )


async def test_ignore_schema_still_guards_unsupported(gen_setup: GenerateSetup) -> None:
    """
    An unsupported object (a rule) in an ignored schema still trips the unsupported guard: the
    guards are not exempted by --ignore-schema, so pgmig refuses a database it cannot fully
    process even when the offending object is in an ignored (but isolated) schema.
    """
    await gen_setup.assert_unsupported(
        src=[],
        dst=[
            "CREATE SCHEMA ext",
            "CREATE TABLE ext.t (n integer)",
            "CREATE RULE ext_no_insert AS ON INSERT TO ext.t DO INSTEAD NOTHING",
        ],
        match=r"not supported",
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_still_guards_invalid_index(gen_setup: GenerateSetup) -> None:
    """
    An invalid index in an ignored schema still trips the invalid-index guard.
    """
    await gen_setup.src.execute("CREATE SCHEMA ext")
    await gen_setup.src.execute("CREATE TABLE ext.t (a integer)")
    await gen_setup.src.execute("INSERT INTO ext.t VALUES (1), (1)")
    with pytest.raises(UniqueViolation):
        await gen_setup.src.execute("CREATE UNIQUE INDEX CONCURRENTLY u ON ext.t (a)")

    with pytest.raises(PgmigUnsupportedError, match=r"invalid index"):
        await agenerate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn, ignore_schemas=["ext"])


async def test_ignore_schema_excludes_matview_dependency_edges(gen_setup: GenerateSetup) -> None:
    """
    A matview reading another matview records a dependency edge in matview_dependencies.load;
    when both sit in the ignored schema the edge is dropped, so no ignored matview leaks into the
    dependency map (its rows carry dependent_schema/referenced_schema, not the shared filter's
    schema_name, so load skips them itself).
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE SCHEMA ext",
            "CREATE MATERIALIZED VIEW ext.base AS SELECT 1 AS x",
            "CREATE MATERIALIZED VIEW ext.derived AS SELECT x FROM ext.base",
        ],
        diff=[],
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_still_guards_matview_dependency(gen_setup: GenerateSetup) -> None:
    """
    A plain view reading a materialized view is refused even inside an ignored schema: the
    matview-dependency guard is not exempted by --ignore-schema.
    """
    await gen_setup.assert_unsupported(
        src=[],
        dst=[
            "CREATE SCHEMA ext",
            "CREATE MATERIALIZED VIEW ext.m AS SELECT 1 AS x",
            "CREATE VIEW ext.v AS SELECT x FROM ext.m",
        ],
        match=r"not supported",
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_refuses_ignored_depends_on_kept(gen_setup: GenerateSetup) -> None:
    """
    An object in the ignored schema depending on a kept one (ext.child -> public.k) means the
    schema is not isolated -- dropping/recreating public.k would be blocked by ext.child at
    apply -- so ignoring it is refused.
    """
    await gen_setup.assert_unsupported(
        src=[],
        dst=[
            "CREATE TABLE public.k (id integer PRIMARY KEY)",
            "CREATE SCHEMA ext",
            "CREATE TABLE ext.child (id integer REFERENCES public.k (id))",
        ],
        match=r"connected",
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_refuses_kept_depends_on_ignored(gen_setup: GenerateSetup) -> None:
    """
    A kept object depending on one in the ignored schema (public.k -> ext.t) is refused too:
    ignoring ext would leave public.k referencing a schema pgmig no longer manages.
    """
    await gen_setup.assert_unsupported(
        src=[],
        dst=[
            "CREATE SCHEMA ext",
            "CREATE TABLE ext.t (id integer PRIMARY KEY)",
            "CREATE TABLE public.k (id integer REFERENCES ext.t (id))",
        ],
        match=r"connected",
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_view_across_boundary_refused(gen_setup: GenerateSetup) -> None:
    """
    A view read across the boundary is a connection just like a foreign key: a kept view reading
    an ignored table is refused.
    """
    await gen_setup.assert_unsupported(
        src=[],
        dst=[
            "CREATE SCHEMA ext",
            "CREATE TABLE ext.t (id integer)",
            "CREATE VIEW public.v AS SELECT id FROM ext.t",
        ],
        match=r"connected",
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_connection_between_kept_schemas_allowed(gen_setup: GenerateSetup) -> None:
    """
    Only a dependency that touches the ignored schema is refused. A cross-schema link between two
    kept schemas (a.t <- b.k) is fine while a third schema is ignored.
    """
    await gen_setup.assert_diff(
        both=[
            "CREATE SCHEMA a",
            "CREATE TABLE a.t (id integer PRIMARY KEY)",
            "CREATE SCHEMA b",
            "CREATE TABLE b.k (id integer REFERENCES a.t (id))",
        ],
        src=[],
        dst=["CREATE SCHEMA ext", "CREATE TABLE ext.iso (n integer)"],
        diff=[],
        ignore_schemas=["ext"],
    )


async def test_ignore_schema_unset_still_diffs(gen_setup: GenerateSetup) -> None:
    """
    Control: without --ignore-schema the same schema is created normally, confirming the tests
    above exercise the flag rather than some other exclusion.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE SCHEMA ext", "CREATE TABLE ext.t (n integer)"],
        diff=[
            'CREATE SCHEMA "ext"',
            'CREATE TABLE "ext"."t" ("n" integer)',
        ],
    )
