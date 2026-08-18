/*
    RC_Processing_Stats — add run identity. ADDITIVE ONLY.

    This table is append-only history (see CLAUDE.md). Nothing here drops,
    truncates or deletes anything, and the script is safe to run repeatedly.

    Do NOT use "SQL/Schemas/RC_Processing_Stats Schema.sql" against a populated
    database: that script begins with DROP TABLE and would destroy the history.

    Why:
      - RunID makes a re-run after a partial failure distinguishable from the
        original attempt, instead of indistinguishable duplicate noise.
      - The filtered unique index makes a duplicate write FAIL LOUDLY rather than
        silently polluting permanent history. It is filtered on RunID IS NOT NULL
        so existing rows, which predate RunID, are unaffected.
      - History tables get queried, so an index for the common access path.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

/* ---- 1. RunID -------------------------------------------------------- */
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID(N'[dbo].[RC_Processing_Stats]')
                 AND name = N'RunID')
BEGIN
    ALTER TABLE dbo.RC_Processing_Stats ADD RunID UNIQUEIDENTIFIER NULL;
    PRINT 'Added RC_Processing_Stats.RunID';
END
ELSE
    PRINT 'RC_Processing_Stats.RunID already present';
GO

/* ---- 2. Row_Inserted_UTC -------------------------------------------- */
/* Created_Date is local (AUS Eastern); a UTC stamp makes ordering across
   daylight-saving boundaries unambiguous. */
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID(N'[dbo].[RC_Processing_Stats]')
                 AND name = N'Row_Inserted_UTC')
BEGIN
    ALTER TABLE dbo.RC_Processing_Stats
        ADD Row_Inserted_UTC DATETIME2(3) NULL
            CONSTRAINT DF_RC_Processing_Stats_Row_Inserted_UTC DEFAULT SYSUTCDATETIME();
    PRINT 'Added RC_Processing_Stats.Row_Inserted_UTC';
END
ELSE
    PRINT 'RC_Processing_Stats.Row_Inserted_UTC already present';
GO

/* ---- 3. Make a duplicate write fail loudly -------------------------- */
/* One row per (run, staging load, customer, db, table). Filtered so the
   pre-RunID rows are exempt. If this index cannot be created, duplicates
   already exist for the same RunID and must be reviewed before enforcing. */
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID(N'[dbo].[RC_Processing_Stats]')
                 AND name = N'UX_RC_Processing_Stats_Row')
BEGIN
    BEGIN TRY
        CREATE UNIQUE NONCLUSTERED INDEX UX_RC_Processing_Stats_Row
            ON dbo.RC_Processing_Stats
               (RunID, Staging_LoadID, Customer_Code, db, Table_Name)
            WHERE RunID IS NOT NULL;
        PRINT 'Created UX_RC_Processing_Stats_Row';
    END TRY
    BEGIN CATCH
        PRINT 'Could not create UX_RC_Processing_Stats_Row: ' + ERROR_MESSAGE();
        PRINT 'Existing rows with a RunID are not unique on '
            + '(RunID, Staging_LoadID, Customer_Code, db, Table_Name). '
            + 'Review them before enforcing uniqueness. Nothing was deleted.';
    END CATCH
END
ELSE
    PRINT 'UX_RC_Processing_Stats_Row already present';
GO

/* ---- 4. Index for historical analysis ------------------------------- */
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID(N'[dbo].[RC_Processing_Stats]')
                 AND name = N'IX_RC_Processing_Stats_Customer_Db_Start')
BEGIN
    CREATE NONCLUSTERED INDEX IX_RC_Processing_Stats_Customer_Db_Start
        ON dbo.RC_Processing_Stats (Customer_Code, db, Start_Time);
    PRINT 'Created IX_RC_Processing_Stats_Customer_Db_Start';
END
ELSE
    PRINT 'IX_RC_Processing_Stats_Customer_Db_Start already present';
GO
