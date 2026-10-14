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
-- NOTE: tblHardshipStatus spells the FHSP label "Possiple Hardship"; the RCS label is
-- "Possible Hardship". hardship_status_codes.json maps one to the other so the label
-- match below finds it (found 2026-10-06 - the Fleetcor row landed with no status).
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
-- 2026-10-06 REWRITE (Stacey Mitchell, Complaints/Hardship Mapping chat, same day):
-- test-debtrak's hardship screen is the new hardship module (HardshipDbContext). Its SOFP
-- page is driven by tblHardship_StatementVersion -> tblHardshipRequest -> the
-- tblHardshipRequest_Line / _Debtor / _Address / _Dependant child rows, NOT by the legacy
-- flat columns on tblHardshipRequest that the first version of this file populated.
-- Every app-created hardship on testse has a current statement version; the migrated
-- Fleetcor ones had none, so the SOFP page showed nothing. The field-by-field targets
-- below follow Documents/../hardship_system_mapping_updated-01-10-2026.xlsx (SOFP
-- Personal/Employment/Financial Details, Section A, Section B, Hardship Status TAB).
--
-- The RCS SOFP income and expense figures are MONTHLY - confirmed by Stacey Mitchell on
-- 2026-10-06 in the Complaints/Hardship Mapping chat. RC_HARDSHIP_EXTRACT carries no
-- frequency for them (only Repay_Frequency for the proposed repayment), so every
-- income/expense line is loaded as FrequencyID 4 (Monthly).
--
-- Open hardships stay open. Stacey, same day, on the 11 Fleetcor hardships (5 approved,
-- 5 in assessment, 1 possible hardship; four approved ones with a moratorium end date
-- already passed): "leave them open, we might need to follow up with the customer" - her
-- team will close applications in RCS before the real migration, so this file never
-- infers closure from a moratorium end date.
--
-- ARCHIVED applications are the exception (Stacey, 2026-10-07): RCS archives an application
-- when it is finished or no longer needed, and an archived one must not come through as
-- open - "just put them through as Financial Hardship Closed". The extract has no archive
-- date yet (Archive_Comment is there but blank); Cheneeth was asked to add it. The staging
-- column Archive_Date is already in the schema and mapping, so once the file carries it the
-- hardship lands as FHSPCLOSED with EndDate = archive date, ClosedBy = RCS Migration and a
-- closing history row. Until then Archive_Date is NULL and nothing here changes.
--
-- 2026-10-07: three more new-module tables, each with a target in the workbook and data in
-- the Fleetcor extract, written the way the application writes them (test-debtrak):
--   tblHardship_DocumentRequest   SOFP Section B checklist (Checklist_Pay_Slips +
--                                 Checklist_Centrelink_Docs -> type 3, Checklist_Medical_Docs
--                                 -> type 5, Checklist_Other_Docs -> type 7), one check item
--                                 per type, ReceivedTS / ProvidedBy set when the box is ticked.
--   tblHardship_PreferredContact  Preferred_Hardship_Contact_Method as a channel row (email /
--                                 mobile) carrying the SOFP email or mobile, linked to the
--                                 matching tblContactDetail row when the contact has one.
--                                 LETTER would need an AddressID row and no extract seen so far
--                                 has it, so it stays on tblHardship.HardshipContactMethodID only.
--   tblHardshipOutcome_Decision   one decision per decided hardship: accepted -> accept-moratorium
--                                 when a moratorium was set, else accept-arrangement, dated
--                                 Approved_Date; declined -> decline with the reason row matched
--                                 on the legacy HardshipDeclinedStatusID; withdrawn -> decline
--                                 with the legacy withdraw reason, as the app records a customer
--                                 withdrawal. decided_by is RCS Migration: the extract has no
--                                 approver. The notice channel follows the preferred contact.
--
-- Re-run safety: every insert re-joins its parent via CreateSessionID = {{CurrentSessionID}}
-- (tblHardship additionally via Z_REF) and is guarded by NOT EXISTS on the natural key, so
-- running the file twice in one session adds nothing the second time.
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
          ClosedBy ,
          HoldStartDate ,
          HoldEndDate ,
          ReviewDate ,
          ClientCode ,
          Z_REF ,
          -- New-module header columns (all set by the app on every hardship it creates)
          HardshipAccepted ,
          CustomerConsentStatusID ,
          AdditionalAssistanceRequired ,
          HardshipSourceID ,
          HardshipCaptureChannelID ,
          HardshipContactMethodID ,
          CaseReference ,
          CreatedBy ,
          CreatedTs ,
          LodgedAt
        )
        SELECT  A.AccountID ,
                HS.HS_Date_Triggered ,
                1 ,
                {{CurrentSessionID}} ,
                HS.Date_Entered ,
                1 ,
                CASE WHEN HS.Archive_Date IS NOT NULL THEN CLOSED.HardshipStatusID ELSE STAT.HardshipStatusID END ,
                CAUSE.HardshipCauseID ,
                LEFT(HS.Other_Cause, 50) ,
                WITHDRAWN.HardshipWithdrawStatusID ,
                HS.Withdrawn_Date ,
                CASE HS.Waiver_Requested WHEN 'Yes' THEN 1 WHEN 'No' THEN 0 END ,
                CASE WHEN HS.Waiver_Amount IS NULL OR LTRIM(RTRIM(HS.Waiver_Amount)) = '' THEN NULL
                     ELSE TRY_CAST(REPLACE(REPLACE(HS.Waiver_Amount, '$', ''), ',', '') AS DECIMAL(18,2)) END ,
                WAIVER.HardshipWaiverStatusID ,
                DECLINED.HardshipDeclinedStatusID ,
                HS.Approved_Date ,
                -- The app stamps EndDate when a hardship is declined or withdrawn
                -- (HardshipAppService.SaveHardship); mirror that from the source dates.
                COALESCE(HS.Declined_Date, HS.Withdrawn_Date, HS.Archive_Date) ,
                CASE WHEN HS.Archive_Date IS NOT NULL THEN 'RCS Migration' END ,
                HS.Moratorium_Start ,
                HS.Moratorium_End ,
                HS.Review_Date ,
                'RCS' ,
                CAST(HS.Extended_Debt_Code AS NVARCHAR(40)) ,
                CASE WHEN HS.Assessment_Result = 'Hardship Accepted' THEN 1 END ,
                CASE WHEN UPPER(LTRIM(RTRIM(HS.Signed))) IN ('1', 'Y', 'YES', 'TRUE') THEN CONSENT_YES.HardshipCustomerConsentStatusID
                     WHEN UPPER(LTRIM(RTRIM(HS.Signed))) IN ('0', 'N', 'NO', 'FALSE') THEN CONSENT_NO.HardshipCustomerConsentStatusID END ,
                CASE WHEN HS.Assistance_Required IS NOT NULL AND LTRIM(RTRIM(HS.Assistance_Required)) <> '' THEN 1 END ,
                -- Application_By is blank in every extract seen so far; the app sets
                -- 'Customer' on everything an operator or the portal lodges.
                SOURCE_CUSTOMER.HardshipSourceID ,
                COALESCE(CHANNEL.HardshipCaptureChannelID, CHANNEL_OTHER.HardshipCaptureChannelID) ,
                CONTACTM.HardshipContactMethodID ,
                -- The app mints HS-nnnnnnnnn (9 digits) from tblHardship_ReferenceRegistry;
                -- a migrated case keeps the 10-digit RCS debt code so it is traceable and
                -- cannot collide with an app-minted reference.
                'HS-' + CAST(HS.Extended_Debt_Code AS NVARCHAR(16)) ,
                COALESCE(NULLIF(LTRIM(RTRIM(HS.Operator_Entered)), ''), 'RCS Migration') ,
                HS.Date_Entered ,
                HS.Date_Entered
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
                OUTER APPLY ( SELECT TOP 1 HardshipStatusID
                              FROM   tblHardshipStatus
                              WHERE  HardshipStatusCode = 'FHSPCLOSED'
                              ORDER BY HardshipStatusID
                            ) CLOSED
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
                OUTER APPLY ( SELECT TOP 1 HardshipCustomerConsentStatusID
                              FROM   tblHardshipCustomerConsentStatus
                              WHERE  HardshipCustomerConsentStatus = 'Yes'
                              ORDER BY HardshipCustomerConsentStatusID
                            ) CONSENT_YES
                OUTER APPLY ( SELECT TOP 1 HardshipCustomerConsentStatusID
                              FROM   tblHardshipCustomerConsentStatus
                              WHERE  HardshipCustomerConsentStatus = 'No'
                              ORDER BY HardshipCustomerConsentStatusID
                            ) CONSENT_NO
                OUTER APPLY ( SELECT TOP 1 HardshipSourceID
                              FROM   tblHardshipSource
                              WHERE  HardshipSource = 'Customer'
                              ORDER BY HardshipSourceID
                            ) SOURCE_CUSTOMER
                -- Application method: Application_Origin first, Sofp_Type as the fallback
                -- (workbook, Hardship Status TAB). RCS values seen: 'Customer Portal',
                -- 'Letter Received', 'Via Telephone'. Anything else lands on 'Others'.
                OUTER APPLY ( SELECT TOP 1 HardshipCaptureChannelID
                              FROM   tblHardshipCaptureChannel
                              WHERE  HardshipCaptureChannel =
                                     CASE WHEN COALESCE(NULLIF(HS.Application_Origin, ''), HS.Sofp_Type) LIKE '%Portal%'    THEN 'Portal'
                                          WHEN COALESCE(NULLIF(HS.Application_Origin, ''), HS.Sofp_Type) LIKE '%Letter%'    THEN 'Letter'
                                          WHEN COALESCE(NULLIF(HS.Application_Origin, ''), HS.Sofp_Type) LIKE '%Telephone%' THEN 'Phone'
                                          WHEN COALESCE(NULLIF(HS.Application_Origin, ''), HS.Sofp_Type) LIKE '%Phone%'     THEN 'Phone'
                                          WHEN COALESCE(NULLIF(HS.Application_Origin, ''), HS.Sofp_Type) LIKE '%Email%'     THEN 'Email'
                                          WHEN COALESCE(NULLIF(HS.Application_Origin, ''), HS.Sofp_Type) LIKE '%SMS%'       THEN 'SMS'
                                     END
                              ORDER BY HardshipCaptureChannelID
                            ) CHANNEL
                OUTER APPLY ( SELECT TOP 1 HardshipCaptureChannelID
                              FROM   tblHardshipCaptureChannel
                              WHERE  HardshipCaptureChannel = 'Others'
                              ORDER BY HardshipCaptureChannelID
                            ) CHANNEL_OTHER
                -- Preferred_Hardship_Contact_Method is EMAIL / LETTER / SMS / PHONE in RCS;
                -- tblHardshipContactMethod labels are Email / Letter / SMS / Phone / Mobile.
                OUTER APPLY ( SELECT TOP 1 HardshipContactMethodID
                              FROM   tblHardshipContactMethod
                              WHERE  UPPER(HardshipContactMethod) = UPPER(LTRIM(RTRIM(HS.Preferred_Hardship_Contact_Method)))
                              ORDER BY HardshipContactMethodID
                            ) CONTACTM
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblHardship H0 WITH ( NOLOCK )
                                 WHERE  H0.AccountId = A.AccountID
                                        AND H0.Z_REF = CAST(HS.Extended_Debt_Code AS NVARCHAR(40))
                                        AND H0.CreateSessionID = {{CurrentSessionID}} )
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

-- RCS hardship comments: tblHardship has no comments column; the workbook (Hardship Status
-- TAB, Assessment / Comments) puts them in tblHardshipHistory.Note (nvarchar(2000)) on a
-- history row carrying the hardship's current status.
INSERT  INTO tblHardshipHistory WITH ( ROWLOCK )
        ( HardshipID, HardshipStatusID, CreateID, CreateSessionID, CreateTS, Note )
        SELECT  H.HardshipID, H.HarshipStatusID, 1, {{CurrentSessionID}}, COALESCE(HS.Date_Entered, GETUTCDATE()),
                LEFT(LTRIM(RTRIM(HS.Hardship_Comments)), 2000)
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardship H WITH ( NOLOCK ) ON H.Z_REF = CAST(HS.Extended_Debt_Code AS NVARCHAR(40))
                                                         AND H.AccountId = A.AccountID
                                                         AND H.CreateSessionID = {{CurrentSessionID}}
        WHERE   A.LoadID = {{LoadID}}
                AND HS.Hardship_Comments IS NOT NULL
                AND LTRIM(RTRIM(HS.Hardship_Comments)) <> ''
                AND NOT EXISTS ( SELECT 1 FROM tblHardshipHistory HH WITH ( NOLOCK )
                                 WHERE  HH.HardshipID = H.HardshipID AND HH.Note IS NOT NULL AND HH.CreateSessionID = {{CurrentSessionID}} )
;

-- An archived application gets its closing step on the timeline too, dated the archive date.
INSERT  INTO tblHardshipHistory WITH ( ROWLOCK )
        ( HardshipID, HardshipStatusID, CreateID, CreateSessionID, CreateTS )
        SELECT  H.HardshipID, CLOSED.HardshipStatusID, 1, {{CurrentSessionID}}, HS.Archive_Date
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardship H WITH ( NOLOCK ) ON H.Z_REF = CAST(HS.Extended_Debt_Code AS NVARCHAR(40))
                                                         AND H.AccountId = A.AccountID
                                                         AND H.CreateSessionID = {{CurrentSessionID}}
                CROSS APPLY ( SELECT TOP 1 HardshipStatusID
                              FROM   tblHardshipStatus
                              WHERE  HardshipStatusCode = 'FHSPCLOSED'
                              ORDER BY HardshipStatusID
                            ) CLOSED
        WHERE   A.LoadID = {{LoadID}}
                AND HS.Archive_Date IS NOT NULL
                AND NOT EXISTS ( SELECT 1 FROM tblHardshipHistory HH WITH ( NOLOCK )
                                 WHERE  HH.HardshipID = H.HardshipID AND HH.HardshipStatusID = CLOSED.HardshipStatusID AND HH.Note IS NULL )
;

-- =====================================================================================
-- SOFP (statement of financial position). One tblHardshipRequest per hardship, re-joined
-- below through AccountID + CreateSessionID (the table has no Z_REF). The legacy flat
-- figure columns are still filled for anything that reads them, but the page itself
-- reads the _Line rows and the statement version inserted after them.
-- =====================================================================================
INSERT  INTO tblHardshipRequest WITH ( ROWLOCK )
        ( AccountID ,
          OtherText ,
          WhenFinancialImpact ,
          ShortTerm ,
          ProposalText ,
          Salary ,
          SalaryFrequencyID ,
          CentrelinkBenefits ,
          CentrelinkBenefitsFrequencyID ,
          OtherIncome ,
          OtherIncomeFrequencyID ,
          MortgageOrRent ,
          MortgageOrRentFrequencyID ,
          CouncilRates ,
          CouncilRatesFrequencyID ,
          TotalUtilitiesBills ,
          TotalUtilitiesBillsFrequencyID ,
          TelephoneMobile ,
          TelephoneMobileFrequencyID ,
          Food ,
          FoodFrequencyID ,
          OtherExpenses ,
          OtherExpensesFrequencyID ,
          OtherExpensesText ,
          HardshipCauseID ,
          Origin ,
          SubmittedAt ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          CreatedBy ,
          CreatedTs ,
          StatusID
        )
        SELECT  A.AccountID ,
                -- OtherText is the description shown for hardship type 'Other' (Hardship
                -- Cause BOX); Other_Information now goes to the statement's CircumstancesText.
                NULLIF(LTRIM(RTRIM(HS.Other_Cause)), '') ,
                HS.Fin_Diff_Begin ,
                CASE HS.Fin_Diff_Term WHEN 'Short Term' THEN 1 WHEN 'Long Term' THEN 0 END ,
                NULLIF(LTRIM(RTRIM(HS.Assistance_Required)), '') ,
                AMT.Income_1 ,          CASE WHEN AMT.Income_1 IS NOT NULL THEN MONTHLY.FrequencyID END ,
                AMT.Centrelink_Income , CASE WHEN AMT.Centrelink_Income IS NOT NULL THEN MONTHLY.FrequencyID END ,
                AMT.Other_Income ,      CASE WHEN AMT.Other_Income IS NOT NULL THEN MONTHLY.FrequencyID END ,
                AMT.Rental_Amount ,     CASE WHEN AMT.Rental_Amount IS NOT NULL THEN MONTHLY.FrequencyID END ,
                AMT.Rates_Amount ,      CASE WHEN AMT.Rates_Amount IS NOT NULL THEN MONTHLY.FrequencyID END ,
                AMT.Utilities ,         CASE WHEN AMT.Utilities IS NOT NULL THEN MONTHLY.FrequencyID END ,
                AMT.Phone_Amount ,      CASE WHEN AMT.Phone_Amount IS NOT NULL THEN MONTHLY.FrequencyID END ,
                AMT.Living_Expenses ,   CASE WHEN AMT.Living_Expenses IS NOT NULL THEN MONTHLY.FrequencyID END ,
                AMT.Other_Amount_1 ,    CASE WHEN AMT.Other_Amount_1 IS NOT NULL THEN MONTHLY.FrequencyID END ,
                LEFT(NULLIF(LTRIM(RTRIM(HS.Other_Expense_Type)), ''), 255) ,
                CAUSE.HardshipCauseID ,
                -- The app leaves Origin NULL on operator-entered statements and writes
                -- 'portal' on customer-portal ones.
                CASE WHEN HS.Sofp_Type = 'Customer Portal' THEN 'portal' END ,
                HS.Date_Signed ,
                1 ,
                {{CurrentSessionID}} ,
                COALESCE(HS.Date_Entered, GETUTCDATE()) ,
                CASE WHEN HS.Sofp_Type = 'Customer Portal' THEN 'Customer Portal'
                     ELSE COALESCE(NULLIF(LTRIM(RTRIM(HS.Operator_Entered)), ''), 'RCS Migration') END ,
                COALESCE(HS.Date_Entered, GETUTCDATE()) ,
                1
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardship H WITH ( NOLOCK ) ON H.Z_REF = CAST(HS.Extended_Debt_Code AS NVARCHAR(40))
                                                         AND H.AccountId = A.AccountID
                                                         AND H.CreateSessionID = {{CurrentSessionID}}
                -- Zero is RCS's "box not used" value (an untouched SOFP arrives as all
                -- 0.00), so zeros are NULL here, matching the _Line rows further down.
                CROSS APPLY ( SELECT
                                NULLIF(TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Income_1)), ''), '$', ''), ',', '') AS DECIMAL(18,2)), 0)                     AS Income_1 ,
                                NULLIF(TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Centrelink_Income)), ''), '$', ''), ',', '') AS DECIMAL(18,2)), 0)            AS Centrelink_Income ,
                                NULLIF(TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Other_Income)), ''), '$', ''), ',', '') AS DECIMAL(18,2)), 0)                 AS Other_Income ,
                                NULLIF(TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Rental_Amount)), ''), '$', ''), ',', '') AS DECIMAL(18,2)), 0)                AS Rental_Amount ,
                                NULLIF(TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Rates_Amount)), ''), '$', ''), ',', '') AS DECIMAL(18,2)), 0)                 AS Rates_Amount ,
                                NULLIF(TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Electricity_Water_Gas_Amount)), ''), '$', ''), ',', '') AS DECIMAL(18,2)), 0) AS Utilities ,
                                NULLIF(TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Phone_Amount)), ''), '$', ''), ',', '') AS DECIMAL(18,2)), 0)                 AS Phone_Amount ,
                                NULLIF(TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Living_Expenses)), ''), '$', ''), ',', '') AS DECIMAL(18,2)), 0)              AS Living_Expenses ,
                                NULLIF(TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Other_Amount_1)), ''), '$', ''), ',', '') AS DECIMAL(18,2)), 0)               AS Other_Amount_1
                            ) AMT
                OUTER APPLY ( SELECT TOP 1 HardshipCauseID
                              FROM   tblHardshipCause
                              WHERE  HardshipCause = HS.Hardship_Cause
                              ORDER BY HardshipCauseID
                            ) CAUSE
                OUTER APPLY ( SELECT TOP 1 FrequencyID FROM tblFrequency WHERE Frequency = 'Monthly' ORDER BY FrequencyID ) MONTHLY
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1 FROM tblHardshipRequest R WITH ( NOLOCK )
                                 WHERE  R.AccountID = A.AccountID AND R.CreateSessionID = {{CurrentSessionID}} )
;

-- Debtor rows: debtor 1 always (DisplayOrder 0, linked to the account's primary contact),
-- debtor 2 only when the extract names one (DisplayOrder 1). Employment status is matched
-- on the tblEmploymentStatus label; RCS 'Other (Please Specify):' lands on 'Unknown' with
-- the free text carried in OccupationTitle when no occupation was given.
INSERT  INTO tblHardshipRequest_Debtor WITH ( ROWLOCK )
        ( HardshipRequestID, ContactID, Title, FirstName, LastName, EmploymentStatusID, OccupationTitle, Employer, DisplayOrder, StatusID )
        SELECT  R.HardshipRequestID ,
                CASE WHEN D.Slot = 1 THEN PRIMARYC.ContactID END ,
                LEFT(NULLIF(LTRIM(RTRIM(D.Title)), ''), 50) ,
                LEFT(COALESCE(NULLIF(LTRIM(RTRIM(D.FirstName)), ''), CASE WHEN D.Slot = 1 THEN PRIMARYC.FirstName END), 200) ,
                -- a business debtor has its name in tblContact.EntityName, not LastName
                LEFT(COALESCE(NULLIF(LTRIM(RTRIM(D.LastName)), ''), CASE WHEN D.Slot = 1 THEN COALESCE(PRIMARYC.LastName, PRIMARYC.EntityName) END), 500) ,
                EMP.EmploymentStatusID ,
                LEFT(COALESCE(NULLIF(LTRIM(RTRIM(D.Occupation)), ''), NULLIF(LTRIM(RTRIM(D.OtherEmployment)), '')), 200) ,
                LEFT(NULLIF(LTRIM(RTRIM(D.Employer)), ''), 500) ,
                D.Slot - 1 ,
                1
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardshipRequest R WITH ( NOLOCK ) ON R.AccountID = A.AccountID AND R.CreateSessionID = {{CurrentSessionID}}
                CROSS APPLY ( VALUES
                                ( 1, HS.Debtor_1_Title, HS.Debtor_1_First_Name, HS.Debtor_1_Surname, HS.Employment_Status_1, HS.Other_Employment_1, HS.Occupation_Debtor_1, HS.Debtor_1_Employer ),
                                ( 2, HS.Debtor_2_Title, HS.Debtor_2_First_Name, HS.Debtor_2_Surname, HS.Employment_Status_2, HS.Other_Employment_2, HS.Occupation_Debtor_2, HS.Debtor_2_Employer )
                            ) D ( Slot, Title, FirstName, LastName, EmploymentStatus, OtherEmployment, Occupation, Employer )
                OUTER APPLY ( SELECT TOP 1 AC.ContactID, C.FirstName, C.LastName, C.EntityName
                              FROM   tblAccount_Contact AC WITH ( NOLOCK )
                                     INNER JOIN tblContact C WITH ( NOLOCK ) ON C.ContactID = AC.ContactID
                              WHERE  AC.AccountID = A.AccountID
                                     AND AC.RelationshipID = {{RelationshipID_PrimaryDebtor}}
                              ORDER BY AC.DisplayOrder, AC.ContactID
                            ) PRIMARYC
                OUTER APPLY ( SELECT TOP 1 EmploymentStatusID
                              FROM   tblEmploymentStatus
                              WHERE  EmploymentStatus LIKE
                                     CASE WHEN D.EmploymentStatus IN ('Full Time', 'Full-Time', 'Employed Full Time')          THEN 'Employed%Full Time'
                                          WHEN D.EmploymentStatus IN ('Part Time', 'Part-Time', 'Employed Part Time')          THEN 'Employed%Part Time'
                                          WHEN D.EmploymentStatus IN ('Self Employed', 'Self-Employed')                        THEN 'Self-Employed'
                                          WHEN D.EmploymentStatus = 'Casual'                                                   THEN 'Casual'
                                          WHEN D.EmploymentStatus = 'Unemployed'                                               THEN 'Unemployed'
                                          WHEN D.EmploymentStatus = 'Retired'                                                  THEN 'Retired'
                                          WHEN D.EmploymentStatus = 'Pensioner'                                                THEN 'Pensioner'
                                          WHEN D.EmploymentStatus IN ('Student', 'Full Time Education')                        THEN 'Student'
                                          WHEN D.EmploymentStatus = 'Home Duties'                                              THEN 'Home Duties'
                                          WHEN D.EmploymentStatus IS NOT NULL AND LTRIM(RTRIM(D.EmploymentStatus)) <> ''       THEN 'Unknown'
                                     END
                              ORDER BY EmploymentStatusID
                            ) EMP
        WHERE   A.LoadID = {{LoadID}}
                AND ( D.Slot = 1
                      OR NULLIF(LTRIM(RTRIM(D.FirstName)), '') IS NOT NULL
                      OR NULLIF(LTRIM(RTRIM(D.LastName)), '') IS NOT NULL )
                AND NOT EXISTS ( SELECT 1 FROM tblHardshipRequest_Debtor RD WITH ( NOLOCK )
                                 WHERE  RD.HardshipRequestID = R.HardshipRequestID AND RD.DisplayOrder = D.Slot - 1 )
;

-- Addresses: residential row (IsPostal 0, Home) and postal row (IsPostal 1, Mail), each only
-- when the extract has a line 1 or a suburb. Lines 1 and 2 are combined into Address, the
-- way the app stores them. StateID is resolved on either the short code or the full name.
INSERT  INTO tblHardshipRequest_Address WITH ( ROWLOCK )
        ( HardshipRequestID, AddressTypeID, Address, Suburb, State, StateID, Postcode, IsPostal, DisplayOrder, StatusID )
        SELECT  R.HardshipRequestID ,
                CASE WHEN AD.IsPostal = 1 THEN {{AddressTypeID_Mail}} ELSE {{AddressTypeID_Home}} END ,
                LEFT(NULLIF(LTRIM(RTRIM(CONCAT(NULLIF(LTRIM(RTRIM(AD.Line1)), ''), ' ', NULLIF(LTRIM(RTRIM(AD.Line2)), '')))), ''), 500) ,
                LEFT(NULLIF(LTRIM(RTRIM(AD.Suburb)), ''), 100) ,
                LEFT(NULLIF(LTRIM(RTRIM(AD.State)), ''), 100) ,
                ST.StateID ,
                LEFT(NULLIF(LTRIM(RTRIM(AD.Postcode)), ''), 100) ,
                AD.IsPostal ,
                AD.IsPostal ,
                1
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardshipRequest R WITH ( NOLOCK ) ON R.AccountID = A.AccountID AND R.CreateSessionID = {{CurrentSessionID}}
                CROSS APPLY ( VALUES
                                ( 0, HS.Debtor_1_Street_Address_1, HS.Debtor_1_Street_Address_2, HS.Debtor_1_Street_Address_Suburb, HS.Debtor_1_Street_Address_State, HS.Debtor_1_Street_Address_Post_Code ),
                                ( 1, HS.Debtor_1_Postal_Address_1, HS.Debtor_1_Postal_Address_2, HS.Debtor_1_Postal_Address_Suburb, HS.Debtor_1_Postal_Address_State, HS.Debtor_1_Postal_Address_Post_Code )
                            ) AD ( IsPostal, Line1, Line2, Suburb, State, Postcode )
                OUTER APPLY ( SELECT TOP 1 StateID
                              FROM   tblState
                              WHERE  UPPER(StateShort) = UPPER(LTRIM(RTRIM(AD.State)))
                                     OR UPPER(State) = UPPER(LTRIM(RTRIM(AD.State)))
                              ORDER BY CountryID, StateID
                            ) ST
        WHERE   A.LoadID = {{LoadID}}
                AND ( NULLIF(LTRIM(RTRIM(AD.Line1)), '') IS NOT NULL OR NULLIF(LTRIM(RTRIM(AD.Suburb)), '') IS NOT NULL )
                AND NOT EXISTS ( SELECT 1 FROM tblHardshipRequest_Address RA WITH ( NOLOCK )
                                 WHERE  RA.HardshipRequestID = R.HardshipRequestID AND RA.IsPostal = AD.IsPostal )
;

-- Dependants: Debtrak has no count column - the number of dependants is the number of
-- rows. One row per No_Dependants (capped at 20), with Age taken positionally from the
-- space-separated Dependant_Ages where it parses to a plausible whole number of years;
-- anything else (e.g. '2.5', or the stray customer ids RCS sometimes puts there) is NULL.
INSERT  INTO tblHardshipRequest_Dependant WITH ( ROWLOCK )
        ( HardshipRequestID, Age, DisplayOrder, StatusID )
        SELECT  R.HardshipRequestID ,
                CASE WHEN TRY_CAST(AG.value AS INT) BETWEEN 0 AND 30 THEN TRY_CAST(AG.value AS INT) END ,
                N.n ,
                1
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardshipRequest R WITH ( NOLOCK ) ON R.AccountID = A.AccountID AND R.CreateSessionID = {{CurrentSessionID}}
                CROSS APPLY ( SELECT TRY_CAST(NULLIF(LTRIM(RTRIM(HS.No_Dependants)), '') AS INT) AS Cnt ) DC
                INNER JOIN ( VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),(12),(13),(14),(15),(16),(17),(18),(19) ) N ( n )
                        ON N.n < DC.Cnt
                OUTER APPLY ( SELECT value FROM STRING_SPLIT(LTRIM(RTRIM(HS.Dependant_Ages)), ' ', 1) WHERE ordinal = N.n + 1 ) AG
        WHERE   A.LoadID = {{LoadID}}
                AND DC.Cnt > 0
                AND NOT EXISTS ( SELECT 1 FROM tblHardshipRequest_Dependant RD WITH ( NOLOCK ) WHERE RD.HardshipRequestID = R.HardshipRequestID )
;

-- SOFP line items: one tblHardshipRequest_Line per populated source figure, categorised per
-- the workbook's SOFP Financial Details tab (CapitalTypeID 1 Income, 2 Expenditure,
-- 3 Assets, 4 Liabilities; CapitalCategoryID resolved on the tblCapitalCategory label).
-- Zero and blank amounts are skipped - RCS pads untouched boxes with 0.00. Property and
-- vehicle assets have no value in the source, so they load as 0 with the description.
-- Income lines link to the debtor row (slot 1 or 2), the way the app writes them.
INSERT  INTO tblHardshipRequest_Line WITH ( ROWLOCK )
        ( HardshipRequestID, CapitalTypeID, CapitalCategoryID, Description, Amount, FrequencyID, RepaymentAmount, HardshipRequestDebtorID, DisplayOrder, StatusID )
        SELECT  X.HardshipRequestID ,
                X.CapitalTypeID ,
                X.CapitalCategoryID ,
                X.Description ,
                X.Amount ,
                X.FrequencyID ,
                NULL ,
                X.HardshipRequestDebtorID ,
                ROW_NUMBER() OVER ( PARTITION BY X.HardshipRequestID, X.CapitalTypeID ORDER BY X.Seq ) - 1 ,
                1
        FROM    ( SELECT  R.HardshipRequestID ,
                          L.CapitalTypeID ,
                          CAT.CapitalCategoryID ,
                          LEFT(NULLIF(LTRIM(RTRIM(L.Description)), ''), 255) AS Description ,
                          COALESCE(L.Amount, 0) AS Amount ,
                          CASE WHEN L.CapitalTypeID IN (1, 2) THEN MONTHLY.FrequencyID END AS FrequencyID ,
                          CASE WHEN L.DebtorSlot = 1 THEN D1.HardshipRequestDebtorID
                               WHEN L.DebtorSlot = 2 THEN D2.HardshipRequestDebtorID END AS HardshipRequestDebtorID ,
                          L.Seq
                  FROM    RC_HARDSHIP_EXTRACT HS
                          INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                          INNER JOIN tblHardshipRequest R WITH ( NOLOCK ) ON R.AccountID = A.AccountID AND R.CreateSessionID = {{CurrentSessionID}}
                          OUTER APPLY ( SELECT TOP 1 HardshipRequestDebtorID FROM tblHardshipRequest_Debtor WHERE HardshipRequestID = R.HardshipRequestID AND DisplayOrder = 0 ORDER BY HardshipRequestDebtorID ) D1
                          OUTER APPLY ( SELECT TOP 1 HardshipRequestDebtorID FROM tblHardshipRequest_Debtor WHERE HardshipRequestID = R.HardshipRequestID AND DisplayOrder = 1 ORDER BY HardshipRequestDebtorID ) D2
                          OUTER APPLY ( SELECT TOP 1 FrequencyID FROM tblFrequency WHERE Frequency = 'Monthly' ORDER BY FrequencyID ) MONTHLY
                          CROSS APPLY ( SELECT
                                          -- money boxes arrive as text with '$' and ',' in some extracts
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Income_1)), ''), '$', ''), ',', '') AS DECIMAL(18,2))                     AS Income_1 ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Income_2)), ''), '$', ''), ',', '') AS DECIMAL(18,2))                     AS Income_2 ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Centrelink_Income)), ''), '$', ''), ',', '') AS DECIMAL(18,2))            AS Centrelink_Income ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Other_Income)), ''), '$', ''), ',', '') AS DECIMAL(18,2))                 AS Other_Income ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Rental_Amount)), ''), '$', ''), ',', '') AS DECIMAL(18,2))                AS Rental_Amount ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Rates_Amount)), ''), '$', ''), ',', '') AS DECIMAL(18,2))                 AS Rates_Amount ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Electricity_Water_Gas_Amount)), ''), '$', ''), ',', '') AS DECIMAL(18,2)) AS Utilities ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Phone_Amount)), ''), '$', ''), ',', '') AS DECIMAL(18,2))                 AS Phone_Amount ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Car_Expenses_Amount)), ''), '$', ''), ',', '') AS DECIMAL(18,2))          AS Car_Expenses ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Living_Expenses)), ''), '$', ''), ',', '') AS DECIMAL(18,2))              AS Living_Expenses ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Other_Amount_1)), ''), '$', ''), ',', '') AS DECIMAL(18,2))               AS Other_Amount_1 ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Other_Amount_2)), ''), '$', ''), ',', '') AS DECIMAL(18,2))               AS Other_Amount_2 ,
                                          HS.Assets_Cheque_Acc                                                                                                       AS Assets_Cheque_Acc ,
                                          HS.Assets_Savings_Acc                                                                                                      AS Assets_Savings_Acc ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Assets_Superannuation)), ''), '$', ''), ',', '') AS DECIMAL(18,2))        AS Assets_Superannuation ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Assets_Other)), ''), '$', ''), ',', '') AS DECIMAL(18,2))                 AS Assets_Other ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Assets_Boat)), ''), '$', ''), ',', '') AS DECIMAL(18,2))                  AS Assets_Boat ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Asset_Caravan)), ''), '$', ''), ',', '') AS DECIMAL(18,2))                AS Asset_Caravan ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Asset_Motorbike)), ''), '$', ''), ',', '') AS DECIMAL(18,2))              AS Asset_Motorbike ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Assets_Furniture_Personal)), ''), '$', ''), ',', '') AS DECIMAL(18,2))    AS Assets_Furniture ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Assets_Computer)), ''), '$', ''), ',', '') AS DECIMAL(18,2))              AS Assets_Computer ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Credit_Card_Balance_1)), ''), '$', ''), ',', '') AS DECIMAL(18,2))        AS CC_Balance_1 ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Credit_Card_Balance_2)), ''), '$', ''), ',', '') AS DECIMAL(18,2))        AS CC_Balance_2 ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Credit_Card_Balance_3)), ''), '$', ''), ',', '') AS DECIMAL(18,2))        AS CC_Balance_3 ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Store_Card_Balance)), ''), '$', ''), ',', '') AS DECIMAL(18,2))           AS Store_Card_Balance ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Overdraft_Balance)), ''), '$', ''), ',', '') AS DECIMAL(18,2))            AS Overdraft_Balance ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Home_Mortgage_Balance)), ''), '$', ''), ',', '') AS DECIMAL(18,2))        AS Home_Mortgage_Balance ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Investment_Loan_Balance)), ''), '$', ''), ',', '') AS DECIMAL(18,2))      AS Investment_Loan_Balance ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Vehicle_Loan_Balance)), ''), '$', ''), ',', '') AS DECIMAL(18,2))         AS Vehicle_Loan_Balance ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Personal_Loan_Balance)), ''), '$', ''), ',', '') AS DECIMAL(18,2))        AS Personal_Loan_Balance ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Other_Loans_Amount)), ''), '$', ''), ',', '') AS DECIMAL(18,2))           AS Other_Loans_Amount ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Hire_Purchase_Amount)), ''), '$', ''), ',', '') AS DECIMAL(18,2))         AS Hire_Purchase_Amount ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Other_Liability_Amount_1)), ''), '$', ''), ',', '') AS DECIMAL(18,2))     AS Other_Liability_Amount_1 ,
                                          TRY_CAST(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(HS.Other_Liability_Amount_2)), ''), '$', ''), ',', '') AS DECIMAL(18,2))     AS Other_Liability_Amount_2 ,
                                          LTRIM(RTRIM(CONCAT(NULLIF(LTRIM(RTRIM(HS.Property_Address_1)), ''), ' ', NULLIF(LTRIM(RTRIM(HS.Property_Address_2)), ''), ' ',
                                                             NULLIF(LTRIM(RTRIM(HS.Property_Suburb)), ''), ' ', NULLIF(LTRIM(RTRIM(HS.Property_State)), ''), ' ',
                                                             NULLIF(LTRIM(RTRIM(HS.Property_Post_Code)), '')))) AS Property_Desc ,
                                          LTRIM(RTRIM(CONCAT(NULLIF(LTRIM(RTRIM(HS.Vehicle_1_Make)), ''), ' ', NULLIF(LTRIM(RTRIM(HS.Vehicle_1_Model)), ''), ' ', NULLIF(LTRIM(RTRIM(HS.Vehicle_1_Year)), '')))) AS Vehicle_1_Desc ,
                                          LTRIM(RTRIM(CONCAT(NULLIF(LTRIM(RTRIM(HS.Vehicle_2_Make)), ''), ' ', NULLIF(LTRIM(RTRIM(HS.Vehicle_2_Model)), ''), ' ', NULLIF(LTRIM(RTRIM(HS.Vehicle_2_Year)), '')))) AS Vehicle_2_Desc
                                      ) V
                          -- Seq, CapitalTypeID, category label, description, amount, debtor slot
                          CROSS APPLY ( VALUES
                                          -- Income (type 1)
                                          (  1, 1, 'Income after tax',                            NULL,                              V.Income_1,                 1 ),
                                          (  2, 1, 'Income after tax',                            NULL,                              V.Income_2,                 2 ),
                                          (  3, 1, 'Centrelink income',                           NULL,                              V.Centrelink_Income,        1 ),
                                          (  4, 1, 'Other income',                                NULL,                              V.Other_Income,             1 ),
                                          -- Expenditure (type 2)
                                          ( 10, 2, 'Rent',                                        NULL,                              V.Rental_Amount,            NULL ),
                                          ( 11, 2, 'Rate and body corporate fees',                NULL,                              V.Rates_Amount,             NULL ),
                                          ( 12, 2, 'Utilities (electricity, gas, water)',         NULL,                              V.Utilities,                NULL ),
                                          ( 13, 2, 'Communication (phone, internet, pay TV)',     NULL,                              V.Phone_Amount,             NULL ),
                                          ( 14, 2, 'Vehicle (eg fuel, insurance, registration)',  NULL,                              V.Car_Expenses,             NULL ),
                                          ( 15, 2, 'Food and groceries (also takeaway)',          'Living expenses (food and clothing)', V.Living_Expenses,      NULL ),
                                          ( 16, 2, 'Other (subscriptions, sports, hobbies)',      HS.Other_Expense_Type,             V.Other_Amount_1,           NULL ),
                                          ( 17, 2, 'Other (subscriptions, sports, hobbies)',      HS.Other_Expense_Type_2,           V.Other_Amount_2,           NULL ),
                                          -- Assets (type 3)
                                          ( 20, 3, 'Savings account',                             'Cheque A/C',                      V.Assets_Cheque_Acc,        NULL ),
                                          ( 21, 3, 'Savings account',                             'Savings A/C',                     V.Assets_Savings_Acc,       NULL ),
                                          ( 22, 3, 'Superannuation',                              NULL,                              V.Assets_Superannuation,    NULL ),
                                          ( 23, 3, 'Other Asset',                                 'Other asset',                     V.Assets_Other,             NULL ),
                                          ( 24, 3, 'Other Asset',                                 'Boat',                            V.Assets_Boat,              NULL ),
                                          ( 25, 3, 'Other Asset',                                 'Caravan',                         V.Asset_Caravan,            NULL ),
                                          ( 26, 3, 'Vehicle',                                     'Motorbike',                       V.Asset_Motorbike,          NULL ),
                                          ( 27, 3, 'Household furniture',                         NULL,                              V.Assets_Furniture,         NULL ),
                                          ( 28, 3, 'Other Asset',                                 'Computer',                        V.Assets_Computer,          NULL ),
                                          ( 29, 3, 'PropertyOwned',                               V.Property_Desc,                   NULL,                       NULL ),
                                          ( 30, 3, 'Vehicle',                                     V.Vehicle_1_Desc,                  NULL,                       NULL ),
                                          ( 31, 3, 'Vehicle',                                     V.Vehicle_2_Desc,                  NULL,                       NULL ),
                                          -- Liabilities (type 4)
                                          ( 40, 4, 'Credit card, store card or layby',            COALESCE(NULLIF(HS.Credit_Card_Type_1, ''), 'Credit card'), V.CC_Balance_1,      NULL ),
                                          ( 41, 4, 'Credit card, store card or layby',            COALESCE(NULLIF(HS.Credit_Card_Type_2, ''), 'Credit card'), V.CC_Balance_2,      NULL ),
                                          ( 42, 4, 'Credit card, store card or layby',            COALESCE(NULLIF(HS.Credit_Card_Type_3, ''), 'Credit card'), V.CC_Balance_3,      NULL ),
                                          ( 43, 4, 'Credit card, store card or layby',            COALESCE(NULLIF(HS.Store_Card_Type, ''), 'Store card'),     V.Store_Card_Balance, NULL ),
                                          ( 44, 4, 'Personal loan/overdraft',                     'Overdraft',                       V.Overdraft_Balance,        NULL ),
                                          ( 45, 4, 'Home/investment property loan',               'Home mortgage',                   V.Home_Mortgage_Balance,    NULL ),
                                          ( 46, 4, 'Home/investment property loan',               'Investment loan',                 V.Investment_Loan_Balance,  NULL ),
                                          ( 47, 4, 'Vehicle loan',                                COALESCE(NULLIF(HS.Vehicle_Loan_Type, ''), 'Vehicle loan'),   V.Vehicle_Loan_Balance, NULL ),
                                          ( 48, 4, 'Personal loan/overdraft',                     COALESCE(NULLIF(HS.Personal_Loan_Type, ''), 'Personal loan'), V.Personal_Loan_Balance, NULL ),
                                          ( 49, 4, 'Personal loan/overdraft',                     'Other loans',                     V.Other_Loans_Amount,       NULL ),
                                          ( 50, 4, 'Lease/rental contract',                       'Hire purchase',                   V.Hire_Purchase_Amount,     NULL ),
                                          ( 51, 4, 'Other (eg overdue bills, rates)',             HS.Other_Liability_Type_1,         V.Other_Liability_Amount_1, NULL ),
                                          ( 52, 4, 'Other (eg overdue bills, rates)',             HS.Other_Liability_Type_2,         V.Other_Liability_Amount_2, NULL )
                                      ) L ( Seq, CapitalTypeID, CategoryLabel, Description, Amount, DebtorSlot )
                          OUTER APPLY ( SELECT TOP 1 CapitalCategoryID
                                        FROM   tblCapitalCategory
                                        WHERE  CapitalCategory = L.CategoryLabel
                                               AND CapitalTypeID = L.CapitalTypeID
                                        ORDER BY CapitalCategoryID
                                      ) CAT
                  WHERE   A.LoadID = {{LoadID}}
                          -- a monetary line needs a non-zero amount; a description-only
                          -- asset line (property, vehicle) needs its description
                          AND ( ( L.Amount IS NOT NULL AND L.Amount <> 0 )
                                OR ( L.Amount IS NULL AND L.Seq IN (29, 30, 31) AND NULLIF(LTRIM(RTRIM(L.Description)), '') IS NOT NULL ) )
                          -- RCS sometimes repeats vehicle 1 in the vehicle 2 boxes
                          AND NOT ( L.Seq = 31 AND V.Vehicle_2_Desc = V.Vehicle_1_Desc )
                          AND NOT EXISTS ( SELECT 1 FROM tblHardshipRequest_Line RL WITH ( NOLOCK ) WHERE RL.HardshipRequestID = R.HardshipRequestID )
                ) X
;

-- Statement version: the row the hardship screen reads to find the SOFP. One per hardship
-- (sequence 1, is_current 1), pointing at the request above. surplus/deficit are frozen
-- here by the app at capture time; the check constraint wants both >= 0 with one of them
-- zero, so net monthly income is split into whichever side applies. All loaded lines are
-- monthly (see the assumption at the top), so no frequency normalisation is needed.
INSERT  INTO tblHardship_StatementVersion WITH ( ROWLOCK )
        ( hardship_request_id, hardship_id, account_id, sequence, origin, captured_by, captured_at,
          surplus_at_capture, deficit_at_capture, is_current,
          EmailDisclaimerAgreed, TimeToOvercome, HomePhone, Mobile, Email,
          ProposedAmount, ProposedFrequencyID, ProposedStartDate,
          SourceReference, SourceCallingApplication, CircumstancesText )
        SELECT  R.HardshipRequestID ,
                H.HardshipID ,
                A.AccountID ,
                1 ,
                CASE WHEN HS.Sofp_Type = 'Customer Portal' THEN 'portal' ELSE 'operator' END ,
                CASE WHEN HS.Sofp_Type = 'Customer Portal' THEN 'Customer Portal'
                     ELSE COALESCE(NULLIF(LTRIM(RTRIM(HS.Operator_Entered)), ''), 'RCS Migration') END ,
                COALESCE(HS.Date_Entered, HS.HS_Date_Triggered, GETUTCDATE()) ,
                CASE WHEN NET.Net > 0 THEN NET.Net ELSE 0 END ,
                CASE WHEN NET.Net < 0 THEN -NET.Net ELSE 0 END ,
                1 ,
                CASE UPPER(LTRIM(RTRIM(HS.Email_Disclaimer))) WHEN 'Y' THEN 1 WHEN 'YES' THEN 1 WHEN '1' THEN 1 WHEN 'N' THEN 0 WHEN 'NO' THEN 0 WHEN '0' THEN 0 END ,
                -- Long_Term_Info / Short_Term_Info explain the expected period; RCS repeats
                -- the term itself ('Short Term') in the box when nothing was typed.
                LEFT(COALESCE(NULLIF(NULLIF(LTRIM(RTRIM(HS.Long_Term_Info)), ''), HS.Fin_Diff_Term),
                              NULLIF(NULLIF(LTRIM(RTRIM(HS.Short_Term_Info)), ''), HS.Fin_Diff_Term)), 500) ,
                LEFT(NULLIF(LTRIM(RTRIM(HS.Debtor_1_Home_Phone)), ''), 500) ,
                LEFT(NULLIF(LTRIM(RTRIM(HS.Debtor_1_Mobile)), ''), 500) ,
                LEFT(NULLIF(LTRIM(RTRIM(HS.Debtor_1_Email)), ''), 500) ,
                NULLIF(HS.Repayment_Amount, 0) ,
                CASE WHEN NULLIF(HS.Repayment_Amount, 0) IS NOT NULL THEN REPFREQ.FrequencyID END ,
                CASE WHEN NULLIF(HS.Repayment_Amount, 0) IS NOT NULL THEN CAST(HS.Repay_Start_Date AS DATE) END ,
                CAST(HS.Extended_Debt_Code AS NVARCHAR(200)) ,
                'RCS Migration' ,
                NULLIF(LTRIM(RTRIM(CONCAT(NULLIF(LTRIM(RTRIM(HS.Other_Information)), ''),
                                          CASE WHEN NULLIF(LTRIM(RTRIM(HS.Other_Information)), '') IS NOT NULL
                                                AND NULLIF(LTRIM(RTRIM(HS.Additional_Information)), '') IS NOT NULL THEN CHAR(13) + CHAR(10) ELSE '' END,
                                          NULLIF(LTRIM(RTRIM(HS.Additional_Information)), '')))), '')
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardship H WITH ( NOLOCK ) ON H.Z_REF = CAST(HS.Extended_Debt_Code AS NVARCHAR(40))
                                                         AND H.AccountId = A.AccountID
                                                         AND H.CreateSessionID = {{CurrentSessionID}}
                INNER JOIN tblHardshipRequest R WITH ( NOLOCK ) ON R.AccountID = A.AccountID AND R.CreateSessionID = {{CurrentSessionID}}
                CROSS APPLY ( SELECT ISNULL(SUM(CASE WHEN RL.CapitalTypeID = 1 THEN RL.Amount END), 0)
                                   - ISNULL(SUM(CASE WHEN RL.CapitalTypeID = 2 THEN RL.Amount END), 0) AS Net
                              FROM   tblHardshipRequest_Line RL WITH ( NOLOCK )
                              WHERE  RL.HardshipRequestID = R.HardshipRequestID
                            ) NET
                OUTER APPLY ( SELECT TOP 1 FrequencyID
                              FROM   tblFrequency
                              WHERE  Frequency = LTRIM(RTRIM(HS.Repay_Frequency))
                              ORDER BY FrequencyID
                            ) REPFREQ
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1 FROM tblHardship_StatementVersion SV WITH ( NOLOCK ) WHERE SV.hardship_request_id = R.HardshipRequestID )
;

-- =====================================================================================
-- SOFP Section B document checklist. The app creates one check item per document type when
-- it requests a SOFP and stamps ReceivedTS / ProvidedBy when the customer supplies it. RCS
-- has three boxes; payslips and Centrelink statements share Debtrak type 3. Only hardships
-- whose extract row carries the checklist (the ones with a SOFP) get rows.
-- =====================================================================================
INSERT  INTO tblHardship_DocumentRequest WITH ( ROWLOCK )
        ( HardshipID, HardshipDocumentTypeID, RequestedTS, RequestedBy, ReceivedTS, ProvidedBy,
          StatusID, IsCheckItem, IsRequired, RequiredFrom )
        SELECT  H.HardshipID ,
                DOC.HardshipDocumentTypeID ,
                COALESCE(HS.Date_Sofp_Requested, HS.Date_Entered, HS.HS_Date_Triggered, H.CreateTS) ,
                LEFT(COALESCE(NULLIF(LTRIM(RTRIM(HS.Operator_Entered)), ''), 'RCS Migration'), 200) ,
                CASE WHEN DOC.Ticked = 1 THEN COALESCE(HS.Date_Entered, HS.HS_Date_Triggered, H.CreateTS) END ,
                CASE WHEN DOC.Ticked = 1 THEN 'customer' END ,
                1 ,
                1 ,
                1 ,
                'customer'
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardship H WITH ( NOLOCK ) ON H.Z_REF = CAST(HS.Extended_Debt_Code AS NVARCHAR(40))
                                                         AND H.AccountId = A.AccountID
                                                         AND H.CreateSessionID = {{CurrentSessionID}}
                CROSS APPLY ( SELECT CASE WHEN UPPER(LTRIM(RTRIM(HS.Checklist_Pay_Slips)))      IN ('1', 'Y', 'YES', 'TRUE') THEN 1 ELSE 0 END AS Pay ,
                                     CASE WHEN UPPER(LTRIM(RTRIM(HS.Checklist_Centrelink_Docs))) IN ('1', 'Y', 'YES', 'TRUE') THEN 1 ELSE 0 END AS Centrelink ,
                                     CASE WHEN UPPER(LTRIM(RTRIM(HS.Checklist_Medical_Docs)))    IN ('1', 'Y', 'YES', 'TRUE') THEN 1 ELSE 0 END AS Medical ,
                                     CASE WHEN UPPER(LTRIM(RTRIM(HS.Checklist_Other_Docs)))      IN ('1', 'Y', 'YES', 'TRUE') THEN 1 ELSE 0 END AS Other
                            ) F
                CROSS APPLY ( VALUES ( 3, CASE WHEN F.Pay = 1 OR F.Centrelink = 1 THEN 1 ELSE 0 END ),
                                     ( 5, F.Medical ),
                                     ( 7, F.Other )
                            ) DOC ( HardshipDocumentTypeID, Ticked )
        WHERE   A.LoadID = {{LoadID}}
                AND COALESCE(NULLIF(LTRIM(RTRIM(HS.Checklist_Pay_Slips)), ''), NULLIF(LTRIM(RTRIM(HS.Checklist_Centrelink_Docs)), ''),
                             NULLIF(LTRIM(RTRIM(HS.Checklist_Medical_Docs)), ''), NULLIF(LTRIM(RTRIM(HS.Checklist_Other_Docs)), '')) IS NOT NULL
                AND NOT EXISTS ( SELECT 1 FROM tblHardship_DocumentRequest DR WITH ( NOLOCK )
                                 WHERE  DR.HardshipID = H.HardshipID AND DR.HardshipDocumentTypeID = DOC.HardshipDocumentTypeID )
;

-- Preferred contact channel row, as the app writes when a customer picks how to be contacted.
-- Channel values are the app's own lower-case ones; the detail text is the SOFP email or
-- mobile, and ContactDetailID is filled when the primary debtor already has that value as a
-- contact detail (type 4 Email / type 2 Mobile).
INSERT  INTO tblHardship_PreferredContact WITH ( ROWLOCK )
        ( HardshipID, ContactID, ContactDetailID, AddressID, Channel, ContactDetail, CreateID, CreateTS )
        SELECT  H.HardshipID ,
                PRIMARYC.ContactID ,
                CD.ContactDetailID ,
                NULL ,
                PC.Channel ,
                LEFT(PC.Detail, 500) ,
                1 ,
                COALESCE(HS.Date_Entered, HS.HS_Date_Triggered, H.CreateTS)
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardship H WITH ( NOLOCK ) ON H.Z_REF = CAST(HS.Extended_Debt_Code AS NVARCHAR(40))
                                                         AND H.AccountId = A.AccountID
                                                         AND H.CreateSessionID = {{CurrentSessionID}}
                CROSS APPLY ( SELECT CASE UPPER(LTRIM(RTRIM(HS.Preferred_Hardship_Contact_Method)))
                                         WHEN 'EMAIL' THEN 'email'
                                         WHEN 'SMS' THEN 'mobile'
                                         WHEN 'MOBILE' THEN 'mobile'
                                     END AS Channel ,
                                     CASE UPPER(LTRIM(RTRIM(HS.Preferred_Hardship_Contact_Method)))
                                         WHEN 'EMAIL' THEN NULLIF(LTRIM(RTRIM(HS.Debtor_1_Email)), '')
                                         ELSE NULLIF(LTRIM(RTRIM(HS.Debtor_1_Mobile)), '')
                                     END AS Detail
                            ) PC
                OUTER APPLY ( SELECT TOP 1 AC.ContactID
                              FROM   tblAccount_Contact AC WITH ( NOLOCK )
                              WHERE  AC.AccountID = A.AccountID
                                     AND AC.RelationshipID = {{RelationshipID_PrimaryDebtor}}
                              ORDER BY AC.DisplayOrder, AC.ContactID
                            ) PRIMARYC
                OUTER APPLY ( SELECT TOP 1 CDX.ContactDetailID
                              FROM   tblContactDetail CDX WITH ( NOLOCK )
                              WHERE  CDX.ContactID = PRIMARYC.ContactID
                                     AND CDX.ContactDetailTypeID = CASE PC.Channel WHEN 'email' THEN 4 ELSE 2 END
                                     AND REPLACE(LTRIM(RTRIM(CDX.ContactDetail)), ' ', '') = REPLACE(PC.Detail, ' ', '')
                              ORDER BY CDX.IsPrimary DESC, CDX.ContactDetailID
                            ) CD
        WHERE   A.LoadID = {{LoadID}}
                AND PC.Channel IS NOT NULL
                AND PC.Detail IS NOT NULL
                AND NOT EXISTS ( SELECT 1 FROM tblHardship_PreferredContact P WITH ( NOLOCK )
                                 WHERE  P.HardshipID = H.HardshipID AND P.Channel = PC.Channel )
;

-- Outcome decision for every hardship RCS has decided. The app writes exactly one of these
-- when an operator accepts, declines or records a withdrawal, pointing at the SOFP request it
-- was decided on. Legacy decline / withdraw reasons map through tblHardshipOutcome_Reason
-- (legacy_reason_kind + legacy_reason_id), which also carries the DeclineReasonCode the app
-- stores beside it.
INSERT  INTO tblHardshipOutcome_Decision WITH ( ROWLOCK )
        ( hardship_id, outcome_id, reason_id, detail, decided_by, decided_at,
          decided_on_hardship_request_id, DeclineReasonCode, NoticeChannelCode, ConsentConfirmed, DecidedByContactID )
        SELECT  H.HardshipID ,
                OUTC.id ,
                RSN.id ,
                NULL ,
                'RCS Migration' ,
                DEC.DecidedAt ,
                R.HardshipRequestID ,
                RSN.DeclineReasonCode ,
                CASE UPPER(LTRIM(RTRIM(HS.Preferred_Hardship_Contact_Method))) WHEN 'EMAIL' THEN 'Email' WHEN 'LETTER' THEN 'Letter' END ,
                NULL ,
                NULL
        FROM    RC_HARDSHIP_EXTRACT HS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = HS.Extended_Debt_Code
                INNER JOIN tblHardship H WITH ( NOLOCK ) ON H.Z_REF = CAST(HS.Extended_Debt_Code AS NVARCHAR(40))
                                                         AND H.AccountId = A.AccountID
                                                         AND H.CreateSessionID = {{CurrentSessionID}}
                LEFT JOIN tblHardshipRequest R WITH ( NOLOCK ) ON R.AccountID = A.AccountID AND R.CreateSessionID = {{CurrentSessionID}}
                CROSS APPLY ( SELECT CASE WHEN HS.Withdrawn_Date IS NOT NULL OR H.HardshipWithdrawStatusIID IS NOT NULL THEN 'withdrawn'
                                          WHEN HS.Declined_Date IS NOT NULL OR H.HardshipDeclinedStatusID IS NOT NULL THEN 'declined'
                                          WHEN HS.Assessment_Result = 'Hardship Accepted' OR H.HardshipAccepted = 1 THEN 'accepted'
                                     END AS Kind ,
                                     COALESCE(HS.Withdrawn_Date, HS.Declined_Date, HS.Approved_Date, HS.Date_Entered, H.CreateTS) AS DecidedAt
                            ) DEC
                OUTER APPLY ( SELECT TOP 1 O.id
                              FROM   tblHardship_Outcome O
                              WHERE  O.code = CASE DEC.Kind
                                                  WHEN 'accepted' THEN CASE WHEN HS.Moratorium_Start IS NOT NULL THEN 'accept-moratorium' ELSE 'accept-arrangement' END
                                                  ELSE 'decline'
                                              END
                              ORDER BY O.is_active DESC, O.id
                            ) OUTC
                OUTER APPLY ( SELECT TOP 1 RR.id, RR.DeclineReasonCode
                              FROM   tblHardshipOutcome_Reason RR
                              WHERE  RR.outcome_id = OUTC.id
                                     AND ( ( DEC.Kind = 'declined'  AND RR.legacy_reason_kind = 'decline'  AND RR.legacy_reason_id = H.HardshipDeclinedStatusID )
                                        OR ( DEC.Kind = 'withdrawn' AND RR.legacy_reason_kind = 'withdraw' AND RR.legacy_reason_id = H.HardshipWithdrawStatusIID ) )
                              ORDER BY RR.is_active DESC, RR.id
                            ) RSN
        WHERE   A.LoadID = {{LoadID}}
                AND DEC.Kind IS NOT NULL
                AND OUTC.id IS NOT NULL
                AND NOT EXISTS ( SELECT 1 FROM tblHardshipOutcome_Decision D WITH ( NOLOCK ) WHERE D.hardship_id = H.HardshipID )
;
