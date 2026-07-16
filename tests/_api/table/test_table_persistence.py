from tests._api.generate_setup import GenerateSetup


def test_create_unlogged_table(gen_setup: GenerateSetup) -> None:
    """
    An UNLOGGED table missing in source -> CREATE UNLOGGED TABLE (the keyword must be
    emitted or the table is created logged and never converges).
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE UNLOGGED TABLE cache (id integer)"],
        diff=['CREATE UNLOGGED TABLE "public"."cache" ("id" integer)'],
    )


def test_flip_logged_to_unlogged(gen_setup: GenerateSetup) -> None:
    """
    Same table, logged in source and unlogged in target -> ALTER TABLE ... SET UNLOGGED.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE cache (id integer)"],
        dst=["CREATE UNLOGGED TABLE cache (id integer)"],
        diff=['ALTER TABLE "public"."cache" SET UNLOGGED'],
    )


def test_flip_unlogged_to_logged(gen_setup: GenerateSetup) -> None:
    """
    Same table, unlogged in source and logged in target -> ALTER TABLE ... SET LOGGED.
    """
    gen_setup.assert_diff(
        src=["CREATE UNLOGGED TABLE cache (id integer)"],
        dst=["CREATE TABLE cache (id integer)"],
        diff=['ALTER TABLE "public"."cache" SET LOGGED'],
    )


def test_persistence_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same table, unlogged on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        src=["CREATE UNLOGGED TABLE cache (id integer)"],
        dst=["CREATE UNLOGGED TABLE cache (id integer)"],
        diff=[],
    )


def test_unlogged_partition_child(gen_setup: GenerateSetup) -> None:
    """
    A partition child is created UNLOGGED independently of its (necessarily logged) parent,
    and its persistence flips in place -- the column diff is skipped for a partition, but
    the persistence flip must still be emitted.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE events (id integer) PARTITION BY RANGE (id)",
            "CREATE UNLOGGED TABLE events_lo PARTITION OF events FOR VALUES FROM (0) TO (10)",
        ],
        dst=[
            "CREATE TABLE events (id integer) PARTITION BY RANGE (id)",
            "CREATE TABLE events_lo PARTITION OF events FOR VALUES FROM (0) TO (10)",
        ],
        diff=['ALTER TABLE "public"."events_lo" SET LOGGED'],
    )
