/*
    The archive schema the staging archive step renames tables into.

    From this change on, the archive is a *rename*, not a copy. At the end of a
    customer's migration each staging table is renamed to <EntityCode>_<table>,
    transferred into this schema, and rebuilt empty from its own schema file -
    all in one transaction. Renaming is a catalog operation, so it costs the same
    whether the table holds ten rows or ten million, and it works identically on
    Azure SQL and on a normal instance. See staging_archive.StagingRenamer.

        dbo.RC_ACCOUNT_EXTRACT  ->  archive.SM9641_RC_ACCOUNT_EXTRACT

    A rename cannot cross databases, so these tables live in the environment's
    own DATABASE rather than in ARCHIVE_DATABASE. tools/sweep_archive.py moves
    them on to ARCHIVE_DATABASE afterwards, out of band - nothing in a migration
    run waits for it. Until it has, the tables here are the ONLY copy of that
    customer's extract: see ArchiveCatalog.SweptTS below.

    Because the archive now accumulates inside the application database, watch
    its size. SQL/Schemas/Migrations/004.migration_data_archive.sql covers the
    database the sweep targets.

    Run once per environment, before the first migration that archives:

        python tools/deploy_schemas.py <env> --set migrations
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

/* CREATE SCHEMA must be the first statement in its batch, hence the EXEC. */
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'archive')
BEGIN
    EXEC (N'CREATE SCHEMA [archive]');
    PRINT 'Created schema archive';
END
ELSE
    PRINT 'Schema archive already present';
GO

/*
    One row per archived table.

    The audit values that used to be columns on every archived row - LoadID,
    CreateTS, EntityCode - live here instead. They cannot be columns any more:
    adding a column to a renamed table means ALTER TABLE ADD, and an
    nvarchar NOT NULL DEFAULT is not a metadata-only operation - it rewrites the
    table, which would cost exactly what the rename was meant to avoid.

    One row per table beats three columns per row on 25 tables per customer, and
    it is what tools/sweep_archive.py drives off.
*/
IF NOT EXISTS (SELECT 1 FROM sys.tables t
               JOIN sys.schemas s ON s.schema_id = t.schema_id
               WHERE s.name = N'archive' AND t.name = N'ArchiveCatalog')
BEGIN
    CREATE TABLE archive.ArchiveCatalog (
        -- SM9641_RC_ACCOUNT_EXTRACT. One archived table, one row, so this is
        -- the key: re-archiving a customer replaces both table and row.
        ArchiveTable  NVARCHAR(128) NOT NULL,
        StagingTable  NVARCHAR(128) NOT NULL,   -- RC_ACCOUNT_EXTRACT
        EntityCode    NVARCHAR(200) NOT NULL,   -- SM9641
        LoadID        INT           NULL,
        CreateTS      DATETIME2(3)  NOT NULL,
        -- Read from sys.dm_db_partition_stats before the rename: the table is
        -- quiescent at that point, so it is exact, and it costs no scan.
        RowsArchived  BIGINT        NULL,
        SessionID     INT           NULL,
        RunID         NVARCHAR(100) NULL,
        SourceDb      NVARCHAR(100) NULL,       -- the extract's source, e.g. SMAUS
        -- NULL until tools/sweep_archive.py has copied this table to
        -- ARCHIVE_DATABASE and reconciled its row count. While it is NULL the
        -- table here is the only copy, and nothing may drop it - see
        -- tools/setup_archive.py, which refuses to.
        SweptTS       DATETIME2(3)  NULL,
        CONSTRAINT PK_ArchiveCatalog PRIMARY KEY CLUSTERED (ArchiveTable)
    );
    CREATE NONCLUSTERED INDEX IX_ArchiveCatalog_Swept
        ON archive.ArchiveCatalog (SweptTS, CreateTS)
        INCLUDE (StagingTable, EntityCode, RowsArchived);
    PRINT 'Created archive.ArchiveCatalog';
END
ELSE
    PRINT 'archive.ArchiveCatalog already present';
GO

/*
    What the archive currently holds, and how much of it has not been swept.

        SELECT * FROM archive.vw_ArchiveSize ORDER BY MB DESC;
*/
CREATE OR ALTER VIEW archive.vw_ArchiveSize
AS
SELECT  c.ArchiveTable,
        c.EntityCode,
        c.StagingTable,
        c.CreateTS,
        c.SweptTS,
        c.RowsArchived,
        CAST(SUM(p.used_page_count) * 8.0 / 1024 AS DECIMAL(18, 2)) AS MB
FROM    archive.ArchiveCatalog AS c
JOIN    sys.tables  AS t ON t.name = c.ArchiveTable
JOIN    sys.schemas AS s ON s.schema_id = t.schema_id AND s.name = N'archive'
JOIN    sys.dm_db_partition_stats AS p ON p.object_id = t.object_id
GROUP BY c.ArchiveTable, c.EntityCode, c.StagingTable, c.CreateTS, c.SweptTS,
         c.RowsArchived;
GO
