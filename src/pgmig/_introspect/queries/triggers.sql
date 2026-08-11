-- Triggers (user triggers only; internal RI/constraint-backing triggers are excluded).
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relkind::text AS relkind,
    t.tgname AS trigger_name,
    pg_get_triggerdef(t.oid) AS trigger_def,
    replace(pg_get_triggerdef(t.oid), 'TRIGGER ' || quote_ident(t.tgname) || ' ', 'TRIGGER ') AS trigger_canonical,
    -- Enable state (pg_get_triggerdef omits it): O=origin/default, D=disabled,
    -- R=enable replica, A=enable always.
    t.tgenabled AS trigger_enabled,
    obj_description(t.oid, 'pg_trigger') AS trigger_comment
FROM
    pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    NOT t.tgisinternal
    -- Ordinary tables ('r'), partitioned parents ('p'), and views ('v', which carry only
    -- INSTEAD OF triggers). The loader routes each row to its table or view by relkind.
    AND c.relkind IN ('r', 'p', 'v')
    -- Exclude triggers cloned onto partitions from a partitioned parent (tgparentid <> 0):
    -- they are (re)created by the parent's cascading CREATE TRIGGER, and Postgres refuses a
    -- direct DROP on them. A parent-level trigger and a table's own local trigger both have
    -- tgparentid = 0 and are kept. Mirrors constraints.sql's conparentid = 0 leg.
    AND t.tgparentid = 0
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
    t.tgname;
