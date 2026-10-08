from pgmig._keys import RelationKey
from pgmig._models import DbIntrospectionResult, Table


def partition_key_changed(src_table: Table, dst_table: Table) -> bool:
    """
    Whether a table's declarative partitioning key or strategy differs between the two sides
    (including a plain table gaining or losing PARTITION BY). Postgres has no in-place ALTER
    for this, so the table diff recreates the whole subtree destructively (see
    tables.generate).
    """
    return (src_table.is_partitioned or dst_table.is_partitioned) and (
        src_table.partition_strategy != dst_table.partition_strategy
        or src_table.partition_key != dst_table.partition_key
    )


def source_subtree(root: RelationKey, src_map: dict[RelationKey, Table]) -> set[RelationKey]:
    """
    Every source table in the partition subtree rooted at `root` (inclusive): the root plus
    all of its partitions, sub-partitions, and so on, walking `partition_parent` links.
    """
    subtree = {root}
    # Fixed-point loop: a table joins once its parent is in the subtree. Bounded by len(src_map).
    added = True
    while added:
        added = False
        for key, table in src_map.items():
            if key not in subtree and table.partition_parent in subtree:
                subtree.add(key)
                added = True
    return subtree


def get_repartitioned_tables(source: DbIntrospectionResult, target: DbIntrospectionResult) -> set[RelationKey]:
    """
    Source tables the migration drops and recreates from scratch because their partition
    subtree is repartitioned: every table present on both sides whose partition key/strategy
    changes, plus all of its source partitions (they cascade away with the parent's DROP).

    Computed lazily on first access and cached for the diff scope (see
    _ContextData.repartitioned_tables). Every generator treats these source tables as absent
    (ctx_iter_table_pairs skips them), so their tables, indexes, constraints, triggers and
    policies are re-emitted as newly created -- without mutating the source model.
    """
    src_map = {
        RelationKey(schema_name, table_name): table
        for schema_name, schema in source.schema_by_name.items()
        for table_name, table in schema.table_by_name.items()
    }
    repartitioned: set[RelationKey] = set()
    for key, src_table in src_map.items():
        dst_schema = target.schema_by_name.get(key.schema)
        dst_table = dst_schema.table_by_name.get(key.name) if dst_schema else None
        if dst_table is not None and partition_key_changed(src_table, dst_table):
            repartitioned |= source_subtree(key, src_map)
    return repartitioned
