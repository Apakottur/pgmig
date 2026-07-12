-- Indexes (standalone only; constraint-backed indexes are excluded).
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    ic.relname AS index_name,
    pg_get_indexdef(i.indexrelid) AS index_def,
    replace(pg_get_indexdef(i.indexrelid), 'INDEX ' || quote_ident(ic.relname) || ' ON ', 'INDEX ON ')
	AS index_canonical,
    obj_description(i.indexrelid, 'pg_class') AS index_comment
FROM
    pg_index i
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_class c ON c.oid = i.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind = 'r'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg    -- index in an extension-owned schema (n.oid)
    --   [x] owning-table leg -- index on an extension-owned table (c.oid)
    --   [-] self leg         -- an extension-owned index sits on an extension-owned
    --                           table, so the owning-table leg already excludes it
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = n.oid
            AND d.deptype = 'e')
    -- Exclude indexes on tables an extension owns directly: they are recreated by
    -- CREATE EXTENSION, so re-emitting them would conflict.
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = c.oid
            AND d.deptype = 'e')
    AND NOT i.indisprimary
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.classid = 'pg_class'::regclass
            AND d.objid = i.indexrelid
            AND d.refclassid = 'pg_constraint'::regclass
            AND d.deptype = 'i')
ORDER BY
    n.nspname,
    c.relname,
    ic.relname;
