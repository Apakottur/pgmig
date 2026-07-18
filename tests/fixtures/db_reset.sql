-- Reset a database to the state of a freshly created one.
DO $$
DECLARE
    entry record;
BEGIN
    -- Clear per-database settings a test may have pinned (e.g. ALTER DATABASE ... SET search_path).
    EXECUTE format('ALTER DATABASE %I RESET ALL', current_database());
    -- Clear ALTER DEFAULT PRIVILEGES rules (pg_default_acl): a fresh database has none, and a
    -- lingering rule holds a shared dependency on its FOR ROLE role that blocks dropping that
    -- role in a later test. DROP OWNED BY removes a role's default-acl entries (and anything it
    -- owns) in the current database. The connection role is skipped -- dropping what it owns
    -- would take the public schema recreated below with it.
    FOR entry IN SELECT DISTINCT
        defaclrole
    FROM
        pg_default_acl
    WHERE
        defaclrole <> CURRENT_USER::regrole LOOP
            EXECUTE format('DROP OWNED BY %s', entry.defaclrole::regrole);
        END LOOP;
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
