from tests._api.generate_setup import GenerateSetup


async def test_function_drop_used_by_column_default(gen_setup: GenerateSetup) -> None:
    """
    Dropping a function a column default depends on: the DROP DEFAULT (TABLE phase) is
    emitted before the DROP FUNCTION (late phase), so the migration is valid and converges.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE FUNCTION f() RETURNS integer LANGUAGE sql AS $$SELECT 1$$",
            "CREATE TABLE t (x integer DEFAULT f())",
        ],
        dst=["CREATE TABLE t (x integer)"],
        diff=[
            'ALTER TABLE "public"."t" ALTER COLUMN "x" DROP DEFAULT',
            'DROP FUNCTION "public"."f"()',
        ],
    )


async def test_function_drop_used_by_check_constraint(gen_setup: GenerateSetup) -> None:
    """
    Dropping a function a check constraint depends on: DROP CONSTRAINT (CONSTRAINT phase)
    precedes DROP FUNCTION (late phase).
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE FUNCTION positive(v integer) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$SELECT v > 0$$",
            "CREATE TABLE t (x integer, CONSTRAINT t_chk CHECK (positive(x)))",
        ],
        dst=["CREATE TABLE t (x integer)"],
        diff=[
            'ALTER TABLE "public"."t" DROP CONSTRAINT "t_chk"',
            'DROP FUNCTION "public"."positive"(v integer)',
        ],
    )


async def test_function_drop_used_by_expression_index(gen_setup: GenerateSetup) -> None:
    """
    Dropping a function an expression index depends on: DROP INDEX (INDEX phase) precedes
    DROP FUNCTION (late phase).
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE FUNCTION lower_x(v text) RETURNS text LANGUAGE sql IMMUTABLE AS $$SELECT lower(v)$$",
            "CREATE TABLE t (x text)",
            "CREATE INDEX t_lx ON t (lower_x(x))",
        ],
        dst=["CREATE TABLE t (x text)"],
        diff=[
            'DROP INDEX "public"."t_lx"',
            'DROP FUNCTION "public"."lower_x"(v text)',
        ],
    )


async def test_function_drop_chain_ordered(gen_setup: GenerateSetup) -> None:
    """
    A function-on-function chain (top -> mid -> leaf via SQL BEGIN ATOMIC bodies), all
    dropped: the un-depended-upon top drops early, and the depended-upon mid and leaf drop
    late, topologically ordered (mid before leaf).
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE FUNCTION leaf() RETURNS integer LANGUAGE sql BEGIN ATOMIC SELECT 1; END",
            "CREATE FUNCTION mid() RETURNS integer LANGUAGE sql BEGIN ATOMIC SELECT leaf(); END",
            "CREATE FUNCTION top() RETURNS integer LANGUAGE sql BEGIN ATOMIC SELECT mid(); END",
        ],
        dst=[],
        diff=[
            'DROP FUNCTION "public"."top"()',
            'DROP FUNCTION "public"."mid"()',
            'DROP FUNCTION "public"."leaf"()',
        ],
    )


async def test_function_drop_diamond_ordered(gen_setup: GenerateSetup) -> None:
    """
    A diamond of dependencies (top -> mid1, mid2 -> leaf), all dropped: leaf is depended on
    by two late routines, so it is dropped only after both, exercising the multi-dependent
    ordering. The two independent mids are ordered arbitrarily-but-deterministically (mid2
    before mid1, the reverse of the dependency-first sort's ties).
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE FUNCTION leaf() RETURNS integer LANGUAGE sql BEGIN ATOMIC SELECT 1; END",
            "CREATE FUNCTION mid1() RETURNS integer LANGUAGE sql BEGIN ATOMIC SELECT leaf(); END",
            "CREATE FUNCTION mid2() RETURNS integer LANGUAGE sql BEGIN ATOMIC SELECT leaf(); END",
            "CREATE FUNCTION top() RETURNS integer LANGUAGE sql BEGIN ATOMIC SELECT mid1() + mid2(); END",
        ],
        dst=[],
        diff=[
            'DROP FUNCTION "public"."top"()',
            'DROP FUNCTION "public"."mid2"()',
            'DROP FUNCTION "public"."mid1"()',
            'DROP FUNCTION "public"."leaf"()',
        ],
    )


async def test_function_drop_circular_with_dropped_table_raises(gen_setup: GenerateSetup) -> None:
    """
    A depended-upon function that itself hard-depends on a table dropped the same run is a
    circular dependency Postgres can only resolve with CASCADE; refuse loudly.
    """
    await gen_setup.assert_unsupported(
        src=[
            "CREATE TABLE readings (a integer)",
            "CREATE FUNCTION reader() RETURNS bigint LANGUAGE sql BEGIN ATOMIC SELECT count(*) FROM readings; END",
            "CREATE TABLE t2 (n bigint DEFAULT reader())",
        ],
        dst=[],
        match=r"circular dependency",
    )


async def test_function_return_type_change_recreates_column_default(gen_setup: GenerateSetup) -> None:
    """
    Return-type change on a function used by an (unchanged) column default: the default is
    dropped, the function recreated, then the default re-added around the recreate.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE FUNCTION f() RETURNS integer LANGUAGE sql AS $$SELECT 1$$",
            "CREATE TABLE t (x bigint DEFAULT f())",
        ],
        dst=[
            "CREATE FUNCTION f() RETURNS bigint LANGUAGE sql AS $$SELECT 1$$",
            "CREATE TABLE t (x bigint DEFAULT f())",
        ],
        diff=[
            'ALTER TABLE "public"."t" ALTER COLUMN "x" DROP DEFAULT',
            'DROP FUNCTION "public"."f"()',
            "CREATE OR REPLACE FUNCTION public.f()\n RETURNS bigint\n LANGUAGE sql\nAS $function$SELECT 1$function$",
            'ALTER TABLE "public"."t" ALTER COLUMN "x" SET DEFAULT public.f()',
        ],
    )


async def test_function_return_type_change_recreates_check_constraint(gen_setup: GenerateSetup) -> None:
    """
    Return-type change on a function used inside an (unchanged) check constraint: the
    constraint is dropped, the function recreated, then the constraint re-added.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE FUNCTION amount(v integer) RETURNS integer LANGUAGE sql IMMUTABLE AS $$SELECT v$$",
            "CREATE TABLE t (x integer, CONSTRAINT t_chk CHECK (amount(x) > 0))",
        ],
        dst=[
            "CREATE FUNCTION amount(v integer) RETURNS bigint LANGUAGE sql IMMUTABLE AS $$SELECT v::bigint$$",
            "CREATE TABLE t (x integer, CONSTRAINT t_chk CHECK (amount(x) > 0))",
        ],
        diff=[
            'ALTER TABLE "public"."t" DROP CONSTRAINT "t_chk"',
            'DROP FUNCTION "public"."amount"(v integer)',
            "CREATE OR REPLACE FUNCTION public.amount(v integer)\n RETURNS bigint\n"
            " LANGUAGE sql\n IMMUTABLE\nAS $function$SELECT v::bigint$function$",
            'ALTER TABLE "public"."t" ADD CONSTRAINT "t_chk" CHECK ((public.amount(x) > 0))',
        ],
    )


async def test_function_return_type_change_recreates_expression_index(gen_setup: GenerateSetup) -> None:
    """
    Return-type change on a function used by an (unchanged) expression index: the index is
    dropped, the function recreated, then the index re-created.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE FUNCTION dbl(v integer) RETURNS integer LANGUAGE sql IMMUTABLE AS $$SELECT v * 2$$",
            "CREATE TABLE t (x integer)",
            "CREATE INDEX t_dbl ON t (dbl(x))",
        ],
        dst=[
            "CREATE FUNCTION dbl(v integer) RETURNS bigint LANGUAGE sql IMMUTABLE AS $$SELECT (v * 2)::bigint$$",
            "CREATE TABLE t (x integer)",
            "CREATE INDEX t_dbl ON t (dbl(x))",
        ],
        diff=[
            'DROP INDEX "public"."t_dbl"',
            'DROP FUNCTION "public"."dbl"(v integer)',
            "CREATE OR REPLACE FUNCTION public.dbl(v integer)\n RETURNS bigint\n"
            " LANGUAGE sql\n IMMUTABLE\nAS $function$SELECT (v * 2)::bigint$function$",
            "CREATE INDEX t_dbl ON public.t USING btree (public.dbl(x))",
        ],
    )


async def test_function_return_type_change_recreates_multiple_dependents(gen_setup: GenerateSetup) -> None:
    """
    Return-type change on a function used by both a column default and a check constraint:
    all dependents are dropped (in their phases) before the recreate and re-added after it.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE FUNCTION f() RETURNS integer LANGUAGE sql IMMUTABLE AS $$SELECT 1$$",
            "CREATE TABLE t (x bigint DEFAULT f(), CONSTRAINT t_chk CHECK (f() > 0))",
        ],
        dst=[
            "CREATE FUNCTION f() RETURNS bigint LANGUAGE sql IMMUTABLE AS $$SELECT 1$$",
            "CREATE TABLE t (x bigint DEFAULT f(), CONSTRAINT t_chk CHECK (f() > 0))",
        ],
        diff=[
            'ALTER TABLE "public"."t" ALTER COLUMN "x" DROP DEFAULT',
            'ALTER TABLE "public"."t" DROP CONSTRAINT "t_chk"',
            'DROP FUNCTION "public"."f"()',
            "CREATE OR REPLACE FUNCTION public.f()\n RETURNS bigint\n LANGUAGE sql\n IMMUTABLE\n"
            "AS $function$SELECT 1$function$",
            'ALTER TABLE "public"."t" ADD CONSTRAINT "t_chk" CHECK ((public.f() > 0))',
            'ALTER TABLE "public"."t" ALTER COLUMN "x" SET DEFAULT public.f()',
        ],
    )


async def test_function_return_type_change_with_dropped_dependent_raises(gen_setup: GenerateSetup) -> None:
    """
    Return-type change where the dependent (its owning table) is also dropped this run: the
    dependent is not present in the target to re-create, so refuse rather than emit a
    non-converging recreate.
    """
    await gen_setup.assert_unsupported(
        src=[
            "CREATE FUNCTION f() RETURNS integer LANGUAGE sql AS $$SELECT 1$$",
            "CREATE TABLE t (x bigint DEFAULT f())",
        ],
        dst=["CREATE FUNCTION f() RETURNS bigint LANGUAGE sql AS $$SELECT 1$$"],
        match=r"Recreating",
    )


async def test_function_return_type_change_with_changed_dependent_raises(gen_setup: GenerateSetup) -> None:
    """
    Return-type change where a dependent also changed (the check expression differs between
    source and target): re-creating the source version would not converge, so refuse.
    """
    await gen_setup.assert_unsupported(
        src=[
            "CREATE FUNCTION amount(v integer) RETURNS integer LANGUAGE sql IMMUTABLE AS $$SELECT v$$",
            "CREATE TABLE t (x integer, CONSTRAINT t_chk CHECK (amount(x) > 0))",
        ],
        dst=[
            "CREATE FUNCTION amount(v integer) RETURNS bigint LANGUAGE sql IMMUTABLE AS $$SELECT v::bigint$$",
            "CREATE TABLE t (x integer, CONSTRAINT t_chk CHECK (amount(x) > 1))",
        ],
        match=r"Recreating",
    )


async def test_function_return_type_change_with_routine_dependent_raises(gen_setup: GenerateSetup) -> None:
    """
    Return-type change on a function another routine depends on is still refused: the
    recreate-around-dependents path is bounded to one level (defaults / constraints /
    indexes) and does not follow routine-on-routine chains.
    """
    await gen_setup.assert_unsupported(
        src=[
            "CREATE FUNCTION leaf() RETURNS integer LANGUAGE sql AS $$SELECT 1$$",
            "CREATE FUNCTION caller() RETURNS bigint LANGUAGE sql BEGIN ATOMIC SELECT leaf(); END",
        ],
        dst=[
            "CREATE FUNCTION leaf() RETURNS bigint LANGUAGE sql AS $$SELECT 1$$",
            "CREATE FUNCTION caller() RETURNS bigint LANGUAGE sql BEGIN ATOMIC SELECT leaf(); END",
        ],
        match=r"Recreating",
    )
