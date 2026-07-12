-- Constraints (primary key, unique, and check).
SELECT
    n.nspname,
    c.relname,
    con.conname,
    pg_get_constraintdef(con.oid),
    con.contype,
    (
        SELECT
            array_agg(a.attname ORDER BY k.ord)
        FROM
            unnest(con.conkey)
            WITH ORDINALITY AS k (attnum, ord)
            JOIN pg_attribute a ON a.attrelid = con.conrelid
                AND a.attnum = k.attnum),
        obj_description(con.oid, 'pg_constraint')
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
            AND d.deptype = 'e');
