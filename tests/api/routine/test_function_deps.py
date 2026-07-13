from tests.api.generate_setup import GenerateSetup


def test_function_drop_used_by_column_default(gen_setup: GenerateSetup) -> None:
    """
    Dropping a function a column default depends on: the DROP DEFAULT (TABLE phase) is
    emitted before the DROP FUNCTION (late phase), so the migration is valid and converges.
    """
    gen_setup.assert_diff(
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


def test_function_drop_used_by_check_constraint(gen_setup: GenerateSetup) -> None:
    """
    Dropping a function a check constraint depends on: DROP CONSTRAINT (CONSTRAINT phase)
    precedes DROP FUNCTION (late phase).
    """
    gen_setup.assert_diff(
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


def test_function_drop_used_by_expression_index(gen_setup: GenerateSetup) -> None:
    """
    Dropping a function an expression index depends on: DROP INDEX (INDEX phase) precedes
    DROP FUNCTION (late phase).
    """
    gen_setup.assert_diff(
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


def test_function_drop_chain_ordered(gen_setup: GenerateSetup) -> None:
    """
    A function-on-function chain (top -> mid -> leaf via SQL BEGIN ATOMIC bodies), all
    dropped: the un-depended-upon top drops early, and the depended-upon mid and leaf drop
    late, topologically ordered (mid before leaf).
    """
    gen_setup.assert_diff(
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


def test_function_drop_diamond_ordered(gen_setup: GenerateSetup) -> None:
    """
    A diamond of dependencies (top -> mid1, mid2 -> leaf), all dropped: leaf is depended on
    by two late routines, so it is dropped only after both, exercising the multi-dependent
    ordering.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE FUNCTION leaf() RETURNS integer LANGUAGE sql BEGIN ATOMIC SELECT 1; END",
            "CREATE FUNCTION mid1() RETURNS integer LANGUAGE sql BEGIN ATOMIC SELECT leaf(); END",
            "CREATE FUNCTION mid2() RETURNS integer LANGUAGE sql BEGIN ATOMIC SELECT leaf(); END",
            "CREATE FUNCTION top() RETURNS integer LANGUAGE sql BEGIN ATOMIC SELECT mid1() + mid2(); END",
        ],
        dst=[],
        diff=[
            'DROP FUNCTION "public"."top"()',
            'DROP FUNCTION "public"."mid1"()',
            'DROP FUNCTION "public"."mid2"()',
            'DROP FUNCTION "public"."leaf"()',
        ],
    )


def test_function_drop_circular_with_dropped_table_raises(gen_setup: GenerateSetup) -> None:
    """
    A depended-upon function that itself hard-depends on a table dropped the same run is a
    circular dependency Postgres can only resolve with CASCADE; refuse loudly.
    """
    gen_setup.assert_unsupported(
        src=[
            "CREATE TABLE readings (a integer)",
            "CREATE FUNCTION reader() RETURNS bigint LANGUAGE sql BEGIN ATOMIC SELECT count(*) FROM readings; END",
            "CREATE TABLE t2 (n bigint DEFAULT reader())",
        ],
        dst=[],
        match=r"circular dependency",
    )


def test_function_return_type_change_with_dependent_raises(gen_setup: GenerateSetup) -> None:
    """
    Recreating a depended-upon function (return-type change forces DROP + CREATE) is still
    refused: its dependents remain in the target, so it cannot be dropped to recreate.
    """
    gen_setup.assert_unsupported(
        src=[
            "CREATE FUNCTION f() RETURNS integer LANGUAGE sql AS $$SELECT 1$$",
            "CREATE TABLE t (x bigint DEFAULT f())",
        ],
        dst=[
            "CREATE FUNCTION f() RETURNS bigint LANGUAGE sql AS $$SELECT 1$$",
            "CREATE TABLE t (x bigint DEFAULT f())",
        ],
        match=r"Recreating",
    )
