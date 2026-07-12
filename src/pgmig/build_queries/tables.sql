-- Tables (and their columns, ordered by name).
SELECT
    n.nspname,
    c.relname,
    a.attname,
    format_type(a.atttypid, a.atttypmod),
    a.attnotnull,
    pg_get_expr(ad.adbin, ad.adrelid),
    col_description(a.attrelid, a.attnum),
    obj_description(c.oid, 'pg_class'),
    a.attidentity,
    pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname)
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
    AND a.attnum > 0
    AND NOT a.attisdropped
ORDER BY
    n.nspname,
    c.relname,
    a.attname;
