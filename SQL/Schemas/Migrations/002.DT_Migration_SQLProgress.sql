/*
    DT_Migration_SQLProgress — checkpoint for the numbered migration SQL files.
    ADDITIVE ONLY, and safe to run repeatedly.

    Files 1-75 now commit one transaction per file, and the checkpoint row for a
    file is written inside that same transaction. So a row here means the file's
    work is durably committed, and the absence of a row means it is not — the two
    can never disagree.

    That is what makes `Run_Migration.py <env> --resume-load-id N` safe: it skips
    exactly the files recorded here and re-runs the rest.

    Keyed on Filename, NOT Sequence. Sequence is not unique: sequences 6/7/8 fan
    out to one file per metafield, and sequence 35 exists twice
    (35.Update_tblAccount_name and 35.tblcontactdetail_create_email_insurance).
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = N'DT_Migration_SQLProgress')
BEGIN
    CREATE TABLE dbo.DT_Migration_SQLProgress (
        LoadID        INT              NOT NULL,
        Customer_Code NVARCHAR(50)     NULL,
        db            NVARCHAR(100)    NULL,
        RunID         UNIQUEIDENTIFIER NULL,
        [Sequence]    INT              NOT NULL,
        Filename      NVARCHAR(400)    NOT NULL,
        Table_Name    NVARCHAR(255)    NULL,
        Rows_Affected BIGINT           NULL,
        Completed_UTC DATETIME2(3)     NOT NULL
            CONSTRAINT DF_DT_Migration_SQLProgress_Completed DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_DT_Migration_SQLProgress PRIMARY KEY CLUSTERED (LoadID, Filename)
    );
    PRINT 'Created dbo.DT_Migration_SQLProgress';
END
ELSE
    PRINT 'dbo.DT_Migration_SQLProgress already present';
GO

/* Resume reads by LoadID; the PK already covers that. This supports reporting
   across loads for one customer. */
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID(N'[dbo].[DT_Migration_SQLProgress]')
                 AND name = N'IX_DT_Migration_SQLProgress_Customer')
BEGIN
    CREATE NONCLUSTERED INDEX IX_DT_Migration_SQLProgress_Customer
        ON dbo.DT_Migration_SQLProgress (Customer_Code, db, Completed_UTC);
    PRINT 'Created IX_DT_Migration_SQLProgress_Customer';
END
ELSE
    PRINT 'IX_DT_Migration_SQLProgress_Customer already present';
GO
