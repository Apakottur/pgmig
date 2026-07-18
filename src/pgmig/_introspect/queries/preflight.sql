-- Presence probe: one cheap row of booleans reporting which object classes the database
-- actually contains, so introspect_db can skip the (planning-heavy) loader query for any
-- class that is absent -- a large win on the small databases typical of a test suite.
--
-- Deliberately lenient: it omits the extension-ownership and serial/identity refinements the
-- loaders apply, so it may report a class present when the loader ultimately finds nothing.
-- That only costs a redundant loader run; it must never report a present class as absent
-- (that would silently drop objects), so every leg is a strict superset of its loader filter.
SELECT
    EXISTS (
        SELECT
            1
        FROM
            pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE
            c.relkind IN ('r', 'p')
            AND n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema') AS has_tables,
    EXISTS (
        SELECT
            1
        FROM
            pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE
            c.relkind = 'v'
            AND n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema') AS has_views,
    EXISTS (
        SELECT
            1
        FROM
            pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE
            c.relkind = 'm'
            AND n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema') AS has_matviews,
    EXISTS (
        SELECT
            1
        FROM
            pg_index i
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE
            c.relkind IN ('r', 'p')
            AND n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema') AS has_indexes,
    EXISTS (
        SELECT
            1
        FROM
            pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE
            con.contype IN ('p', 'u', 'c', 'f', 'x')
            AND c.relkind IN ('r', 'p')
            AND n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema') AS has_constraints,
    EXISTS (
        SELECT
            1
        FROM
            pg_sequence s
            JOIN pg_class c ON c.oid = s.seqrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE
            n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema') AS has_sequences,
    EXISTS (
        SELECT
            1
        FROM
            pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE
            p.prokind IN ('f', 'p')
            AND n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema') AS has_functions,
    EXISTS (
        SELECT
            1
        FROM
            pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE
            NOT t.tgisinternal
            -- Tables ('r'/'p') and views ('v', INSTEAD OF triggers); matches triggers.sql.
            AND c.relkind IN ('r', 'p', 'v')
            AND n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema') AS has_triggers,
    EXISTS (
        SELECT
            1
        FROM
            pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE
            t.typtype = 'e'
            AND n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema') AS has_enums,
    EXISTS (
        SELECT
            1
        FROM
            pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE
            t.typtype = 'd'
            AND n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema') AS has_domains,
    EXISTS (
        SELECT
            1
        FROM
            pg_type t
            JOIN pg_class c ON c.oid = t.typrelid
            JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE
            t.typtype = 'c'
            AND c.relkind = 'c'
            AND n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema') AS has_composite_types;
