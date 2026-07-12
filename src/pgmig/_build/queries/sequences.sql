-- Sequences (standalone only; sequences owned by a serial/identity column are excluded).
SELECT
    n.nspname AS schema_name,
    c.relname AS seq_name,
    format_type(s.seqtypid, NULL) AS seq_type,
    s.seqstart AS seq_start,
    s.seqincrement AS seq_inc,
    s.seqmin AS seq_min,
    s.seqmax AS seq_max,
    s.seqcache AS seq_cache,
    s.seqcycle AS seq_cycle,
    obj_description(c.oid, 'pg_class') AS seq_comment
FROM
    pg_sequence s
    JOIN pg_class c ON c.oid = s.seqrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
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
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.classid = 'pg_class'::regclass
            AND d.objid = c.oid
            AND d.refclassid = 'pg_class'::regclass
            AND d.deptype IN ('a', 'i'))
ORDER BY
    n.nspname,
    c.relname;
