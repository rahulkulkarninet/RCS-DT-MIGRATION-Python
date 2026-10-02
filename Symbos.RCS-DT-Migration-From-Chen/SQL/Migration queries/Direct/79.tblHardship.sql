-- Z_REF carries HS.Extended_Debt_Code, the same way Z_REF/Z_ID carry the source key on
-- tblPayment/tblSMSOutput/tblComplaint elsewhere in this folder, so the child inserts
-- below can re-join the row just inserted.
--
-- Status and Hardship_Cause are normalized to tblHardshipStatus.HardshipStatus and
-- tblHardshipCause.HardshipCause in place, before this file runs, by
-- update_hardship_statuses/update_hardship_causes (see hardship_status_service.py/
-- hardship_cause_service.py and variables/hardship_status_codes.json,
-- variables/hardship_cause_codes.json) - the same mechanism RC_ACCOUNT_EXTRACT.MA_Status
-- and .Reason_Closed go through. Hardship_Cause is a raw tblHardshipCause.HardshipCauseID
-- in this customer's extract; the Python step resolves that to the canonical label the
-- same way it would resolve a text value. A value with no mapping and no configured
-- default is left as-is and reported invalid rather than guessed at here.
--
-- Withdrawn_Reason, Waiver_Status and Declined_Reason are matched directly against their
-- lookup tables via OUTER APPLY (no Python normalization step): all three are optional,
-- populated only for the subset of rows that were withdrawn/waived/declined, unlike
-- Status and Hardship_Cause which apply to every row.
--
-- ClientCode is a literal 'RCS', not HS.Client_Code: confirmed 2026-09-18 for the Treatment
-- domain by pulling the live app's own query out of Query Store - it scopes by the shared
-- 'RCS' tenant, not the account's own operating client - and Chen's Complaint migration
-- independently uses the same literal 'RCS'. Not independently confirmed for Hardship via a
-- live capture the way Treatment was, but applied here on the strength of that pattern.
--
-- Preferred_Hardship_Contact_Method is not migrated: dev-debtrak's tblHardship has no
-- CommunicationPreferenceID column (checked 2026-09-29), so there is nowhere to put it.
INSERT  INTO tblHardship WITH ( ROWLOCK )
        ( AccountId ,
          TriggerDate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          HarshipStatusID ,
          HardshipCauseID ,
          HardshipCauseOther ,
          HardshipWithdrawStatusIID ,
          HardshipWithdrawDate ,
          DebtWaiverRequested ,
          DebtWaiverAmount ,
          HardshipWaiverStatusID ,
          HardshipDeclinedStatusID ,
          ApproveDate ,
          EndDate ,
          HoldStartDate ,
          HoldEndDate ,
          ReviewDate ,
          ClientCode ,
          Z_REF
        )
        SELECT  A.AccountID ,
                HS.HS_Date_Triggered ,
                1 ,
                {{CurrentSessionID}} ,
                HS.Date_Entered ,
                1 ,
                STAT.HardshipStatusID ,
                CAUSE.HardshipCauseID ,
                HS.Other_Cause ,
                WITHDRAWN.HardshipWithdrawStatusID ,
                HS.Withdrawn_Date ,
                CASE HS.Waiver_Requested WHEN 'Yes' THEN 1 WHEN 'No' THEN 0 END ,
                CASE WHEN HS.Waiver_Amount IS NULL OR LTRIM(RTRIM(HS.Waiver_Amount)) = '' THEN NULL
                     ELSE TRY_CAST(REPLACE(REPLACE(HS.Waiver_Amount, '$', ''), ',', '') AS DECIMAL(18,2)) END ,
                WAIVER.HardshipWaiverStatusID ,
                DECLINED.HardshipDeclinedStatusID ,
                HS.Approved_Date ,
                HS.Declined_Date ,
                HS.Moratorium_Start ,
                HS.Moratorium_End ,
                HS.Review_Date ,
                'RCS' ,
                CAST(HS.Extended_Debt_Code AS NVARCHAR(40))
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                -- OUTER APPLY TOP 1, not a plain JOIN: defensive against a lookup table
                -- carrying more than one row per label, the same reason 01.tblaccount.sql
                -- uses this pattern for tblProduct and 77.tblComplaint.sql uses it throughout.
                OUTER APPLY ( SELECT TOP 1 HardshipStatusID
                              FROM   tblHardshipStatus
                              WHERE  HardshipStatus = HS.Status
                              ORDER BY HardshipStatusID
                            ) STAT
                OUTER APPLY ( SELECT TOP 1 HardshipCauseID
                              FROM   tblHardshipCause
                              WHERE  HardshipCause = HS.Hardship_Cause
                              ORDER BY HardshipCauseID
                            ) CAUSE
                OUTER APPLY ( SELECT TOP 1 HardshipWithdrawStatusID
                              FROM   tblHardshipWithdrawStatus
                              WHERE  HardshipWithdrawStatus = HS.Withdrawn_Reason
                              ORDER BY HardshipWithdrawStatusID
                            ) WITHDRAWN
                OUTER APPLY ( SELECT TOP 1 HardshipWaiverStatusID
                              FROM   tblHardshipWaiverStatus
                              WHERE  HardshipWaiverStatus = HS.Waiver_Status
                              ORDER BY HardshipWaiverStatusID
                            ) WAIVER
                OUTER APPLY ( SELECT TOP 1 HardshipDeclinedStatusID
                              FROM   tblHardshipDeclinedStatus
                              WHERE  HardshipDeclinedStatus = HS.Declined_Reason
                              ORDER BY HardshipDeclinedStatusID
                            ) DECLINED
        WHERE   A.LoadID = {{LoadID}}
;

-- One tblHardship_CauseSelection row per hardship, matching the resolved HardshipCauseID -
-- this extract carries a single Hardship_Cause value per row, not a multi-select list.
INSERT  INTO tblHardship_CauseSelection WITH ( ROWLOCK )
        ( HardshipID, HardshipCauseID, DisplayOrder, CreateTS, StatusID )
        SELECT  H.HardshipID, CAUSE.HardshipCauseID, 1, GETUTCDATE(), 1
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardship H WITH ( NOLOCK ) ON H.Z_REF = CAST(HS.Extended_Debt_Code AS NVARCHAR(40))
                                                         AND H.AccountId = A.AccountID
                                                         AND H.CreateSessionID = {{CurrentSessionID}}
                CROSS APPLY ( SELECT TOP 1 HardshipCauseID
                              FROM   tblHardshipCause
                              WHERE  HardshipCause = HS.Hardship_Cause
                              ORDER BY HardshipCauseID
                            ) CAUSE
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1 FROM tblHardship_CauseSelection CS WITH ( NOLOCK ) WHERE CS.HardshipID = H.HardshipID )
;

-- One tblHardshipHistory row per '|'-delimited entry in Status_Change_History, paired
-- positionally with the matching entry in Status_Change_Date via STRING_SPLIT's ordinal.
INSERT  INTO tblHardshipHistory WITH ( ROWLOCK )
        ( HardshipID, HardshipStatusID, CreateID, CreateSessionID, CreateTS )
        SELECT  H.HardshipID, STAT.HardshipStatusID, 1, {{CurrentSessionID}}, TRY_CAST(SD.value AS DATETIME)
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardship H WITH ( NOLOCK ) ON H.Z_REF = CAST(HS.Extended_Debt_Code AS NVARCHAR(40))
                                                         AND H.AccountId = A.AccountID
                                                         AND H.CreateSessionID = {{CurrentSessionID}}
                CROSS APPLY STRING_SPLIT(HS.Status_Change_History, '|', 1) SC
                OUTER APPLY ( SELECT value FROM STRING_SPLIT(HS.Status_Change_Date, '|', 1) WHERE ordinal = SC.ordinal ) SD
                OUTER APPLY ( SELECT TOP 1 HardshipStatusID
                              FROM   tblHardshipStatus
                              WHERE  HardshipStatusCode = LTRIM(RTRIM(SC.value))
                              ORDER BY HardshipStatusID
                            ) STAT
        WHERE   A.LoadID = {{LoadID}}
                AND LTRIM(RTRIM(SC.value)) <> ''
                AND NOT EXISTS ( SELECT 1 FROM tblHardshipHistory HH WITH ( NOLOCK ) WHERE HH.HardshipID = H.HardshipID )
;

-- tblHardshipRequest carries the SOFP (statement of financial position) figures. There is
-- no HardshipID FK on this table - it correlates to the account directly, the same way
-- the source extract's SOFP section is keyed by Debt Reference rather than a hardship
-- instance id. Only the income/expense fields with a clean 1:1 or documented-simplification
-- fit (see hardship_system_mapping_updated 1 - COMPLETED.xlsx, SOFP Financial Details /
-- Section A tabs) are populated; itemized assets/liabilities have no destination columns
-- on this table and are deliberately left unmigrated.
INSERT  INTO tblHardshipRequest WITH ( ROWLOCK )
        ( AccountID ,
          WhenFinancialImpact ,
          ShortTerm ,
          Salary ,
          OtherIncome ,
          MortgageOrRent ,
          CouncilRates ,
          TotalUtilitiesBills ,
          TelephoneMobile ,
          Food ,
          OtherExpenses ,
          OtherText ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  A.AccountID ,
                HS.Fin_Diff_Begin ,
                CASE HS.Fin_Diff_Term WHEN 'Short Term' THEN 1 WHEN 'Long Term' THEN 0 END ,
                CASE WHEN HS.Income_1 IS NULL OR LTRIM(RTRIM(HS.Income_1)) = '' THEN NULL
                     ELSE TRY_CAST(REPLACE(REPLACE(HS.Income_1, '$', ''), ',', '') AS DECIMAL(18,2)) END ,
                CASE WHEN HS.Other_Income IS NULL OR LTRIM(RTRIM(HS.Other_Income)) = '' THEN NULL
                     ELSE TRY_CAST(REPLACE(REPLACE(HS.Other_Income, '$', ''), ',', '') AS DECIMAL(18,2)) END ,
                CASE WHEN HS.Rental_Amount IS NULL OR LTRIM(RTRIM(HS.Rental_Amount)) = '' THEN NULL
                     ELSE TRY_CAST(REPLACE(REPLACE(HS.Rental_Amount, '$', ''), ',', '') AS DECIMAL(18,2)) END ,
                CASE WHEN HS.Rates_Amount IS NULL OR LTRIM(RTRIM(HS.Rates_Amount)) = '' THEN NULL
                     ELSE TRY_CAST(REPLACE(REPLACE(HS.Rates_Amount, '$', ''), ',', '') AS DECIMAL(18,2)) END ,
                CASE WHEN HS.Electricity_Water_Gas_Amount IS NULL OR LTRIM(RTRIM(HS.Electricity_Water_Gas_Amount)) = '' THEN NULL
                     ELSE TRY_CAST(REPLACE(REPLACE(HS.Electricity_Water_Gas_Amount, '$', ''), ',', '') AS DECIMAL(18,2)) END ,
                CASE WHEN HS.Phone_Amount IS NULL OR LTRIM(RTRIM(HS.Phone_Amount)) = '' THEN NULL
                     ELSE TRY_CAST(REPLACE(REPLACE(HS.Phone_Amount, '$', ''), ',', '') AS DECIMAL(18,2)) END ,
                CASE WHEN HS.Living_Expenses IS NULL OR LTRIM(RTRIM(HS.Living_Expenses)) = '' THEN NULL
                     ELSE TRY_CAST(REPLACE(REPLACE(HS.Living_Expenses, '$', ''), ',', '') AS DECIMAL(18,2)) END ,
                CASE WHEN HS.Other_Amount_1 IS NULL OR LTRIM(RTRIM(HS.Other_Amount_1)) = '' THEN NULL
                     ELSE TRY_CAST(REPLACE(REPLACE(HS.Other_Amount_1, '$', ''), ',', '') AS DECIMAL(18,2)) END ,
                HS.Other_Information ,
                1 ,
                {{CurrentSessionID}} ,
                HS.Date_Entered ,
                1
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1 FROM tblHardshipRequest R WITH ( NOLOCK ) WHERE R.AccountID = A.AccountID )
;
