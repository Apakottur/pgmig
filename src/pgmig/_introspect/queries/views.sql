-- Views and materialized views (user ones only; extension-owned ones are excluded).
-- relkind tells the loader which schema mapping a row belongs to ('v' view, 'm' matview).
SELECT
    n.nspname AS schema_name,
    c.relkind,
    c.relname AS view_name,
    pg_get_viewdef(c.oid) AS view_definition,
    obj_description(c.oid, 'pg_class') AS view_comment,
    c.reloptions AS view_options,
    pg_get_userbyid(c.relowner) AS view_owner
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind IN ('v', 'm')
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg  -- (mat)view in an extension-owned schema (n.oid)
    --   [x] self leg       -- the (mat)view itself is extension-owned (c.oid)
    --   [ ] owning-table leg -- n/a, a (mat)view is not attached to a table
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
