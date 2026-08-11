from tests._api.generate_setup import GenerateSetup


async def test_create_identity_with_options(gen_setup: GenerateSetup) -> None:
    """
    A new identity column carrying non-default sequence options renders them inline in the
    GENERATED ... AS IDENTITY (...) clause. Default options (start 1, increment 1, cache 1)
    are omitted.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (START WITH 100 INCREMENT BY 5 CACHE 10))"],
        diff=[
            'CREATE TABLE "public"."person" '
            '("id" integer GENERATED ALWAYS AS IDENTITY (START WITH 100 INCREMENT BY 5 CACHE 10))'
        ],
    )


async def test_create_identity_with_maxvalue_and_cycle(gen_setup: GenerateSetup) -> None:
    """
    A non-default MAXVALUE and CYCLE render inline; the default START/MINVALUE stay omitted.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (MAXVALUE 500 CYCLE))"],
        diff=['CREATE TABLE "public"."person" ("id" integer GENERATED ALWAYS AS IDENTITY (MAXVALUE 500 CYCLE))'],
    )


async def test_create_identity_descending(gen_setup: GenerateSetup) -> None:
    """
    A descending identity (negative increment): its defaults flip (start defaults to the
    MAXVALUE end), so a -1 start and -1 max stay omitted while the explicit MINVALUE shows.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (INCREMENT BY -1 MINVALUE -100))"],
        diff=[
            'CREATE TABLE "public"."person" ("id" integer GENERATED ALWAYS AS IDENTITY (INCREMENT BY -1 MINVALUE -100))'
        ],
    )


async def test_add_identity_column_with_options(gen_setup: GenerateSetup) -> None:
    """
    Adding an identity column to an existing table carries its options in the ADD COLUMN.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=["CREATE TABLE person (name text, id integer GENERATED ALWAYS AS IDENTITY (INCREMENT BY 5))"],
        diff=['ALTER TABLE "public"."person" ADD COLUMN "id" integer GENERATED ALWAYS AS IDENTITY (INCREMENT BY 5)'],
    )


async def test_identity_default_options_unchanged(gen_setup: GenerateSetup) -> None:
    """
    A plain identity with all-default options on both sides -> no migration SQL (the default
    options must not be spuriously emitted as a difference).
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        src=[],
        dst=[],
        diff=[],
    )


async def test_identity_same_options_unchanged(gen_setup: GenerateSetup) -> None:
    """
    An identity with identical non-default options on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (START WITH 100 INCREMENT BY 5))"],
        src=[],
        dst=[],
        diff=[],
    )


async def test_identity_start_change(gen_setup: GenerateSetup) -> None:
    """
    A changed START value -> SET START WITH on the existing identity column.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (START WITH 100))"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "id" SET START WITH 100'],
    )


async def test_identity_increment_change(gen_setup: GenerateSetup) -> None:
    """
    A changed INCREMENT -> SET INCREMENT BY.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (INCREMENT BY 5))"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "id" SET INCREMENT BY 5'],
    )


async def test_identity_cache_change(gen_setup: GenerateSetup) -> None:
    """
    A changed CACHE -> SET CACHE.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (CACHE 10))"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "id" SET CACHE 10'],
    )


async def test_identity_cycle_added(gen_setup: GenerateSetup) -> None:
    """
    Turning CYCLE on -> SET CYCLE.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (CYCLE))"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "id" SET CYCLE'],
    )


async def test_identity_cycle_removed(gen_setup: GenerateSetup) -> None:
    """
    Turning CYCLE off -> SET NO CYCLE.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (CYCLE))"],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "id" SET NO CYCLE'],
    )


async def test_identity_minvalue_change(gen_setup: GenerateSetup) -> None:
    """
    A lowered MINVALUE -> SET MINVALUE (lowering keeps the current value valid, so it
    converges without a sequence restart). START is pinned so only MINVALUE differs (an
    ascending sequence's start otherwise defaults to its MINVALUE).
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (START WITH 1 MINVALUE -100))"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "id" SET MINVALUE -100'],
    )


async def test_identity_maxvalue_change(gen_setup: GenerateSetup) -> None:
    """
    A lowered MAXVALUE -> SET MAXVALUE.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (MAXVALUE 500))"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "id" SET MAXVALUE 500'],
    )


async def test_identity_option_back_to_default(gen_setup: GenerateSetup) -> None:
    """
    An option returning to its default -> SET <option> to the default value, so the diff
    converges even though the target clause omits it.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (INCREMENT BY 5))"],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "id" SET INCREMENT BY 1'],
    )


async def test_identity_multiple_options_change_chained(gen_setup: GenerateSetup) -> None:
    """
    Several changed options chain into a single ALTER COLUMN statement, in a stable order.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY (START WITH 100 INCREMENT BY 5 CACHE 10))"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "id" SET START WITH 100 SET INCREMENT BY 5 SET CACHE 10'],
    )


async def test_identity_kind_flip_with_option_change(gen_setup: GenerateSetup) -> None:
    """
    A generation-kind flip and an option change together: SET GENERATED (existing path) then
    the option SET chain, without double-emitting.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        dst=["CREATE TABLE person (id integer GENERATED BY DEFAULT AS IDENTITY (INCREMENT BY 5))"],
        diff=[
            'ALTER TABLE "public"."person" ALTER COLUMN "id" SET GENERATED BY DEFAULT',
            'ALTER TABLE "public"."person" ALTER COLUMN "id" SET INCREMENT BY 5',
        ],
    )


async def test_serial_to_identity_with_options(gen_setup: GenerateSetup) -> None:
    """
    A serial column converted to an identity column with options carries those options inline
    in the ADD ... AS IDENTITY, and still drops the serial default first.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id serial)"],
        dst=["CREATE TABLE person (id integer GENERATED BY DEFAULT AS IDENTITY (INCREMENT BY 5))"],
        diff=[
            'ALTER TABLE "public"."person" ALTER COLUMN "id" DROP DEFAULT',
            'ALTER TABLE "public"."person" ALTER COLUMN "id" ADD GENERATED BY DEFAULT AS IDENTITY (INCREMENT BY 5)',
        ],
    )
