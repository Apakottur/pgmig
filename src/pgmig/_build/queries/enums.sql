-- Enum types (user enums only; extension-owned ones are excluded).
SELECT
    n.nspname AS schema_name,
    t.typname AS enum_name,
    array_agg(e.enumlabel ORDER BY e.enumsortorder) AS enum_values,
    obj_description(t.oid, 'pg_type') AS enum_comment
FROM
    pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    JOIN pg_enum e ON e.enumtypid = t.oid
WHERE
    t.typtype = 'e'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = t.oid
            AND d.deptype = 'e')
GROUP BY
    n.nspname,
    t.oid,
    t.typname
ORDER BY
    n.nspname,
    t.typname;
