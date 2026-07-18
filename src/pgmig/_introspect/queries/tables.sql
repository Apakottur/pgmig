-- Tables (and their columns, in physical order). Includes partitioned parents
-- (relkind 'p') and partitions (relkind 'r'/'p' with relispartition).
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS column_type,
    -- The column's collation, but only when it differs from the type's default collation
    -- (pg_type.typcollation). Emitting the default for every column that has one would make an
    -- identical DB diff against itself; a column with no collation has attcollation 0 = the
    -- type default, so it yields NULL here too.
    CASE WHEN a.attcollation <> col_type.typcollation THEN
        co.collname
    END AS column_collation,
    a.attnotnull AS column_not_null,
    -- A generated column's expression lives in pg_attrdef too, so split by attgenerated:
    -- a plain column's expression is a DEFAULT, a generated column's is its GENERATED clause.
    CASE WHEN a.attgenerated = '' THEN
        pg_get_expr(ad.adbin, ad.adrelid)
    END AS column_default,
    CASE WHEN a.attgenerated <> '' THEN
        pg_get_expr(ad.adbin, ad.adrelid)
    END AS generation_expression,
    col_description(a.attrelid, a.attnum) AS column_comment,
    obj_description(c.oid, 'pg_class') AS table_comment,
    pg_get_userbyid(c.relowner) AS table_owner,
    -- 'u' = UNLOGGED, 'p' = permanent. Temp tables ('t') live in pg_temp schemas, which
    -- the schema filter below excludes, and partitioned parents cannot be unlogged, so
    -- only 'p'/'u' reach the loader.
    c.relpersistence AS table_persistence,
    -- Row-level security: relrowsecurity is ENABLE ROW LEVEL SECURITY, relforcerowsecurity is
    -- FORCE ROW LEVEL SECURITY (applies the policies to the table owner too). Both are diffed
    -- as ALTER TABLE toggles; the policies themselves are a separate table-child object.
    c.relrowsecurity AS table_row_security,
    c.relforcerowsecurity AS table_force_row_security,
    -- Replica identity: 'd' default, 'n' nothing, 'f' full, 'i' using index. Logical
    -- replication depends on it, so a difference must be diffed. For 'i', resolve the
    -- identity index's (schema-local, unqualified) name via pg_index.indisreplident.
    c.relreplident AS table_replica_identity,
    CASE WHEN c.relreplident = 'i' THEN
    (
        SELECT
            ri.relname
        FROM
            pg_index ix
            JOIN pg_class ri ON ri.oid = ix.indexrelid
        WHERE
            ix.indrelid = c.oid
            AND ix.indisreplident)
    END AS table_replica_identity_index,
    a.attidentity AS column_identity,
    a.attgenerated AS column_generated,
    pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) AS column_serial_sequence,
    -- Backing sequence options of an identity column (NULL for every non-identity column).
    -- The identity sequence is linked to its column by an INTERNAL ('i') pg_depend edge.
    idseq.seqstart AS identity_start,
    idseq.seqincrement AS identity_increment,
    idseq.seqmin AS identity_min,
    idseq.seqmax AS identity_max,
    idseq.seqcache AS identity_cache,
    idseq.seqcycle AS identity_cycle,
    -- Partitioning metadata (per table, repeated on every column row; the loader reads
    -- it once when it first creates the table).
    pt.partstrat::text AS partition_strategy,
    CASE WHEN c.relkind = 'p' THEN
        pg_get_partkeydef (c.oid)
    END AS partition_key,
    CASE WHEN c.relispartition THEN
        pg_get_expr(c.relpartbound, c.oid)
    END AS partition_bound,
    pn.nspname AS partition_parent_schema,
    pc.relname AS partition_parent_name
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    -- Partitioned-parent metadata (partition strategy). NULL for a plain table.
    LEFT JOIN pg_partitioned_table pt ON pt.partrelid = c.oid
    -- Partition-parent link. Gated on relispartition so legacy INHERITS parents (which
    -- also appear in pg_inherits) do not get misclassified as partitions.
    LEFT JOIN pg_inherits inh ON inh.inhrelid = c.oid
        AND c.relispartition
    LEFT JOIN pg_class pc ON pc.oid = inh.inhparent
    LEFT JOIN pg_namespace pn ON pn.oid = pc.relnamespace
    -- LEFT JOIN (with the column filters in the ON, not the WHERE) so a zero-column
    -- table still yields one row -- otherwise it produces no rows and is invisible to
    -- the diff, silently claiming convergence while the whole table is missing.
    LEFT JOIN pg_attribute a ON a.attrelid = c.oid
        AND a.attnum > 0
        AND NOT a.attisdropped
    LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid
        AND ad.adnum = a.attnum
    LEFT JOIN pg_type col_type ON col_type.oid = a.atttypid
    LEFT JOIN pg_collation co ON co.oid = a.attcollation
    -- Identity column's backing sequence: the sequence has an INTERNAL dependency on the
    -- column (deptype 'i'). Serial columns use deptype 'a' instead, so this matches identity
    -- sequences only. NULL-joins for every non-identity column.
    LEFT JOIN pg_depend idseq_dep ON idseq_dep.refobjid = a.attrelid
        AND idseq_dep.refobjsubid = a.attnum
        AND idseq_dep.deptype = 'i'
        AND idseq_dep.classid = 'pg_class'::regclass
        AND idseq_dep.refclassid = 'pg_class'::regclass
    LEFT JOIN pg_sequence idseq ON idseq.seqrelid = idseq_dep.objid
WHERE
    c.relkind IN ('r', 'p')
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg  -- table in an extension-owned schema (n.oid)
    --   [x] self leg       -- the table itself is extension-owned (c.oid)
    --   [-] owning-table leg -- n/a; the table is the owner
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = n.oid
            AND d.deptype = 'e')
    -- Exclude tables an extension owns directly (e.g. PostGIS spatial_ref_sys in
    -- public): CREATE EXTENSION already creates them, so re-emitting CREATE TABLE
    -- would fail with "relation already exists".
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = c.oid
            AND d.deptype = 'e')
ORDER BY
    n.nspname,
    c.relname,
    a.attnum;
