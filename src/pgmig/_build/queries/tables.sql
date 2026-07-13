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
    pg_get_userbyid(c.relowner) AS table_owner,
    a.attidentity AS column_identity,
    pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) AS column_serial_sequence
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    -- LEFT JOIN (with the column filters in the ON, not the WHERE) so a zero-column
    -- table still yields one row -- otherwise it produces no rows and is invisible to
    -- the diff, silently claiming convergence while the whole table is missing.
    LEFT JOIN pg_attribute a ON a.attrelid = c.oid
        AND a.attnum > 0
        AND NOT a.attisdropped
    LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid
        AND ad.adnum = a.attnum
WHERE
    c.relkind = 'r'
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
