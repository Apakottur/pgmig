-- Triggers (user triggers only; internal RI/constraint-backing triggers are excluded).
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    t.tgname AS trigger_name,
    pg_get_triggerdef(t.oid) AS trigger_def,
    replace(pg_get_triggerdef(t.oid), 'TRIGGER ' || quote_ident(t.tgname) || ' ', 'TRIGGER ') AS trigger_canonical,
    obj_description(t.oid, 'pg_trigger') AS trigger_comment
FROM
    pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    NOT t.tgisinternal
    AND c.relkind = 'r'
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
ORDER BY
    n.nspname,
    c.relname,
    t.tgname;
