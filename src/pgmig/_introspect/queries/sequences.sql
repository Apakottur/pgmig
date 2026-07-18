-- Sequences (the backing sequence of a serial/identity column is excluded; a manually
-- created sequence with OWNED BY is kept and its owner surfaced in owned_* below).
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
    c.relpersistence AS seq_persistence,
    obj_description(c.oid, 'pg_class') AS seq_comment,
    pg_get_userbyid(c.relowner) AS seq_owner,
    -- Manual OWNED BY target (deptype 'a' to a column). NULL for a truly standalone
    -- sequence. A serial/identity backing sequence carries the same 'a'/'i' dependency but
    -- is excluded entirely by the WHERE clause below, so any row that reaches here with an
    -- 'a' dependency is a manual OWNED BY.
    owned_n.nspname AS owned_schema,
    owned_c.relname AS owned_table,
    owned_a.attname AS owned_column
FROM
    pg_sequence s
    JOIN pg_class c ON c.oid = s.seqrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_depend owned_d ON owned_d.classid = 'pg_class'::regclass
        AND owned_d.objid = c.oid
        AND owned_d.refclassid = 'pg_class'::regclass
        AND owned_d.deptype = 'a'
    LEFT JOIN pg_class owned_c ON owned_c.oid = owned_d.refobjid
    LEFT JOIN pg_namespace owned_n ON owned_n.oid = owned_c.relnamespace
    LEFT JOIN pg_attribute owned_a ON owned_a.attrelid = owned_d.refobjid
        AND owned_a.attnum = owned_d.refobjsubid
WHERE
    n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors / re-emits an object whose
    -- owner was dropped):
    --   [x] namespace leg  -- sequence in an extension-owned schema (n.oid)
    --   [x] self leg       -- the sequence itself is extension-owned (c.oid)
    --   [ ] owning-table leg -- n/a; a sequence backing a serial/identity column is
    --                           excluded separately below
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
            d.objid = c.oid
            AND d.deptype = 'e')
    -- Exclude only a sequence whose lifecycle belongs to the column that owns it -- the
    -- table layer emits it inline (serial / GENERATED AS IDENTITY):
    --   deptype 'i'  -- an identity column's internal sequence.
    --   deptype 'a'  -- an auto-owned sequence whose owning column is either:
    --       * a serial column: its default is a nextval() on this very sequence
    --         (matched via pg_attrdef); or
    --       * an identity column (attidentity <> ''): the identity manages its own
    --         sequence, and a serial->identity conversion leaves the old serial sequence
    --         'a'-owned by the now-identity column -- an unused orphan that must stay
    --         excluded, or the migration would not converge.
    --     A manual OWNED BY on a plain column carries the same 'a' dependency but neither
    --     of these holds, so it is kept and introspected.
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
            JOIN pg_attribute col ON col.attrelid = d.refobjid
                AND col.attnum = d.refobjsubid
        WHERE
            d.classid = 'pg_class'::regclass
            AND d.objid = c.oid
            AND d.refclassid = 'pg_class'::regclass
            AND (d.deptype = 'i'
                OR (d.deptype = 'a'
                    AND (col.attidentity <> ''
                        OR EXISTS (
                            SELECT
                                1
                            FROM
                                pg_attrdef ad
                                JOIN pg_depend dd ON dd.classid = 'pg_attrdef'::regclass
                                    AND dd.objid = ad.oid
                                    AND dd.refclassid = 'pg_class'::regclass
                                    AND dd.refobjid = c.oid
                            WHERE
                                ad.adrelid = d.refobjid
                                AND ad.adnum = d.refobjsubid)))))
    ORDER BY
        n.nspname,
        c.relname;
