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
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg    -- trigger in an extension-owned schema (n.oid)
    --   [x] owning-table leg -- trigger on an extension-owned table, e.g. a user audit
    --                           trigger on PostGIS spatial_ref_sys (c.oid)
    --   [-] self leg         -- an extension-owned trigger sits on an extension-owned
    --                           table, so the owning-table leg already excludes it
    {{exclude_extension_owned :n.oid }} {{exclude_extension_owned :c.oid }}
ORDER BY
    n.nspname,
    c.relname,
    t.tgname;
