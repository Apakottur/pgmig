from tests.fixtures.generate_setup import GenerateSetup


def test_function_create(gen_setup: GenerateSetup) -> None:
    """
    Function present in target but missing in source -> CREATE (from pg_get_functiondef).
    """
    gen_setup.dst.execute("CREATE FUNCTION add(a integer, b integer) RETURNS integer LANGUAGE sql AS $$SELECT a + b$$")

    gen_setup.assert_migration_sql(
        [
            "CREATE OR REPLACE FUNCTION public.add(a integer, b integer)\n"
            " RETURNS integer\n"
            " LANGUAGE sql\n"
            "AS $function$SELECT a + b$function$;"
        ]
    )


def test_function_drop(gen_setup: GenerateSetup) -> None:
    """
    Function present in source but missing in target -> DROP ROUTINE with signature.
    """
    gen_setup.src.execute("CREATE FUNCTION add(a integer, b integer) RETURNS integer LANGUAGE sql AS $$SELECT a + b$$")

    gen_setup.assert_migration_sql('DROP FUNCTION "public"."add"(a integer, b integer);')


def test_function_body_change(gen_setup: GenerateSetup) -> None:
    """
    Same signature and return type, different body -> single CREATE OR REPLACE.
    """
    gen_setup.src.execute("CREATE FUNCTION calc(a integer) RETURNS integer LANGUAGE sql AS $$SELECT a + 1$$")
    gen_setup.dst.execute("CREATE FUNCTION calc(a integer) RETURNS integer LANGUAGE sql AS $$SELECT a + 2$$")

    gen_setup.assert_migration_sql(
        [
            "CREATE OR REPLACE FUNCTION public.calc(a integer)\n"
            " RETURNS integer\n"
            " LANGUAGE sql\n"
            "AS $function$SELECT a + 2$function$;"
        ]
    )


def test_function_return_type_change(gen_setup: GenerateSetup) -> None:
    """
    Same signature, different return type -> DROP ROUTINE then CREATE (OR REPLACE cannot change it).
    """
    gen_setup.src.execute("CREATE FUNCTION calc(a integer) RETURNS integer LANGUAGE sql AS $$SELECT a$$")
    gen_setup.dst.execute("CREATE FUNCTION calc(a integer) RETURNS bigint LANGUAGE sql AS $$SELECT a::bigint$$")

    gen_setup.assert_migration_sql(
        [
            'DROP FUNCTION "public"."calc"(a integer);',
            "CREATE OR REPLACE FUNCTION public.calc(a integer)\n"
            " RETURNS bigint\n"
            " LANGUAGE sql\n"
            "AS $function$SELECT a::bigint$function$;",
        ]
    )


def test_function_overload_added(gen_setup: GenerateSetup) -> None:
    """
    Adding an overload (same name, different args) leaves the existing one untouched.
    """
    gen_setup.src.execute("CREATE FUNCTION f(a integer) RETURNS integer LANGUAGE sql AS $$SELECT a$$")
    gen_setup.dst.execute("CREATE FUNCTION f(a integer) RETURNS integer LANGUAGE sql AS $$SELECT a$$")
    gen_setup.dst.execute("CREATE FUNCTION f(a text) RETURNS text LANGUAGE sql AS $$SELECT a$$")

    gen_setup.assert_migration_sql(
        ["CREATE OR REPLACE FUNCTION public.f(a text)\n RETURNS text\n LANGUAGE sql\nAS $function$SELECT a$function$;"]
    )


def test_procedure_create(gen_setup: GenerateSetup) -> None:
    """
    A procedure is created from its definition.
    """
    gen_setup.dst.execute("CREATE PROCEDURE noop() LANGUAGE sql AS $$SELECT 1$$")

    gen_setup.assert_migration_sql(
        [
            "CREATE OR REPLACE PROCEDURE public.noop()\n LANGUAGE sql\nAS $procedure$SELECT 1$procedure$;",
        ]
    )


def test_procedure_drop(gen_setup: GenerateSetup) -> None:
    """
    A procedure present only in source is dropped via DROP PROCEDURE.
    """
    gen_setup.src.execute("CREATE PROCEDURE noop() LANGUAGE sql AS $$SELECT 1$$")

    gen_setup.assert_migration_sql('DROP PROCEDURE "public"."noop"();')


def test_function_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical function on both sides -> no migration SQL.
    """
    gen_setup.src.execute("CREATE FUNCTION add(a integer, b integer) RETURNS integer LANGUAGE sql AS $$SELECT a + b$$")
    gen_setup.dst.execute("CREATE FUNCTION add(a integer, b integer) RETURNS integer LANGUAGE sql AS $$SELECT a + b$$")

    gen_setup.assert_migration_sql("")
