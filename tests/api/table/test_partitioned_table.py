from tests.api.generate_setup import GenerateSetup


def test_partitioned_table_create_range(gen_setup: GenerateSetup) -> None:
    """
    A range-partitioned parent and its partition, present in target only -> CREATE the
    parent (with PARTITION BY) then each partition (with PARTITION OF, no column list).
    """
    gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE events (id integer NOT NULL) PARTITION BY RANGE (id)",
            "CREATE TABLE events_2024 PARTITION OF events FOR VALUES FROM (1) TO (100)",
        ],
        diff=[
            'CREATE TABLE "public"."events" ("id" integer NOT NULL) PARTITION BY RANGE (id)',
            'CREATE TABLE "public"."events_2024" PARTITION OF "public"."events" FOR VALUES FROM (1) TO (100)',
        ],
    )


def test_partitioned_table_create_list_and_default(gen_setup: GenerateSetup) -> None:
    """
    A list-partitioned table with an explicit partition and a DEFAULT partition. Creates
    are ordered parent first, then partitions by name.
    """
    gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE t (id integer, region text) PARTITION BY LIST (region)",
            "CREATE TABLE t_us PARTITION OF t FOR VALUES IN ('us', 'ca')",
            "CREATE TABLE t_def PARTITION OF t DEFAULT",
        ],
        diff=[
            'CREATE TABLE "public"."t" ("id" integer, "region" text) PARTITION BY LIST (region)',
            'CREATE TABLE "public"."t_def" PARTITION OF "public"."t" DEFAULT',
            'CREATE TABLE "public"."t_us" PARTITION OF "public"."t" FOR VALUES IN (\'us\', \'ca\')',
        ],
    )


def test_partitioned_table_create_hash(gen_setup: GenerateSetup) -> None:
    """
    A hash-partitioned table.
    """
    gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE h (id integer) PARTITION BY HASH (id)",
            "CREATE TABLE h0 PARTITION OF h FOR VALUES WITH (MODULUS 4, REMAINDER 0)",
        ],
        diff=[
            'CREATE TABLE "public"."h" ("id" integer) PARTITION BY HASH (id)',
            'CREATE TABLE "public"."h0" PARTITION OF "public"."h" FOR VALUES WITH (modulus 4, remainder 0)',
        ],
    )


def test_partitioned_table_subpartition(gen_setup: GenerateSetup) -> None:
    """
    A partition that is itself partitioned (sub-partitioning). Creates are ordered by
    hierarchy depth: grandparent, parent, leaf.
    """
    gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE s (id integer, region text) PARTITION BY RANGE (id)",
            "CREATE TABLE s_1 PARTITION OF s FOR VALUES FROM (1) TO (100) PARTITION BY LIST (region)",
            "CREATE TABLE s_1_us PARTITION OF s_1 FOR VALUES IN ('us')",
        ],
        diff=[
            'CREATE TABLE "public"."s" ("id" integer, "region" text) PARTITION BY RANGE (id)',
            'CREATE TABLE "public"."s_1" PARTITION OF "public"."s" '
            "FOR VALUES FROM (1) TO (100) PARTITION BY LIST (region)",
            'CREATE TABLE "public"."s_1_us" PARTITION OF "public"."s_1" FOR VALUES IN (\'us\')',
        ],
    )


def test_partitioned_table_drop_whole_unit(gen_setup: GenerateSetup) -> None:
    """
    A partitioned table present in source only -> a single DROP TABLE on the parent; the
    partition is dropped by cascade, not re-emitted.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE events (id integer) PARTITION BY RANGE (id)",
            "CREATE TABLE events_2024 PARTITION OF events FOR VALUES FROM (1) TO (100)",
        ],
        dst=[],
        diff=['DROP TABLE "public"."events"'],
    )


def test_partitioned_table_add_partition(gen_setup: GenerateSetup) -> None:
    """
    Parent on both sides, a new partition in target only -> CREATE ... PARTITION OF.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE events (id integer) PARTITION BY RANGE (id)"],
        src=[],
        dst=["CREATE TABLE events_2024 PARTITION OF events FOR VALUES FROM (1) TO (100)"],
        diff=['CREATE TABLE "public"."events_2024" PARTITION OF "public"."events" FOR VALUES FROM (1) TO (100)'],
    )


def test_partitioned_table_remove_partition(gen_setup: GenerateSetup) -> None:
    """
    Parent on both sides, a partition in source only (parent survives) -> DROP TABLE the
    partition.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE events (id integer) PARTITION BY RANGE (id)"],
        src=["CREATE TABLE events_2024 PARTITION OF events FOR VALUES FROM (1) TO (100)"],
        dst=[],
        diff=['DROP TABLE "public"."events_2024"'],
    )


def test_partitioned_table_attach(gen_setup: GenerateSetup) -> None:
    """
    A table that is standalone in source but a partition in target -> ATTACH PARTITION.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE events (id integer) PARTITION BY RANGE (id)"],
        src=["CREATE TABLE events_2024 (id integer)"],
        dst=["CREATE TABLE events_2024 PARTITION OF events FOR VALUES FROM (1) TO (100)"],
        diff=['ALTER TABLE "public"."events" ATTACH PARTITION "public"."events_2024" FOR VALUES FROM (1) TO (100)'],
    )


def test_partitioned_table_detach(gen_setup: GenerateSetup) -> None:
    """
    A table that is a partition in source but standalone in target -> DETACH PARTITION
    (the table itself survives).
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE events (id integer) PARTITION BY RANGE (id)"],
        src=["CREATE TABLE events_2024 PARTITION OF events FOR VALUES FROM (1) TO (100)"],
        dst=["CREATE TABLE events_2024 (id integer)"],
        diff=['ALTER TABLE "public"."events" DETACH PARTITION "public"."events_2024"'],
    )


def test_partitioned_table_reparent(gen_setup: GenerateSetup) -> None:
    """
    A partition attached to a different parent across the diff -> DETACH from the source
    parent, then ATTACH to the target parent.
    """
    gen_setup.assert_diff(
        both=[
            "CREATE TABLE p1 (id integer) PARTITION BY RANGE (id)",
            "CREATE TABLE p2 (id integer) PARTITION BY RANGE (id)",
        ],
        src=["CREATE TABLE part PARTITION OF p1 FOR VALUES FROM (1) TO (100)"],
        dst=["CREATE TABLE part PARTITION OF p2 FOR VALUES FROM (1) TO (100)"],
        diff=[
            'ALTER TABLE "public"."p1" DETACH PARTITION "public"."part"',
            'ALTER TABLE "public"."p2" ATTACH PARTITION "public"."part" FOR VALUES FROM (1) TO (100)',
        ],
    )


def test_partitioned_table_index_on_parent(gen_setup: GenerateSetup) -> None:
    """
    An index declared on a partitioned parent is emitted once (ON, not ON ONLY) and
    cascades to partitions; the auto-created child mirror index is not re-emitted, so the
    migration converges.
    """
    gen_setup.assert_diff(
        both=[
            "CREATE TABLE events (id integer, region text) PARTITION BY RANGE (id)",
            "CREATE TABLE events_2024 PARTITION OF events FOR VALUES FROM (1) TO (100)",
        ],
        src=[],
        dst=["CREATE INDEX events_region_idx ON events (region)"],
        diff=["CREATE INDEX events_region_idx ON public.events USING btree (region)"],
    )


def test_partitioned_table_primary_key_on_parent(gen_setup: GenerateSetup) -> None:
    """
    A primary key declared on a partitioned parent is emitted once and cascades to
    partitions; the inherited child constraint is not re-emitted.
    """
    gen_setup.assert_diff(
        both=[
            "CREATE TABLE events (id integer NOT NULL) PARTITION BY RANGE (id)",
            "CREATE TABLE events_2024 PARTITION OF events FOR VALUES FROM (1) TO (100)",
        ],
        src=[],
        dst=["ALTER TABLE events ADD CONSTRAINT events_pkey PRIMARY KEY (id)"],
        diff=['ALTER TABLE "public"."events" ADD CONSTRAINT "events_pkey" PRIMARY KEY (id)'],
    )


def test_partitioned_table_cross_schema(gen_setup: GenerateSetup) -> None:
    """
    A partition living in a different schema than its parent is created (and referenced)
    with fully qualified names.
    """
    gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE SCHEMA parts",
            "CREATE TABLE events (id integer) PARTITION BY RANGE (id)",
            "CREATE TABLE parts.events_2024 PARTITION OF events FOR VALUES FROM (1) TO (100)",
        ],
        diff=[
            'CREATE SCHEMA "parts"',
            'CREATE TABLE "public"."events" ("id" integer) PARTITION BY RANGE (id)',
            'CREATE TABLE "parts"."events_2024" PARTITION OF "public"."events" FOR VALUES FROM (1) TO (100)',
        ],
    )


def test_partitioned_table_key_change_raises(gen_setup: GenerateSetup) -> None:
    """
    Changing the partition key/strategy is impossible in place; refuse loudly rather than
    emit a data-destructive DROP + CREATE.
    """
    gen_setup.assert_not_implemented(
        src=["CREATE TABLE events (id integer, region text) PARTITION BY RANGE (id)"],
        dst=["CREATE TABLE events (id integer, region text) PARTITION BY LIST (region)"],
        match=r"Partition key/strategy change is not supported",
    )


def test_partitioned_table_bound_change_raises(gen_setup: GenerateSetup) -> None:
    """
    Changing a partition's bound (same parent) is impossible in place; refuse loudly.
    """
    gen_setup.assert_not_implemented(
        both=["CREATE TABLE events (id integer) PARTITION BY RANGE (id)"],
        src=["CREATE TABLE events_2024 PARTITION OF events FOR VALUES FROM (1) TO (100)"],
        dst=["CREATE TABLE events_2024 PARTITION OF events FOR VALUES FROM (1) TO (200)"],
        match=r"Partition bound change is not supported",
    )
