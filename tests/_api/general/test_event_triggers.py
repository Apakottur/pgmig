from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import get_unique_postgres_name

# An event trigger function, shared by both sides unless a test changes it.
_FN = "CREATE FUNCTION et_fn() RETURNS event_trigger LANGUAGE plpgsql AS $$BEGIN END;$$"


async def test_event_trigger_added(gen_setup: GenerateSetup) -> None:
    """
    An event trigger present only on the target -> CREATE EVENT TRIGGER.
    """
    await gen_setup.assert_diff(
        both=[_FN],
        src=[],
        dst=["CREATE EVENT TRIGGER et ON ddl_command_end EXECUTE FUNCTION et_fn()"],
        diff=['CREATE EVENT TRIGGER "et" ON ddl_command_end EXECUTE FUNCTION "public"."et_fn"()'],
    )


async def test_event_trigger_added_with_its_function(gen_setup: GenerateSetup) -> None:
    """
    An event trigger and its function both new: the function is created before the trigger.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[_FN, "CREATE EVENT TRIGGER et ON ddl_command_end EXECUTE FUNCTION et_fn()"],
        diff=[
            "CREATE OR REPLACE FUNCTION public.et_fn()\n RETURNS event_trigger\n LANGUAGE plpgsql\n"
            "AS $function$BEGIN END;$function$",
            'CREATE EVENT TRIGGER "et" ON ddl_command_end EXECUTE FUNCTION "public"."et_fn"()',
        ],
    )


async def test_event_trigger_dropped_with_its_function(gen_setup: GenerateSetup) -> None:
    """
    An event trigger and its function both removed: the trigger is dropped before the function.
    """
    await gen_setup.assert_diff(
        src=[_FN, "CREATE EVENT TRIGGER et ON ddl_command_end EXECUTE FUNCTION et_fn()"],
        dst=[],
        diff=['DROP EVENT TRIGGER "et"', 'DROP FUNCTION "public"."et_fn"()'],
    )


async def test_event_trigger_tags(gen_setup: GenerateSetup) -> None:
    """
    The WHEN TAG IN filter is rendered with its tags sorted.
    """
    await gen_setup.assert_diff(
        both=[_FN],
        src=[],
        dst=[
            "CREATE EVENT TRIGGER et ON ddl_command_start WHEN TAG IN ('DROP TABLE', 'CREATE TABLE') "
            "EXECUTE FUNCTION et_fn()"
        ],
        diff=[
            "CREATE EVENT TRIGGER \"et\" ON ddl_command_start WHEN TAG IN ('CREATE TABLE', 'DROP TABLE') "
            'EXECUTE FUNCTION "public"."et_fn"()'
        ],
    )


async def test_event_trigger_tag_order_is_not_a_change(gen_setup: GenerateSetup) -> None:
    """
    The same tags listed in a different order are the same filter: no diff.
    """
    await gen_setup.assert_diff(
        both=[_FN],
        src=[
            "CREATE EVENT TRIGGER et ON ddl_command_start WHEN TAG IN ('DROP TABLE', 'CREATE TABLE') "
            "EXECUTE FUNCTION et_fn()"
        ],
        dst=[
            "CREATE EVENT TRIGGER et ON ddl_command_start WHEN TAG IN ('CREATE TABLE', 'DROP TABLE') "
            "EXECUTE FUNCTION et_fn()"
        ],
        diff=[],
    )


async def test_event_trigger_tags_changed(gen_setup: GenerateSetup) -> None:
    """
    A changed tag filter has no ALTER form: the trigger is dropped and recreated. The event and
    the function are part of the same rename key, so a change to either takes this path too.
    """
    await gen_setup.assert_diff(
        both=[_FN],
        src=["CREATE EVENT TRIGGER et ON ddl_command_start WHEN TAG IN ('CREATE TABLE') EXECUTE FUNCTION et_fn()"],
        dst=["CREATE EVENT TRIGGER et ON ddl_command_start EXECUTE FUNCTION et_fn()"],
        diff=[
            'DROP EVENT TRIGGER "et"',
            'CREATE EVENT TRIGGER "et" ON ddl_command_start EXECUTE FUNCTION "public"."et_fn"()',
        ],
    )


async def test_event_trigger_renamed(gen_setup: GenerateSetup) -> None:
    """
    The same trigger under a new name -> ALTER EVENT TRIGGER ... RENAME TO.
    """
    await gen_setup.assert_diff(
        both=[_FN],
        src=["CREATE EVENT TRIGGER et_old ON ddl_command_end EXECUTE FUNCTION et_fn()"],
        dst=["CREATE EVENT TRIGGER et_new ON ddl_command_end EXECUTE FUNCTION et_fn()"],
        diff=['ALTER EVENT TRIGGER "et_old" RENAME TO "et_new"'],
    )


async def test_event_trigger_disabled(gen_setup: GenerateSetup) -> None:
    """
    An enable-state change -> ALTER EVENT TRIGGER ... DISABLE.
    """
    await gen_setup.assert_diff(
        both=[_FN, "CREATE EVENT TRIGGER et ON ddl_command_end EXECUTE FUNCTION et_fn()"],
        src=[],
        dst=["ALTER EVENT TRIGGER et DISABLE"],
        diff=['ALTER EVENT TRIGGER "et" DISABLE'],
    )


async def test_event_trigger_created_in_non_default_state(gen_setup: GenerateSetup) -> None:
    """
    A new trigger lands enabled (origin); a non-default target state is set after the create.
    """
    await gen_setup.assert_diff(
        both=[_FN],
        src=[],
        dst=[
            "CREATE EVENT TRIGGER et ON ddl_command_end EXECUTE FUNCTION et_fn()",
            "ALTER EVENT TRIGGER et ENABLE ALWAYS",
        ],
        diff=[
            'CREATE EVENT TRIGGER "et" ON ddl_command_end EXECUTE FUNCTION "public"."et_fn"()',
            'ALTER EVENT TRIGGER "et" ENABLE ALWAYS',
        ],
    )


async def test_event_trigger_comment(gen_setup: GenerateSetup) -> None:
    """
    A comment change -> COMMENT ON EVENT TRIGGER.
    """
    await gen_setup.assert_diff(
        both=[_FN, "CREATE EVENT TRIGGER et ON ddl_command_end EXECUTE FUNCTION et_fn()"],
        src=[],
        dst=["COMMENT ON EVENT TRIGGER et IS 'audits DDL'"],
        diff=["COMMENT ON EVENT TRIGGER \"et\" IS 'audits DDL'"],
    )


async def test_event_trigger_recreated_keeps_comment(gen_setup: GenerateSetup) -> None:
    """
    A drop-and-recreate loses the comment, so the target comment is re-emitted after the create.
    """
    await gen_setup.assert_diff(
        both=[_FN],
        src=[
            "CREATE EVENT TRIGGER et ON ddl_command_start EXECUTE FUNCTION et_fn()",
            "COMMENT ON EVENT TRIGGER et IS 'audits DDL'",
        ],
        dst=[
            "CREATE EVENT TRIGGER et ON ddl_command_end EXECUTE FUNCTION et_fn()",
            "COMMENT ON EVENT TRIGGER et IS 'audits DDL'",
        ],
        diff=[
            'DROP EVENT TRIGGER "et"',
            'CREATE EVENT TRIGGER "et" ON ddl_command_end EXECUTE FUNCTION "public"."et_fn"()',
            "COMMENT ON EVENT TRIGGER \"et\" IS 'audits DDL'",
        ],
    )


async def test_event_trigger_owner(gen_setup: GenerateSetup) -> None:
    """
    With include_owner, a differing owner -> ALTER EVENT TRIGGER ... OWNER TO. Postgres requires
    an event trigger's owner to be a superuser, so the role is created as one.
    """
    owner = get_unique_postgres_name("pgmig_et_owner", gen_setup.unique_key)
    await gen_setup.src.execute(f"DROP ROLE IF EXISTS {owner}")
    await gen_setup.src.execute(f"CREATE ROLE {owner} SUPERUSER")
    await gen_setup.assert_diff(
        both=[_FN, "CREATE EVENT TRIGGER et ON ddl_command_end EXECUTE FUNCTION et_fn()"],
        src=[],
        dst=[f"ALTER EVENT TRIGGER et OWNER TO {owner}"],
        diff=[f'ALTER EVENT TRIGGER "et" OWNER TO "{owner}"'],
        include_owner=True,
    )


async def test_event_trigger_function_return_type_change(gen_setup: GenerateSetup) -> None:
    """
    A function that stops being an event-trigger function (return-type change) while its event
    trigger is removed: the trigger is dropped first, then the function is recreated. The event
    trigger is not counted as a dependent the recreate path must re-add.
    """
    await gen_setup.assert_diff(
        src=[_FN, "CREATE EVENT TRIGGER et ON ddl_command_end EXECUTE FUNCTION et_fn()"],
        dst=["CREATE FUNCTION et_fn() RETURNS integer LANGUAGE sql AS $$SELECT 1$$"],
        diff=[
            'DROP EVENT TRIGGER "et"',
            'DROP FUNCTION "public"."et_fn"()',
            "CREATE OR REPLACE FUNCTION public.et_fn()\n RETURNS integer\n LANGUAGE sql\nAS $function$SELECT 1$function$",
        ],
    )


async def test_event_trigger_function_in_ignored_schema(gen_setup: GenerateSetup) -> None:
    """
    An event trigger whose function lives in an --ignore-schema schema is ignored with it: the
    trigger cannot exist without its function. Reproduces the Supabase platform event triggers
    (owned by supabase_admin, functions in the ignored `extensions` schema), which used to make
    pgmig refuse the whole database.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE SCHEMA ext",
            "CREATE FUNCTION ext.noop() RETURNS event_trigger LANGUAGE plpgsql AS $$BEGIN END;$$",
            "CREATE EVENT TRIGGER t ON ddl_command_end EXECUTE FUNCTION ext.noop()",
        ],
        diff=[],
        ignore_schemas=["ext"],
    )


async def test_event_trigger_function_in_ignored_schema_on_both_sides(gen_setup: GenerateSetup) -> None:
    """
    Event triggers on an ignored schema's functions are skipped on both sides, even when they
    differ, while a trigger on a kept function is still diffed.
    """
    await gen_setup.assert_diff(
        both=[
            _FN,
            "CREATE SCHEMA ext",
            "CREATE FUNCTION ext.noop() RETURNS event_trigger LANGUAGE plpgsql AS $$BEGIN END;$$",
        ],
        src=["CREATE EVENT TRIGGER ignored_old ON ddl_command_start EXECUTE FUNCTION ext.noop()"],
        dst=[
            "CREATE EVENT TRIGGER ignored_new ON sql_drop EXECUTE FUNCTION ext.noop()",
            "CREATE EVENT TRIGGER kept ON ddl_command_end EXECUTE FUNCTION et_fn()",
        ],
        diff=['CREATE EVENT TRIGGER "kept" ON ddl_command_end EXECUTE FUNCTION "public"."et_fn"()'],
        ignore_schemas=["ext"],
    )
