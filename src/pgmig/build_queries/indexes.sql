-- Indexes (standalone only; constraint-backed indexes are excluded).
SELECT
    n.nspname,
    c.relname,
    ic.relname,
    pg_get_indexdef(i.indexrelid),
    replace(pg_get_indexdef(i.indexrelid), 'INDEX ' || quote_ident(ic.relname) || ' ON ', 'INDEX ON ')
FROM
    pg_index i
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_class c ON c.oid = i.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind = 'r'
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
            AND d.deptype = 'i');
