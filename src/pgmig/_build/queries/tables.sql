-- Tables (and their columns, in physical order). Includes partitioned parents
-- (relkind 'p') and partitions (relkind 'r'/'p' with relispartition).
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS column_type,
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
    a.attidentity AS column_identity,
    a.attgenerated AS column_generated,
    pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) AS column_serial_sequence,
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
    {{exclude_extension_owned :n.oid }}
    -- Exclude tables an extension owns directly (e.g. PostGIS spatial_ref_sys in
    -- public): CREATE EXTENSION already creates them, so re-emitting CREATE TABLE
    -- would fail with "relation already exists".
    {{exclude_extension_owned :c.oid }}
ORDER BY
    n.nspname,
    c.relname,
    a.attnum;
