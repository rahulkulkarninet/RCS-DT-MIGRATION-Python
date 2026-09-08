

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = N'DT_Migration_LoopProgress')
BEGIN
    CREATE TABLE dbo.DT_Migration_LoopProgress (
        LoadID      INT           NOT NULL,
        StageName   VARCHAR(50)   NOT NULL,
        LastKey1    INT           NULL,        -- e.g. AccountID
        LastKey2    INT           NULL,        -- e.g. ContactID, for composite drivers
        RowsDone    BIGINT        NOT NULL CONSTRAINT DF_LoopProgress_RowsDone DEFAULT 0,
        UpdatedUTC  DATETIME2(3)  NOT NULL
            CONSTRAINT DF_LoopProgress_UpdatedUTC DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_DT_Migration_LoopProgress PRIMARY KEY CLUSTERED (LoadID, StageName)
    );
    PRINT 'Created dbo.DT_Migration_LoopProgress';
END
ELSE
    PRINT 'dbo.DT_Migration_LoopProgress already present';
GO

/*
    Stage names written by SQL/Migration queries/Loop/76.final loops and sps to run.sql:

      correspondence_recalc  loop 5, spAccount_Contact_CorrespondenceRecalculate,
                             driver tblAccount_Contact, key (AccountID, ContactID)
      account_totals         loop 6, spAccountCalculateTotals,
                             driver tblAccount, key AccountID

    Loops 1-4 are not yet instrumented: they are TVF inserts rather than per-row
    stored-procedure calls, so they cost far less at volume, and Tier B of
    docs/file-76-scaling-approach.md would replace two of them with set-based
    statements outright.

    To re-run a load from the beginning, delete its rows here:
        DELETE FROM dbo.DT_Migration_LoopProgress WHERE LoadID = <id>;
    Note that only makes the loops re-run; it does not undo what they already did.
    Use tools/discard_load.py to remove the data itself.
*/
