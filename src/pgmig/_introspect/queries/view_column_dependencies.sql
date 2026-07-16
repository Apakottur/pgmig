-- Column-level dependencies of views and materialized views: for each user view or matview,
-- the table columns its definition reads. A view's rewrite rule (pg_rewrite) depends
-- (pg_depend) on the columns it reads; a column-level dependency carries refobjsubid > 0,
-- which is the referenced column's attnum. The view and matview diffs use these to drop and
-- recreate a (mat)view around a change to a column it reads (Postgres refuses to alter the
-- type of, or drop, a column a view or matview uses). View-on-view edges are handled
-- separately (view_dependencies.sql), so the referenced side is restricted to ordinary and
-- partitioned tables here.
--
-- A whole-row reference (SELECT t FROM t) carries refobjsubid = 0: the dependency is on the
-- relation, not a single column. A materialized view stores the table's composite row type,
-- so a type change to ANY column then fails ("cannot alter table because column m.t uses its
-- row type"); a refobjsubid = 0 row for a matview therefore expands to every live column of
-- the table. Plain views do not store the row type (such an ALTER succeeds), so their
-- refobjsubid = 0 rows are ignored. This conservatively also catches a matview whose only
-- whole-relation reference is an aggregate (SELECT count(*) FROM t), which would not actually
-- block the ALTER -- an accepted, rare over-recreate rather than a missed apply failure.
SELECT DISTINCT
    dependent_ns.nspname AS view_schema,
    dependent.relname AS view_name,
    table_ns.nspname AS table_schema,
    tbl.relname AS table_name,
    att.attname AS column_name
FROM
    pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    JOIN pg_namespace dependent_ns ON dependent_ns.oid = dependent.relnamespace
    JOIN pg_class tbl ON tbl.oid = d.refobjid
    JOIN pg_namespace table_ns ON table_ns.oid = tbl.relnamespace
    JOIN pg_attribute att ON att.attrelid = tbl.oid
        AND att.attnum > 0
        AND NOT att.attisdropped
        AND (att.attnum = d.refobjsubid
            OR (d.refobjsubid = 0
                AND dependent.relkind = 'm'))
WHERE
    dependent.relkind IN ('v', 'm')
    AND tbl.relkind IN ('r', 'p')
    AND (d.refobjsubid > 0
        OR (d.refobjsubid = 0
            AND dependent.relkind = 'm'))
    AND dependent_ns.nspname NOT LIKE 'pg_%'
    AND dependent_ns.nspname <> 'information_schema'
ORDER BY
    view_schema,
    view_name,
    table_schema,
    table_name,
    column_name;
