-- Dependencies among plain views: a user view whose definition reads from another plain
-- view. A view's rewrite rule (pg_rewrite) depends (pg_depend) on the relations it reads;
-- a dependency on another view means ordering the create/drop needs a topological sort
-- within the view phases (see view_dependencies.py load). Matview-involving pairs are
-- excluded here and handled by matview_dependencies.sql instead. A dependency on a plain
-- table is fine (tables are created before, and dropped after, the view phases).
SELECT DISTINCT
    dependent_ns.nspname AS dependent_schema,
    dependent.relname AS dependent_view,
    referenced_ns.nspname AS referenced_schema,
    referenced.relname AS referenced_view
FROM
    pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    JOIN pg_namespace dependent_ns ON dependent_ns.oid = dependent.relnamespace
    JOIN pg_class referenced ON referenced.oid = d.refobjid
    JOIN pg_namespace referenced_ns ON referenced_ns.oid = referenced.relnamespace
WHERE
    dependent.relkind = 'v'
    AND referenced.relkind = 'v'
    AND dependent.oid <> referenced.oid
    -- Only edges among managed objects belong here: an edge to a view pgmig does not model
    -- (a system view, or an extension-owned one in a user schema) is bogus state that would
    -- mislead the ordering and recreate logic. Exclude, on each side, what views.sql /
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
