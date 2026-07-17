-- Dependencies involving a materialized view: a view or matview whose definition reads
-- from another view or matview, where at least one side is a materialized view. Plain
-- view-on-view dependencies live in view_dependencies.sql; every matview-involving edge
-- lives here. matview_dependencies.py splits the rows by dependent kind: a matview reading
-- a view/matview is loaded as an ordering edge; a plain view reading a matview is refused
-- (the matview's phase is later than the view's, so the view cannot be ordered first). A
-- dependency on a plain table is fine (tables are created before, and dropped after, the
-- view phases).
SELECT DISTINCT
    dependent_ns.nspname AS dependent_schema,
    dependent.relname AS dependent_view,
    dependent.relkind AS dependent_kind,
    referenced_ns.nspname AS referenced_schema,
    referenced.relname AS referenced_view,
    referenced.relkind AS referenced_kind
FROM
    pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    JOIN pg_namespace dependent_ns ON dependent_ns.oid = dependent.relnamespace
    JOIN pg_class referenced ON referenced.oid = d.refobjid
    JOIN pg_namespace referenced_ns ON referenced_ns.oid = referenced.relnamespace
WHERE
    dependent.relkind IN ('v', 'm')
    AND referenced.relkind IN ('v', 'm')
    AND (dependent.relkind = 'm'
        OR referenced.relkind = 'm')
    AND dependent.oid <> referenced.oid
    -- Both endpoints must be objects pgmig manages, or this guard falsely refuses a database
    -- over a dependency on something it never diffs. A monitoring matview over pg_stat_activity
    -- (system schema) or over pg_stat_statements (extension-owned view, in the user's own
    -- public schema) is the common trigger. Exclude, on each side, what views.sql /
    -- materialized_views.sql exclude from the model:
    --   [x] system-schema leg -- pg_catalog / information_schema (nspname)
    --   [x] namespace leg     -- object in an extension-owned schema (*_ns.oid)
    --   [x] self leg          -- the object itself is extension-owned (dependent/referenced.oid)
    AND dependent_ns.nspname NOT LIKE 'pg_%'
    AND dependent_ns.nspname <> 'information_schema'
    AND referenced_ns.nspname NOT LIKE 'pg_%'
    AND referenced_ns.nspname <> 'information_schema'
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend ed
        WHERE
            ed.objid = dependent_ns.oid
            AND ed.deptype = 'e')
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend ed
        WHERE
            ed.objid = dependent.oid
            AND ed.deptype = 'e')
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend ed
        WHERE
            ed.objid = referenced_ns.oid
            AND ed.deptype = 'e')
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend ed
        WHERE
            ed.objid = referenced.oid
            AND ed.deptype = 'e')
ORDER BY
    dependent_schema,
    dependent_view,
    referenced_schema,
    referenced_view;
