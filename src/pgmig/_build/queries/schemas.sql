-- Schemas (user namespaces, excluding system and extension-owned ones).
SELECT
    n.nspname AS schema_name,
    obj_description(n.oid, 'pg_namespace') AS schema_comment
FROM
    pg_namespace n
WHERE
    n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = n.oid
            AND d.deptype = 'e')
ORDER BY
    n.nspname;
