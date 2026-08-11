-- Table columns typed by a user enum (directly, or as an array of the enum). The enum diff
-- uses these to rewrite dependent columns when an enum's values are removed or reordered -- a
-- change with no in-place ALTER form, requiring the enum to be dropped and recreated with every
-- dependent column retyped through text. The hazard-flag columns (is_generated, in_index,
-- in_constraint) let the diff refuse shapes the rewrite does not handle instead of emitting SQL
-- that fails at apply. Mirrors the pg_attribute join pattern of view_column_dependencies.sql.
--
-- A column of type enum[] carries atttypid = the enum's array type (pg_type.typarray), not the
-- enum oid itself; both are matched, and is_array records which. Only ordinary and partitioned
-- tables are considered (relkind 'r','p'); enum columns of matviews/composite types are out of
-- the rewrite's scope and are caught elsewhere (view_column_dependencies raise) or left to fail.
SELECT
    en.nspname AS enum_schema,
    et.typname AS enum_name,
    tn.nspname AS table_schema,
    tbl.relname AS table_name,
    att.attname AS column_name,
    (att.atttypid = et.typarray) AS is_array,
    (att.attgenerated <> '') AS is_generated,
    EXISTS (
        SELECT
            1
        FROM
            pg_index i
        WHERE
            i.indrelid = tbl.oid
            AND att.attnum = ANY (i.indkey)) AS in_index,
    EXISTS (
        SELECT
            1
        FROM
            pg_constraint c
        WHERE
            c.conrelid = tbl.oid
            AND att.attnum = ANY (c.conkey)) AS in_constraint
FROM
    pg_type et
    JOIN pg_namespace en ON en.oid = et.typnamespace
    JOIN pg_attribute att ON att.atttypid = et.oid
        OR att.atttypid = et.typarray
    JOIN pg_class tbl ON tbl.oid = att.attrelid
    JOIN pg_namespace tn ON tn.oid = tbl.relnamespace
WHERE
    et.typtype = 'e'
    AND att.attnum > 0
    AND NOT att.attisdropped
    AND tbl.relkind IN ('r', 'p')
    AND en.nspname NOT LIKE 'pg_%'
    AND en.nspname <> 'information_schema'
    AND tn.nspname NOT LIKE 'pg_%'
    AND tn.nspname <> 'information_schema'
    -- Extension-owned enums are excluded, same as enums.sql (namespace leg + self leg).
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = en.oid
            AND d.deptype = 'e')
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = et.oid
            AND d.deptype = 'e')
ORDER BY
    enum_schema,
    enum_name,
    table_schema,
    table_name,
    column_name;
