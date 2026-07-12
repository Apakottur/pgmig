-- Sequences (standalone only; sequences owned by a serial/identity column are excluded).
SELECT
    n.nspname,
    c.relname,
    format_type(s.seqtypid, NULL),
    s.seqstart,
    s.seqincrement,
    s.seqmin,
    s.seqmax,
    s.seqcache,
    s.seqcycle
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
            AND d.deptype IN ('a', 'i'));
