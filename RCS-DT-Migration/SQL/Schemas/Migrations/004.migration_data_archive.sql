/*
    The archive database the staging archive step writes to.

    Each environment names its own, in ARCHIVE_DATABASE in its config/<env>.env:

        testse   test-migration-data   on debtrak-test-sql (test-debtrak)
        uat      dev-migration-data    on debtrak-dev-sql  (dev-debtrak)
        dev/v10  migration_data        alongside the environment's own database

    <archive-db> below means whichever of those you are setting up. It always
    lives on the same server as that environment's DATABASE.

    Setting the archive up is two steps, both run ONCE per environment and
    neither run by Run_Migration.py:

      1. this script - the database and the migration account's access to it.
         Needs privileges the migration's own service principal does not have
         and does not need.
      2. python tools/setup_archive.py <env> - the RC_* tables inside it,
         generated from the staging tables plus the LoadID / CreateTS /
         EntityCode audit columns. Connects as the migration account.

    A migration run only inserts rows into what step 2 created; it issues no DDL
    against this database, and fails the customer if a table is missing. So run
    step 2 again after a staging schema change adds a column, not per load.

    Run the section below for your target, then:

        python tools/setup_archive.py <env> --dry-run   -- what it would create
        python tools/setup_archive.py <env>             -- create it
        python tools/archive_staging.py <env> --dry-run -- what a run would copy

    On Azure SQL every database is its own security boundary: a principal with
    access to test-debtrak has none to test-migration-data until it is given a
    user there. The server firewall is shared, though, so no new firewall rule
    is needed for a database on a server you already reach.
*/

/* ==========================================================================
   1. AZURE SQL (testse, uat) — create the database
   ==========================================================================

   Connect to *master* on the logical server as an Entra admin, or use the
   portal / az CLI. T-SQL, testse's name shown:

        CREATE DATABASE [test-migration-data]
            (EDITION = 'Standard', SERVICE_OBJECTIVE = 'S1');

   In an elastic pool instead:

        CREATE DATABASE [test-migration-data]
            (SERVICE_OBJECTIVE = ELASTIC_POOL(name = <pool-name>));

   az CLI equivalent:

        az sql db create -g <resource-group> -s debtrak-test-sql \
            -n test-migration-data --edition Standard --service-objective S1

   For uat that is [dev-migration-data] on debtrak-dev-sql.

   Size it for what is kept: the archive accumulates one copy of every
   customer's extract per load and is never truncated by the migration.
*/

/* ==========================================================================
   2. AZURE SQL — give the migration's service principal access
   ==========================================================================

   Connect to *<archive-db>* (not master) as a Microsoft Entra admin. SQL
   authentication cannot create Entra users, however high its privileges.

   testse: the principal is sp-debtrak-se-test
           (CLIENT_ID 2ff8edf0-dccb-4148-a649-2c1154e1e129), which is a
           contained user with db_owner in test-debtrak today. Mirror that:

        CREATE USER [sp-debtrak-se-test] FROM EXTERNAL PROVIDER;
        ALTER ROLE db_owner ADD MEMBER [sp-debtrak-se-test];

   uat:    same shape, for the principal behind
           CLIENT_ID fa499e81-2dcc-46d1-b53b-527703b420ae. Get its display name
           from the app registration, or from the existing user in dev-debtrak:

        SELECT name, CONVERT(VARCHAR(200), sid, 1) AS sid_hex
        FROM sys.database_principals WHERE type = 'E' ORDER BY name;

   FROM EXTERNAL PROVIDER makes the SQL server look the name up in Microsoft
   Graph, which only works when the server's managed identity holds the
   Directory Readers role. If it does not, the error is

        Principal '<name>' could not be resolved / Msg 33134

   and the way through is to give the SID explicitly - no Graph lookup, same
   resulting user. The SID is the client id as a byte-swapped GUID:

        -- testse: 2ff8edf0-dccb-4148-a649-2c1154e1e129
        CREATE USER [sp-debtrak-se-test]
            WITH SID = 0xF0EDF82FCBDC4841A6492C1154E1E129, TYPE = E;
        ALTER ROLE db_owner ADD MEMBER [sp-debtrak-se-test];

        -- uat: fa499e81-2dcc-46d1-b53b-527703b420ae
        CREATE USER [<uat-principal-display-name>]
            WITH SID = 0x819E49FACC2DD146B53B527703B420AE, TYPE = E;
        ALTER ROLE db_owner ADD MEMBER [<uat-principal-display-name>];

   (First three GUID fields reverse byte order, the last eight bytes do not:
    2ff8edf0 -> F0EDF82F, dccb -> CBDC, 4148 -> 4841, then a6492c1154e1e129.)

   db_owner matches how the principal is set up in test-debtrak. The step needs
   less than that, if this database is shared with anything else:

        ALTER ROLE db_ddladmin   ADD MEMBER [<principal>];  -- setup_archive.py
        ALTER ROLE db_datawriter ADD MEMBER [<principal>];  -- INSERT
        ALTER ROLE db_datareader ADD MEMBER [<principal>];  -- the duplicate guard

   Only setup_archive.py needs db_ddladmin. An environment whose archive tables
   already exist runs the migration on the two data roles alone, if you would
   rather drop it again afterwards.

   Azure SQL has no cross-database queries, so on these environments the step
   streams rows through the client. Both connections use the same service
   principal, so nothing further is needed to make that work.
*/

/* ==========================================================================
   3. SQL SERVER (dev, v10)
   ==========================================================================

   Same instance, so the step copies with a cross-database INSERT ... SELECT and
   never moves data through the client.

        CREATE DATABASE [migration_data];      -- ARCHIVE_DATABASE for this env
        GO

        USE [migration_data];
        GO

        -- Windows authentication: the account that runs the migration.
        CREATE USER [<DOMAIN\account>] FOR LOGIN [<DOMAIN\account>];
        ALTER ROLE db_ddladmin   ADD MEMBER [<DOMAIN\account>];
        ALTER ROLE db_datawriter ADD MEMBER [<DOMAIN\account>];
        ALTER ROLE db_datareader ADD MEMBER [<DOMAIN\account>];
        GO
*/

/* ==========================================================================
   4. Naming
   ==========================================================================
   The name comes from ARCHIVE_DATABASE in that environment's config/<env>.env,
   and must be on the same server as DATABASE. Every env file sets it; an env
   file that does not falls back to 'migration_data' (DEFAULT_ARCHIVE_DATABASE
   in db_manager.py), which on an environment that names its archive something
   else means the archive step reports a missing table for a database that was
   never the target.
*/
