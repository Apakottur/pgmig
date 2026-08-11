import pytest

from tests._api.generate_setup import GenerateSetup

# Temporal constraints (WITHOUT OVERLAPS keys and PERIOD foreign keys) are Postgres 18+.
# The non-range key columns need a GiST operator class, supplied by btree_gist.
_BTREE_GIST = "CREATE EXTENSION IF NOT EXISTS btree_gist"

_SKIP_REASON = "temporal constraints require Postgres 18+"


async def test_temporal_primary_key_add(gen_setup: GenerateSetup) -> None:
    """
    A WITHOUT OVERLAPS primary key present in target but missing in source -> ADD CONSTRAINT,
    with the WITHOUT OVERLAPS clause preserved.
    """
    if gen_setup.pg_major < 18:
        pytest.skip(_SKIP_REASON)
    await gen_setup.assert_diff(
        both=[
            _BTREE_GIST,
            "CREATE TABLE room (id integer NOT NULL, valid_at daterange NOT NULL)",
        ],
        src=[],
        dst=["ALTER TABLE room ADD CONSTRAINT room_pkey PRIMARY KEY (id, valid_at WITHOUT OVERLAPS)"],
        diff=['ALTER TABLE "public"."room" ADD CONSTRAINT "room_pkey" PRIMARY KEY (id, valid_at WITHOUT OVERLAPS)'],
    )


async def test_temporal_primary_key_drop(gen_setup: GenerateSetup) -> None:
    """
    A WITHOUT OVERLAPS primary key present in source but missing in target -> DROP CONSTRAINT.
    """
    if gen_setup.pg_major < 18:
        pytest.skip(_SKIP_REASON)
    await gen_setup.assert_diff(
        both=[
            _BTREE_GIST,
            "CREATE TABLE room (id integer NOT NULL, valid_at daterange NOT NULL)",
        ],
        src=["ALTER TABLE room ADD CONSTRAINT room_pkey PRIMARY KEY (id, valid_at WITHOUT OVERLAPS)"],
        dst=[],
        diff=['ALTER TABLE "public"."room" DROP CONSTRAINT "room_pkey"'],
    )


async def test_temporal_primary_key_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical WITHOUT OVERLAPS primary key on both sides -> no migration SQL.
    """
    if gen_setup.pg_major < 18:
        pytest.skip(_SKIP_REASON)
    await gen_setup.assert_diff(
        both=[
            _BTREE_GIST,
            "CREATE TABLE room (id integer NOT NULL, valid_at daterange NOT NULL)",
            "ALTER TABLE room ADD CONSTRAINT room_pkey PRIMARY KEY (id, valid_at WITHOUT OVERLAPS)",
        ],
        src=[],
        dst=[],
        diff=[],
    )


async def test_temporal_unique_add(gen_setup: GenerateSetup) -> None:
    """
    A WITHOUT OVERLAPS unique constraint present in target but missing in source -> ADD CONSTRAINT.
    """
    if gen_setup.pg_major < 18:
        pytest.skip(_SKIP_REASON)
    await gen_setup.assert_diff(
        both=[
            _BTREE_GIST,
            "CREATE TABLE room (id integer NOT NULL, valid_at daterange NOT NULL)",
        ],
        src=[],
        dst=["ALTER TABLE room ADD CONSTRAINT room_uq UNIQUE (id, valid_at WITHOUT OVERLAPS)"],
        diff=['ALTER TABLE "public"."room" ADD CONSTRAINT "room_uq" UNIQUE (id, valid_at WITHOUT OVERLAPS)'],
    )


async def test_temporal_unique_drop(gen_setup: GenerateSetup) -> None:
    """
    A WITHOUT OVERLAPS unique constraint present in source but missing in target -> DROP CONSTRAINT.
    """
    if gen_setup.pg_major < 18:
        pytest.skip(_SKIP_REASON)
    await gen_setup.assert_diff(
        both=[
            _BTREE_GIST,
            "CREATE TABLE room (id integer NOT NULL, valid_at daterange NOT NULL)",
        ],
        src=["ALTER TABLE room ADD CONSTRAINT room_uq UNIQUE (id, valid_at WITHOUT OVERLAPS)"],
        dst=[],
        diff=['ALTER TABLE "public"."room" DROP CONSTRAINT "room_uq"'],
    )


async def test_temporal_unique_rename(gen_setup: GenerateSetup) -> None:
    """
    Same WITHOUT OVERLAPS definition on both sides, only the name differs -> RENAME CONSTRAINT.
    """
    if gen_setup.pg_major < 18:
        pytest.skip(_SKIP_REASON)
    await gen_setup.assert_diff(
        both=[
            _BTREE_GIST,
            "CREATE TABLE room (id integer NOT NULL, valid_at daterange NOT NULL)",
        ],
        src=["ALTER TABLE room ADD CONSTRAINT room_uq_old UNIQUE (id, valid_at WITHOUT OVERLAPS)"],
        dst=["ALTER TABLE room ADD CONSTRAINT room_uq_new UNIQUE (id, valid_at WITHOUT OVERLAPS)"],
        diff=['ALTER TABLE "public"."room" RENAME CONSTRAINT "room_uq_old" TO "room_uq_new"'],
    )


async def test_temporal_unique_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different WITHOUT OVERLAPS key columns -> DROP CONSTRAINT then ADD CONSTRAINT.
    """
    if gen_setup.pg_major < 18:
        pytest.skip(_SKIP_REASON)
    await gen_setup.assert_diff(
        both=[
            _BTREE_GIST,
            "CREATE TABLE room (id integer NOT NULL, code integer NOT NULL, valid_at daterange NOT NULL)",
        ],
        src=["ALTER TABLE room ADD CONSTRAINT room_uq UNIQUE (id, valid_at WITHOUT OVERLAPS)"],
        dst=["ALTER TABLE room ADD CONSTRAINT room_uq UNIQUE (id, code, valid_at WITHOUT OVERLAPS)"],
        diff=[
            'ALTER TABLE "public"."room" DROP CONSTRAINT "room_uq"',
            'ALTER TABLE "public"."room" ADD CONSTRAINT "room_uq" UNIQUE (id, code, valid_at WITHOUT OVERLAPS)',
        ],
    )


async def test_temporal_period_foreign_key_add(gen_setup: GenerateSetup) -> None:
    """
    A PERIOD foreign key present in target but missing in source -> ADD CONSTRAINT, with the
    PERIOD clause preserved and the referenced table schema-qualified.
    """
    if gen_setup.pg_major < 18:
        pytest.skip(_SKIP_REASON)
    await gen_setup.assert_diff(
        both=[
            _BTREE_GIST,
            "CREATE TABLE room (id integer NOT NULL, valid_at daterange NOT NULL, "
            "CONSTRAINT room_pkey PRIMARY KEY (id, valid_at WITHOUT OVERLAPS))",
            "CREATE TABLE booking (id integer NOT NULL, valid_at daterange NOT NULL)",
        ],
        src=[],
        dst=[
            "ALTER TABLE booking ADD CONSTRAINT booking_room_fkey "
            "FOREIGN KEY (id, PERIOD valid_at) REFERENCES room (id, PERIOD valid_at)"
        ],
        diff=[
            'ALTER TABLE "public"."booking" ADD CONSTRAINT "booking_room_fkey" '
            "FOREIGN KEY (id, PERIOD valid_at) REFERENCES public.room(id, PERIOD valid_at)"
        ],
    )


async def test_temporal_period_foreign_key_drop(gen_setup: GenerateSetup) -> None:
    """
    A PERIOD foreign key present in source but missing in target -> DROP CONSTRAINT.
    """
    if gen_setup.pg_major < 18:
        pytest.skip(_SKIP_REASON)
    await gen_setup.assert_diff(
        both=[
            _BTREE_GIST,
            "CREATE TABLE room (id integer NOT NULL, valid_at daterange NOT NULL, "
            "CONSTRAINT room_pkey PRIMARY KEY (id, valid_at WITHOUT OVERLAPS))",
            "CREATE TABLE booking (id integer NOT NULL, valid_at daterange NOT NULL)",
        ],
        src=[
            "ALTER TABLE booking ADD CONSTRAINT booking_room_fkey "
            "FOREIGN KEY (id, PERIOD valid_at) REFERENCES room (id, PERIOD valid_at)"
        ],
        dst=[],
        diff=['ALTER TABLE "public"."booking" DROP CONSTRAINT "booking_room_fkey"'],
    )


async def test_temporal_period_foreign_key_add_ordered_after_referenced_pk(gen_setup: GenerateSetup) -> None:
    """
    Creating the referenced and referencing temporal tables together: the WITHOUT OVERLAPS
    primary key is added before the PERIOD foreign key, and both come after the CREATE TABLEs.
    """
    if gen_setup.pg_major < 18:
        pytest.skip(_SKIP_REASON)
    await gen_setup.assert_diff(
        both=[_BTREE_GIST],
        src=[],
        dst=[
            "CREATE TABLE room (id integer NOT NULL, valid_at daterange NOT NULL, "
            "CONSTRAINT room_pkey PRIMARY KEY (id, valid_at WITHOUT OVERLAPS))",
            "CREATE TABLE booking (id integer NOT NULL, valid_at daterange NOT NULL)",
            "ALTER TABLE booking ADD CONSTRAINT booking_room_fkey "
            "FOREIGN KEY (id, PERIOD valid_at) REFERENCES room (id, PERIOD valid_at)",
        ],
        diff=[
            'CREATE TABLE "public"."booking" ("id" integer NOT NULL, "valid_at" daterange NOT NULL)',
            'CREATE TABLE "public"."room" ("id" integer NOT NULL, "valid_at" daterange NOT NULL)',
            'ALTER TABLE "public"."room" ADD CONSTRAINT "room_pkey" PRIMARY KEY (id, valid_at WITHOUT OVERLAPS)',
            'ALTER TABLE "public"."booking" ADD CONSTRAINT "booking_room_fkey" '
            "FOREIGN KEY (id, PERIOD valid_at) REFERENCES public.room(id, PERIOD valid_at)",
        ],
    )
