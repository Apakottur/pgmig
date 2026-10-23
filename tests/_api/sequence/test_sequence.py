from tests._api.generate_setup import GenerateSetup


async def test_sequence_create(gen_setup: GenerateSetup) -> None:
    """
    Sequence present in target but missing in source -> CREATE SEQUENCE, listing only the
    parameters that differ from their Postgres default (CACHE 1 is one, so it is dropped).
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE SEQUENCE counter AS integer INCREMENT BY 2 MINVALUE 0 MAXVALUE 100 START WITH 5 CACHE 1 CYCLE"],
        diff=[
            'CREATE SEQUENCE "public"."counter" AS integer START WITH 5 INCREMENT BY 2 MINVALUE 0 MAXVALUE 100 CYCLE'
        ],
    )


async def test_sequence_create_no_cycle(gen_setup: GenerateSetup) -> None:
    """
    A non-cycling sequence is created without a trailing CYCLE.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE SEQUENCE counter AS integer INCREMENT BY 1 MINVALUE 1 MAXVALUE 100 START WITH 1 CACHE 1"],
        diff=['CREATE SEQUENCE "public"."counter" AS integer MAXVALUE 100'],
    )


async def test_sequence_create_all_defaults(gen_setup: GenerateSetup) -> None:
    """
    A sequence with no explicit parameters is created bare -- every parameter Postgres reports
    is its own default, so none is spelled out.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE SEQUENCE counter"],
        diff=['CREATE SEQUENCE "public"."counter"'],
    )


async def test_sequence_create_narrower_type(gen_setup: GenerateSetup) -> None:
    """
    A non-bigint sequence keeps its AS clause and nothing else: the type is what re-derives the
    MINVALUE/MAXVALUE defaults the omitted bounds rely on.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE SEQUENCE counter AS smallint"],
        diff=['CREATE SEQUENCE "public"."counter" AS smallint'],
    )


async def test_sequence_create_descending(gen_setup: GenerateSetup) -> None:
    """
    A descending sequence defaults to type_min..-1 starting at -1, so only the increment is
    spelled out.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE SEQUENCE counter INCREMENT BY -1"],
        diff=['CREATE SEQUENCE "public"."counter" INCREMENT BY -1'],
    )


async def test_sequence_create_descending_explicit_start(gen_setup: GenerateSetup) -> None:
    """
    A descending sequence's default start is its MAXVALUE; a start that differs from the
    resolved maximum is spelled out.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE SEQUENCE counter INCREMENT BY -1 START WITH -5"],
        diff=['CREATE SEQUENCE "public"."counter" START WITH -5 INCREMENT BY -1'],
    )


async def test_sequence_create_non_default_cache(gen_setup: GenerateSetup) -> None:
    """
    A cache other than 1 is spelled out.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE SEQUENCE counter CACHE 20"],
        diff=['CREATE SEQUENCE "public"."counter" CACHE 20'],
    )


async def test_sequence_drop(gen_setup: GenerateSetup) -> None:
    """
    Sequence present in source but missing in target -> DROP SEQUENCE.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter"],
        dst=[],
        diff=['DROP SEQUENCE "public"."counter"'],
    )


async def test_sequence_alter_increment(gen_setup: GenerateSetup) -> None:
    """
    Different increment -> ALTER SEQUENCE INCREMENT BY.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter INCREMENT BY 1"],
        dst=["CREATE SEQUENCE counter INCREMENT BY 5"],
        diff=['ALTER SEQUENCE "public"."counter" INCREMENT BY 5'],
    )


async def test_sequence_alter_min_and_max(gen_setup: GenerateSetup) -> None:
    """
    Different min and max -> ALTER SEQUENCE MINVALUE MAXVALUE.
    """
    # Pin START equal on both so only MINVALUE/MAXVALUE differ (START defaults to MINVALUE).
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter MINVALUE 1 MAXVALUE 100 START WITH 10"],
        dst=["CREATE SEQUENCE counter MINVALUE 10 MAXVALUE 200 START WITH 10"],
        diff=['ALTER SEQUENCE "public"."counter" MINVALUE 10 MAXVALUE 200'],
    )


async def test_sequence_alter_start(gen_setup: GenerateSetup) -> None:
    """
    Different start -> ALTER SEQUENCE START WITH.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter START WITH 1"],
        dst=["CREATE SEQUENCE counter START WITH 50"],
        diff=['ALTER SEQUENCE "public"."counter" START WITH 50'],
    )


async def test_sequence_alter_cache(gen_setup: GenerateSetup) -> None:
    """
    Different cache -> ALTER SEQUENCE CACHE.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter CACHE 1"],
        dst=["CREATE SEQUENCE counter CACHE 10"],
        diff=['ALTER SEQUENCE "public"."counter" CACHE 10'],
    )


async def test_sequence_toggle_cycle(gen_setup: GenerateSetup) -> None:
    """
    Cycle turned on -> ALTER SEQUENCE CYCLE; turned off -> NO CYCLE.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter NO CYCLE"],
        dst=["CREATE SEQUENCE counter CYCLE"],
        diff=['ALTER SEQUENCE "public"."counter" CYCLE'],
    )


async def test_sequence_toggle_cycle_off(gen_setup: GenerateSetup) -> None:
    """
    Cycle turned off -> ALTER SEQUENCE NO CYCLE.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter CYCLE"],
        dst=["CREATE SEQUENCE counter NO CYCLE"],
        diff=['ALTER SEQUENCE "public"."counter" NO CYCLE'],
    )


async def test_sequence_alter_type(gen_setup: GenerateSetup) -> None:
    """
    Different data type -> ALTER SEQUENCE AS.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter AS integer MAXVALUE 100"],
        dst=["CREATE SEQUENCE counter AS bigint MAXVALUE 100"],
        diff=['ALTER SEQUENCE "public"."counter" AS bigint'],
    )


async def test_sequence_alter_multiple_parameters(gen_setup: GenerateSetup) -> None:
    """
    Two parameters differ -> one ALTER SEQUENCE with both clauses, in fixed order.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter INCREMENT BY 1 CACHE 1"],
        dst=["CREATE SEQUENCE counter INCREMENT BY 3 CACHE 5"],
        diff=['ALTER SEQUENCE "public"."counter" INCREMENT BY 3 CACHE 5'],
    )


async def test_sequence_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to a sequence present on both sides -> COMMENT ON SEQUENCE.
    """
    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE counter"],
        src=[],
        dst=["COMMENT ON SEQUENCE counter IS 'the counter'"],
        diff=['COMMENT ON SEQUENCE "public"."counter" IS \'the counter\''],
    )
