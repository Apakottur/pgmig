import pytest

from tests.api.generate_setup import GenerateSetup


def test_function_create(gen_setup: GenerateSetup) -> None:
    """
    Function present in target but missing in source -> CREATE (from pg_get_functiondef).
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE FUNCTION add(a integer, b integer) RETURNS integer LANGUAGE sql AS $$SELECT a + b$$"],
        diff=[
            "CREATE OR REPLACE FUNCTION public.add(a integer, b integer)\n"
            " RETURNS integer\n"
            " LANGUAGE sql\n"
            "AS $function$SELECT a + b$function$"
        ],
    )


def test_function_drop(gen_setup: GenerateSetup) -> None:
    """
    Function present in source but missing in target -> DROP ROUTINE with signature.
    """
    gen_setup.assert_diff(
        src=["CREATE FUNCTION add(a integer, b integer) RETURNS integer LANGUAGE sql AS $$SELECT a + b$$"],
        dst=[],
        diff=['DROP FUNCTION "public"."add"(a integer, b integer)'],
    )


def test_function_body_change(gen_setup: GenerateSetup) -> None:
    """
    Same signature and return type, different body -> single CREATE OR REPLACE.
    """
    gen_setup.assert_diff(
        src=["CREATE FUNCTION calc(a integer) RETURNS integer LANGUAGE sql AS $$SELECT a + 1$$"],
        dst=["CREATE FUNCTION calc(a integer) RETURNS integer LANGUAGE sql AS $$SELECT a + 2$$"],
        diff=[
            "CREATE OR REPLACE FUNCTION public.calc(a integer)\n"
            " RETURNS integer\n"
            " LANGUAGE sql\n"
            "AS $function$SELECT a + 2$function$"
        ],
    )


def test_function_return_type_change(gen_setup: GenerateSetup) -> None:
    """
    Same signature, different return type -> DROP ROUTINE then CREATE (OR REPLACE cannot change it).
    """
    gen_setup.assert_diff(
        src=["CREATE FUNCTION calc(a integer) RETURNS integer LANGUAGE sql AS $$SELECT a$$"],
        dst=["CREATE FUNCTION calc(a integer) RETURNS bigint LANGUAGE sql AS $$SELECT a::bigint$$"],
        diff=[
            'DROP FUNCTION "public"."calc"(a integer)',
            "CREATE OR REPLACE FUNCTION public.calc(a integer)\n"
            " RETURNS bigint\n"
            " LANGUAGE sql\n"
            "AS $function$SELECT a::bigint$function$",
        ],
    )


def test_function_overload_added(gen_setup: GenerateSetup) -> None:
    """
    Adding an overload (same name, different args) leaves the existing one untouched.
    """
    gen_setup.assert_diff(
        src=["CREATE FUNCTION f(a integer) RETURNS integer LANGUAGE sql AS $$SELECT a$$"],
        dst=[
            "CREATE FUNCTION f(a integer) RETURNS integer LANGUAGE sql AS $$SELECT a$$",
            "CREATE FUNCTION f(a text) RETURNS text LANGUAGE sql AS $$SELECT a$$",
        ],
        diff=[
            "CREATE OR REPLACE FUNCTION public.f(a text)\n RETURNS text\n LANGUAGE sql\nAS $function$SELECT a$function$"
        ],
    )


def test_procedure_create(gen_setup: GenerateSetup) -> None:
    """
    A procedure is created from its definition.
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE PROCEDURE noop() LANGUAGE sql AS $$SELECT 1$$"],
        diff=["CREATE OR REPLACE PROCEDURE public.noop()\n LANGUAGE sql\nAS $procedure$SELECT 1$procedure$"],
    )


def test_procedure_drop(gen_setup: GenerateSetup) -> None:
    """
    A procedure present only in source is dropped via DROP PROCEDURE.
    """
    gen_setup.assert_diff(
        src=["CREATE PROCEDURE noop() LANGUAGE sql AS $$SELECT 1$$"],
        dst=[],
        diff=['DROP PROCEDURE "public"."noop"()'],
    )


def test_function_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical function on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        src=["CREATE FUNCTION add(a integer, b integer) RETURNS integer LANGUAGE sql AS $$SELECT a + b$$"],
        dst=["CREATE FUNCTION add(a integer, b integer) RETURNS integer LANGUAGE sql AS $$SELECT a + b$$"],
        diff=[],
    )


def test_function_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to a function present on both sides -> COMMENT ON FUNCTION.
    """
    gen_setup.assert_diff(
        both=["CREATE FUNCTION add(a integer, b integer) RETURNS integer LANGUAGE sql AS $$SELECT a + b$$"],
        src=[],
        dst=["COMMENT ON FUNCTION add(integer, integer) IS 'adds'"],
        diff=['COMMENT ON FUNCTION "public"."add"(a integer, b integer) IS \'adds\''],
    )


def test_function_drop_with_dependent_unsupported(gen_setup: GenerateSetup) -> None:
    """
    Dropping a function that a column default depends on is refused (dependency-aware
    drop ordering is not implemented): raise NotImplementedError rather than emit an
    invalid migration that DROP FUNCTION-before-DROP DEFAULT.
    """
    gen_setup.src.execute("CREATE FUNCTION f() RETURNS integer LANGUAGE sql AS $$SELECT 1$$")
    gen_setup.src.execute("CREATE TABLE t (x integer DEFAULT f())")
    gen_setup.dst.execute("CREATE TABLE t (x integer)")

    with pytest.raises(NotImplementedError):
        gen_setup.assert_migration_sql("")
