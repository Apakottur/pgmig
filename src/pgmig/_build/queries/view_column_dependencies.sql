-- Column-level dependencies of plain views: for each user view, the table columns its
-- definition reads. A view's rewrite rule (pg_rewrite) depends (pg_depend) on the columns
-- it reads; a column-level dependency carries refobjsubid > 0, which is the referenced
-- column's attnum. The view diff uses these to drop and recreate a view around a change to
-- a column it reads (Postgres refuses to alter the type of, or drop, a column a view uses).
-- View-on-view edges are handled separately (view_dependencies.sql), so the referenced side
-- is restricted to ordinary and partitioned tables here.
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
        AND att.attnum = d.refobjsubid
WHERE
    dependent.relkind = 'v'
    AND tbl.relkind IN ('r', 'p')
    AND d.refobjsubid > 0
    AND dependent_ns.nspname NOT LIKE 'pg_%'
    AND dependent_ns.nspname <> 'information_schema'
ORDER BY
    view_schema,
    view_name,
    table_schema,
    table_name,
    column_name;
