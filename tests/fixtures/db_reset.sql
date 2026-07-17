-- Reset a database to the state of a freshly created one.
DO $$
DECLARE
    entry record;
BEGIN
    -- Clear per-database settings a test may have pinned (e.g. ALTER DATABASE ... SET search_path).
    EXECUTE format('ALTER DATABASE %I RESET ALL', current_database());
    -- Drop extensions before schemas: an extension living in a custom schema blocks
    -- DROP SCHEMA on that schema until the extension itself is gone.
    FOR entry IN
    SELECT
        extname
    FROM
        pg_extension
    WHERE
        extname <> 'plpgsql' LOOP
            EXECUTE format('DROP EXTENSION %I CASCADE', entry.extname);
        END LOOP;
    -- Drop every non-system schema; CASCADE removes the objects inside them.
    FOR entry IN
    SELECT
        nspname
    FROM
        pg_namespace
    WHERE
        nspname NOT LIKE 'pg_%'
        AND nspname NOT IN ('information_schema', 'public')
        LOOP
            EXECUTE format('DROP SCHEMA %I CASCADE', entry.nspname);
        END LOOP;
END
$$;

-- Recreate a pristine public schema, matching a freshly created database (including the
-- default comment, whose absence would otherwise show up as a diff).
DROP SCHEMA public CASCADE;

CREATE SCHEMA public;

COMMENT ON SCHEMA public IS 'standard public schema';
