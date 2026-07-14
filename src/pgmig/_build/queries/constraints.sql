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
    c.relkind IN ('r', 'p')
    AND con.contype IN ('p', 'u', 'c', 'f')
    -- Exclude constraints inherited from a partitioned parent (conparentid <> 0): they are
    -- (re)created by the parent's cascading ADD CONSTRAINT. A parent-level declaration and
    -- a child's own local constraint both have conparentid = 0 and are kept.
    AND con.conparentid = 0
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg    -- constraint in an extension-owned schema (n.oid)
    --   [x] owning-table leg -- constraint on an extension-owned table (c.oid)
    --   [-] self leg         -- an extension-owned constraint sits on an extension-owned
    --                           table, so the owning-table leg already excludes it
    {{exclude_extension_owned :n.oid }}
    -- Exclude constraints on tables an extension owns directly: they are recreated by
    -- CREATE EXTENSION, so re-emitting them would conflict.
    {{exclude_extension_owned :c.oid }};
