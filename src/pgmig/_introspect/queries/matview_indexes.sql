-- Indexes on materialized views. A matview index is dropped and recreated with its
-- matview on a definition change, so it must be modelled to be re-emitted. Matviews carry
-- no primary keys or constraints, so (unlike indexes.sql) there is no indisprimary or
-- constraint-backed leg to exclude. Extension-owned indexes/matviews are excluded (the
-- extension recreates them).
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
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
