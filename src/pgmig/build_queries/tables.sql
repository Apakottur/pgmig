-- Tables (and their columns, in physical order).
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS column_type,
    a.attnotnull AS column_not_null,
    pg_get_expr(ad.adbin, ad.adrelid) AS column_default,
    col_description(a.attrelid, a.attnum) AS column_comment,
    obj_description(c.oid, 'pg_class') AS table_comment,
    a.attidentity AS column_identity,
    pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) AS column_serial_sequence
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid
    LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid
        AND ad.adnum = a.attnum
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
    AND a.attnum > 0
    AND NOT a.attisdropped
ORDER BY
    n.nspname,
    c.relname,
    a.attnum;
