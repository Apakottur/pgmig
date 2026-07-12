-- Constraints (primary key, unique, and check).
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    con.conname AS con_name,
    pg_get_constraintdef(con.oid) AS con_def,
    con.contype AS con_type,
    (
        SELECT
            array_agg(a.attname ORDER BY k.ord)
        FROM
            unnest(con.conkey)
            WITH ORDINALITY AS k (attnum, ord)
            JOIN pg_attribute a ON a.attrelid = con.conrelid
                AND a.attnum = k.attnum) AS con_columns,
        obj_description(con.oid, 'pg_constraint') AS con_comment
    FROM
        pg_constraint con
    JOIN pg_class c ON c.oid = con.conrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind = 'r'
    AND con.contype IN ('p', 'u', 'c', 'f')
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = n.oid
            AND d.deptype = 'e')
    -- Exclude constraints on tables an extension owns directly: they are recreated by
    -- CREATE EXTENSION, so re-emitting them would conflict.
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = c.oid
            AND d.deptype = 'e');
