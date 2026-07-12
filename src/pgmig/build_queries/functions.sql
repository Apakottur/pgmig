-- Functions and procedures (excluding aggregates, window functions, and extension-owned ones).
SELECT
    n.nspname,
    p.proname,
    pg_get_function_identity_arguments(p.oid),
    pg_get_functiondef(p.oid),
    format_type(p.prorettype, NULL),
    p.prokind,
    obj_description(p.oid, 'pg_proc')
FROM
    pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE
    p.prokind IN ('f', 'p')
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = p.oid
            AND d.deptype = 'e');
