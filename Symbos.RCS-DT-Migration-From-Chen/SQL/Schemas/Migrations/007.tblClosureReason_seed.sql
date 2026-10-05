/*
    tblClosureReason - the labels variables/closure_reason_codes.json maps to.

    NOT run by Run_Migration.py. Safe to run top to bottom on any environment:
    a label already present (compared trimmed, in the column's own collation) is
    skipped, so a second run inserts nothing.

    The closure reason workflow rewrites RC_ACCOUNT_EXTRACT.Reason_Closed to a
    tblClosureReason label and sweeps anything it cannot resolve to
    'Other Reason - Please see notes'. A mapping whose target label is missing
    here would silently fall into that sweep, so every label the JSON maps to
    must exist first.

    Audit columns copy the original 2012 seed rows (CreateID/ModifyID 1,
    session 1, StatusID 1). DisplayOrder and ClientCode take the table defaults.

    Measured 2026-09-24, uat / dev-debtrak: ids 1-7 present; Paid In Full,
    Deceased, Settled For Less and Loaded In Error were missing.
*/

SET NOCOUNT ON;

DECLARE @Wanted TABLE (ClosureReason NVARCHAR(255) NOT NULL);
INSERT INTO @Wanted (ClosureReason)
VALUES  (N'Paid In Full'),
        (N'Other Reason - Please see notes'),
        (N'Client Instructions'),
        (N'Deceased'),
        (N'Bankrupt/NAP or Liquidation'),
        (N'Settled For Less'),
        (N'Uneconomical to pursue'),
        (N'Loaded In Error');

BEGIN TRANSACTION;

INSERT INTO dbo.tblClosureReason
            (ClosureReason, CreateID, CreateSessionID, CreateTS,
             ModifyID, ModifySessionID, ModifyTS, StatusID)
OUTPUT      inserted.ClosureReasonID, inserted.ClosureReason
SELECT      w.ClosureReason, 1, 1, GETDATE(), 1, 1, GETDATE(), 1
FROM        @Wanted w
WHERE       NOT EXISTS (
                SELECT 1
                FROM   dbo.tblClosureReason cr
                WHERE  LTRIM(RTRIM(cr.ClosureReason)) = w.ClosureReason
            );

COMMIT TRANSACTION;

SELECT      ClosureReasonID, ClosureReason, InactiveTS
FROM        dbo.tblClosureReason
ORDER BY    ClosureReasonID;
