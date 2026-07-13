-- Dependencies among (materialized) views: a user view or matview whose definition reads
-- from another view or matview. A view's rewrite rule (pg_rewrite) depends (pg_depend) on
-- the relations it reads; a dependency on another view/matview means ordering the
-- create/drop needs a topological sort within the shared view phases, which is not
-- implemented yet, so such a pair must be reported rather than mis-ordered. A dependency
-- on a plain table is fine (tables are created before, and dropped after, the view phases).
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
    AND dependent.oid <> referenced.oid
    AND dependent_ns.nspname NOT LIKE 'pg_%'
    AND dependent_ns.nspname <> 'information_schema'
ORDER BY
    dependent_schema,
    dependent_view,
    referenced_schema,
    referenced_view;
