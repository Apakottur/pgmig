-- Materialized views (user matviews only; extension-owned ones are excluded).
-- Mirror of views.sql; the two differ only in the relkind ('m' here, 'v' there). Keep in sync.
SELECT
    n.nspname AS schema_name,
    c.relname AS view_name,
    pg_get_viewdef(c.oid) AS view_definition,
    obj_description(c.oid, 'pg_class') AS view_comment,
    c.reloptions AS view_options,
    pg_get_userbyid(c.relowner) AS view_owner
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind = 'm'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg  -- matview in an extension-owned schema (n.oid)
    --   [x] self leg       -- the matview itself is extension-owned (c.oid)
    --   [ ] owning-table leg -- n/a, a matview is not attached to a table
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
    c.relname;
