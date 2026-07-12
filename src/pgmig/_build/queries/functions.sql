-- Functions and procedures (excluding aggregates, window functions, and extension-owned ones).
SELECT
    n.nspname AS schema_name,
    p.proname AS func_name,
    pg_get_function_identity_arguments(p.oid) AS func_args,
    pg_get_functiondef(p.oid) AS func_def,
    format_type(p.prorettype, NULL) AS func_rettype,
    p.prokind AS func_kind,
    obj_description(p.oid, 'pg_proc') AS func_comment,
    EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.refclassid = 'pg_proc'::regclass
            AND d.refobjid = p.oid
            AND d.deptype IN ('n', 'a')
            AND d.classid <> 'pg_trigger'::regclass) AS func_has_dependents
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
