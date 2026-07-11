from tests.fixtures.generate_setup import GenerateSetup


def test_sequence_create(gen_setup: GenerateSetup) -> None:
    """
    Sequence present in target but missing in source -> CREATE SEQUENCE.
    """
    gen_setup.dst.execute(
        "CREATE SEQUENCE counter AS integer INCREMENT BY 2 MINVALUE 0 MAXVALUE 100 START WITH 5 CACHE 1 CYCLE"
    )

    gen_setup.assert_migration_sql(
        'CREATE SEQUENCE "public"."counter" AS integer INCREMENT BY 2 MINVALUE 0 MAXVALUE 100 START WITH 5 CACHE 1 CYCLE;'
    )


def test_sequence_create_no_cycle(gen_setup: GenerateSetup) -> None:
    """
    A non-cycling sequence is created without a trailing CYCLE.
    """
    gen_setup.dst.execute(
        "CREATE SEQUENCE counter AS integer INCREMENT BY 1 MINVALUE 1 MAXVALUE 100 START WITH 1 CACHE 1"
    )

    gen_setup.assert_migration_sql(
        'CREATE SEQUENCE "public"."counter" AS integer INCREMENT BY 1 MINVALUE 1 MAXVALUE 100 START WITH 1 CACHE 1;'
    )


def test_sequence_drop(gen_setup: GenerateSetup) -> None:
    """
    Sequence present in source but missing in target -> DROP SEQUENCE.
    """
    gen_setup.src.execute("CREATE SEQUENCE counter")

    gen_setup.assert_migration_sql('DROP SEQUENCE "public"."counter";')


def test_sequence_alter_increment(gen_setup: GenerateSetup) -> None:
    """
    Different increment -> ALTER SEQUENCE INCREMENT BY.
    """
    gen_setup.src.execute("CREATE SEQUENCE counter INCREMENT BY 1")
    gen_setup.dst.execute("CREATE SEQUENCE counter INCREMENT BY 5")

    gen_setup.assert_migration_sql('ALTER SEQUENCE "public"."counter" INCREMENT BY 5;')


def test_sequence_alter_min_and_max(gen_setup: GenerateSetup) -> None:
    """
    Different min and max -> ALTER SEQUENCE MINVALUE MAXVALUE.
    """
    # Pin START equal on both so only MINVALUE/MAXVALUE differ (START defaults to MINVALUE).
    gen_setup.src.execute("CREATE SEQUENCE counter MINVALUE 1 MAXVALUE 100 START WITH 10")
    gen_setup.dst.execute("CREATE SEQUENCE counter MINVALUE 10 MAXVALUE 200 START WITH 10")

    gen_setup.assert_migration_sql('ALTER SEQUENCE "public"."counter" MINVALUE 10 MAXVALUE 200;')


def test_sequence_alter_start(gen_setup: GenerateSetup) -> None:
    """
    Different start -> ALTER SEQUENCE START WITH.
    """
    gen_setup.src.execute("CREATE SEQUENCE counter START WITH 1")
    gen_setup.dst.execute("CREATE SEQUENCE counter START WITH 50")

    gen_setup.assert_migration_sql('ALTER SEQUENCE "public"."counter" START WITH 50;')


def test_sequence_alter_cache(gen_setup: GenerateSetup) -> None:
    """
    Different cache -> ALTER SEQUENCE CACHE.
    """
    gen_setup.src.execute("CREATE SEQUENCE counter CACHE 1")
    gen_setup.dst.execute("CREATE SEQUENCE counter CACHE 10")

    gen_setup.assert_migration_sql('ALTER SEQUENCE "public"."counter" CACHE 10;')


def test_sequence_toggle_cycle(gen_setup: GenerateSetup) -> None:
    """
    Cycle turned on -> ALTER SEQUENCE CYCLE; turned off -> NO CYCLE.
    """
    gen_setup.src.execute("CREATE SEQUENCE counter NO CYCLE")
    gen_setup.dst.execute("CREATE SEQUENCE counter CYCLE")

    gen_setup.assert_migration_sql('ALTER SEQUENCE "public"."counter" CYCLE;')


def test_sequence_toggle_cycle_off(gen_setup: GenerateSetup) -> None:
    """
    Cycle turned off -> ALTER SEQUENCE NO CYCLE.
    """
    gen_setup.src.execute("CREATE SEQUENCE counter CYCLE")
    gen_setup.dst.execute("CREATE SEQUENCE counter NO CYCLE")

    gen_setup.assert_migration_sql('ALTER SEQUENCE "public"."counter" NO CYCLE;')


def test_sequence_alter_type(gen_setup: GenerateSetup) -> None:
    """
    Different data type -> ALTER SEQUENCE AS.
    """
    gen_setup.src.execute("CREATE SEQUENCE counter AS integer MAXVALUE 100")
    gen_setup.dst.execute("CREATE SEQUENCE counter AS bigint MAXVALUE 100")

    gen_setup.assert_migration_sql('ALTER SEQUENCE "public"."counter" AS bigint;')


def test_sequence_alter_multiple_parameters(gen_setup: GenerateSetup) -> None:
    """
    Two parameters differ -> one ALTER SEQUENCE with both clauses, in fixed order.
    """
    gen_setup.src.execute("CREATE SEQUENCE counter INCREMENT BY 1 CACHE 1")
    gen_setup.dst.execute("CREATE SEQUENCE counter INCREMENT BY 3 CACHE 5")

    gen_setup.assert_migration_sql('ALTER SEQUENCE "public"."counter" INCREMENT BY 3 CACHE 5;')


def test_sequence_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical sequence on both sides -> no migration SQL.
    """
    gen_setup.execute_both("CREATE SEQUENCE counter INCREMENT BY 2 START WITH 5")

    gen_setup.assert_migration_sql("")
