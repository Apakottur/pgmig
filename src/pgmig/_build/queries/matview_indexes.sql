-- Indexes on a materialized view. The basic materialized-view cut does not model matview
-- indexes, and a definition change drops and recreates the matview (which would silently
-- lose them), so their presence must raise rather than be discarded. Extension-owned
-- indexes/matviews are excluded (the extension recreates them).
SELECT
    n.nspname AS schema_name,
    c.relname AS view_name,
    ic.relname AS index_name
FROM
    pg_index i
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_class c ON c.oid = i.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind = 'm'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion: index in an extension-owned schema, or an index on a
    -- matview an extension owns directly (recreated by CREATE EXTENSION).
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = n.oid
            AND d.deptype = 'e')
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
    ic.relname;
