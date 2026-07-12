-- Schemas (user namespaces, excluding system and extension-owned ones).
SELECT
    n.nspname,
    obj_description(n.oid, 'pg_namespace')
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
            AND d.deptype = 'e');
