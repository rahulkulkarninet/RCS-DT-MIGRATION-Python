-- Z_REF carries CMP.ZID, the same way Z_REF/Z_ID carry the source key on tblPayment/
-- tblSMSOutput elsewhere in this folder, so the child inserts below can re-join the rows
-- just inserted. CMP_Complaint_Number can't serve that purpose: it's a small per-debt
-- sequence, not unique across accounts, whereas ZID is unique per source row.
--
-- tblComplaint had no Z_REF/Z_ID columns of its own (unlike its sibling framework tables),
-- so one was added (ALTER TABLE tblComplaint ADD Z_REF NVARCHAR(400) NULL) rather than
-- reusing ClientReferenceNumber for this. ClientReferenceNumber is a real client-facing
-- field - "Complaints Data Mapping.xlsx" confirms it holds the client's own case number
-- (6 of 17 real client reports carry it as "Client Reference"/"Client Reference Number"/
-- "Supplier Reference"). This customer's extract has no such column, so it is correctly
-- left NULL here rather than overloaded with the internal correlation key, which would
-- have silently destroyed a future client's real reference number.
--
-- CMP_Source and CMP_Issue_1/2/3 are normalized to tblComplainant.Name/tblComplaintRoot.RootCause
-- in place, before this file runs, by update_complainants/update_complaint_roots (see
-- complainant_service.py/complaint_root_service.py and variables/complainant_codes.json,
-- variables/complaint_root_codes.json) - the same mechanism RC_ACCOUNT_EXTRACT.MA_Status
-- and .Reason_Closed go through. A value with no mapping and no configured default is left
-- as-is and reported invalid rather than guessed at here.
--
-- Cross-checked against "Complaints Data Mapping.xlsx" (dev-debtrak schema, 08-Sep-2026):
-- ComplaintReference is cast to NVARCHAR(20) to match that column's actual width (was
-- previously cast to 40, an oversized cast that risked a truncation error for a customer
-- with a longer CMP_Complaint_Number than this one's). ComplaintPriorityId/
-- ComplaintSeverityId were added below since CMP_Priority/CMP_Severity are available
-- source columns with real "has-home" target FKs that nothing was previously wiring up
-- (empty for this customer's data, but not for every customer). ComplaintRootId/
-- ComplaintRootSecondaryId on the main row are confirmed as a legacy/deliberate
-- divergence in that document - tblComplaintIssue below is the model's real home for
-- root cause, so those two main-row columns are populated for legacy compatibility only.
INSERT  INTO tblComplaint WITH ( ROWLOCK )
        ( AccountId ,
          DateReceived ,
          ComplainantId ,
          ComplaintTypeId ,
          ComplaintMethodId ,
          Summary ,
          ExpectedOutcome ,
          CallBack ,
          CustomerImpact ,
          ReviewDate ,
          RegulatoryReferral ,
          RegulatoryReferralDate ,
          SentDate ,
          ComplaintRootId ,
          ComplaintRootSecondaryId ,
          CommunicationPreferenceID ,
          ComplaintOutcomeId ,
          ComplaintSourceId ,
          ComplaintOriginatorId ,
          ComplaintLevelId ,
          Resolved ,
          ResolvedDate ,
          ComplaintReference ,
          RegulatoryCaseNumber ,
          DefaultListingRemoved ,
          ActionTaken ,
          ComplaintUpheldID ,
          ComplaintPriorityId ,
          ComplaintSeverityId ,
          CreateId ,
          CreateSessionId ,
          CreateTS ,
          CustomerImpactDetails ,
          DecisionInformationRequestedComplainant ,
          ResolutionDetails ,
          ZendeskTicketNumber ,
          ClientReferralDate ,
          Z_REF ,
          OmbudsmanResponseDueDate ,
          ClientCode ,
          AccountReference ,
          OwnershipStatus ,
          LodgedByTeamCode ,
          IsDraft ,
          Classification ,
          IsRestrictedVisibility
        )
        SELECT  A.AccountID ,
                CMP.CMP_Made_Date ,
                COMPL.ComplainantId ,
                1 ,
                ISNULL(METH.ComplaintMethodId, ( SELECT ComplaintMethodId FROM tblComplaintMethod WHERE Method = 'Other' )) ,
                CMP.CMP_Details ,
                CMP.CMP_Expected_Outcome ,
                CASE WHEN CMP.CMP_Callback IS NULL THEN NULL
                     WHEN CMP.CMP_Callback = 'No call back required' THEN 0
                     ELSE 1 END ,
                CASE CMP.CMP_Impact WHEN 'Yes' THEN 1 WHEN 'No' THEN 0 END ,
                CMP.CMP_Review_Date ,
                CASE CMP.CMP_Referred_From_AFCA WHEN 'Yes' THEN 1 WHEN 'No' THEN 0 END ,
                CMP.CMP_AFCA_Referred_Date ,
                CMP.CMP_Info_Sent_Date ,
                ROOT1.ComplaintRootId ,
                ROOTSEC1.ComplaintRootSecondaryID ,
                COMMPREF.CommunicationPreferenceID ,
                OUTCM.ComplaintOutcomeId ,
                SRCLK.ComplaintSourceID ,
                ORIG.ComplaintOriginatorID ,
                LVL.ComplaintLevelID ,
                CASE WHEN CMP.CMP_Status LIKE '%CLS%' OR CMP.CMP_Status LIKE '%CLOSED%' THEN 1 ELSE 0 END ,
                CASE WHEN CMP.CMP_Status LIKE '%CLS%' OR CMP.CMP_Status LIKE '%CLOSED%' THEN CMP.CMP_Status_Date END ,
                CAST(CMP.CMP_Complaint_Number AS NVARCHAR(20)) ,
                CMP.Afca_Case_Number ,
                CASE CMP.CMP_Default_Listing_Removed WHEN 'Yes' THEN 1 WHEN 'No' THEN 0 END ,
                CMP.CMP_Action_Taken ,
                UPHELD.ComplaintUpheldID ,
                PRIOR.ComplaintPriorityID ,
                SEV.ComplaintSeverityID ,
                1 ,
                {{CurrentSessionID}} ,
                CMP.CMP_Enter_date ,
                CMP.CMP_Impact_Details ,
                CASE CMP.CMP_Info_Requested WHEN 'Yes' THEN 1 WHEN 'No' THEN 0 END ,
                CMP.CMP_Outcome ,
                CMP.Zendesk_Ticket_Number ,
                CMP.CMP_Referred_to_Client_Date ,
                CMP.ZID ,
                CMP.CMP_AFCA_Date_Required ,
                CMP.Client_Code ,
                CAST(CMP.Extended_Debt_Code AS NVARCHAR(50)) ,
                CMP.CMP_Ownership ,
                CMP.CMP_Logged_By ,
                0 ,
                'COMPLAINT' ,
                0
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplainant COMPL ON COMPL.Name = CMP.CMP_Source
                -- OUTER/CROSS APPLY TOP 1, not a plain JOIN: several of these lookups carry
                -- multiple rows per label (test-debtrak has tblComplaintSource/tblComplaintOriginator
                -- 3x each, tblComplaintRoot 2-3x for a couple of values - likely per-client/tenant
                -- copies), so a plain join fans a single complaint out into duplicates, the same
                -- reason 01.tblaccount.sql uses this pattern for tblProduct. ORDER BY the id keeps
                -- the row chosen deterministic between runs.
                OUTER APPLY ( SELECT TOP 1 ComplaintMethodId
                              FROM   tblComplaintMethod
                              WHERE  Method = CMP.CMP_Received_Via
                              ORDER BY ComplaintMethodId
                            ) METH
                OUTER APPLY ( SELECT TOP 1 ComplaintRootId
                              FROM   tblComplaintRoot
                              WHERE  RootCause = CMP.CMP_Issue_1
                              ORDER BY ComplaintRootId
                            ) ROOT1
                OUTER APPLY ( SELECT TOP 1 ComplaintRootSecondaryID
                              FROM   tblComplaintRootSecondary
                              WHERE  ComplaintRootSecondary = CMP.CMP_Sub_Issue_1
                                     AND ComplaintRootID = ROOT1.ComplaintRootId
                              ORDER BY ComplaintRootSecondaryID
                            ) ROOTSEC1
                OUTER APPLY ( SELECT TOP 1 CommunicationPreferenceID
                              FROM   tblCommunicationPreference
                              WHERE  CommunicationPreference = CMP.CMP_Preferred_Contact
                              ORDER BY CommunicationPreferenceID
                            ) COMMPREF
                OUTER APPLY ( SELECT TOP 1 ComplaintOutcomeId
                              FROM   tblComplaintOutcome
                              WHERE  Outcome = CASE
                                         WHEN CMP.CMP_Status LIKE '%CLS%' OR CMP.CMP_Status LIKE '%CLOSED%' THEN 'Completed'
                                         WHEN CMP.CMP_Status LIKE '%HOLD%' THEN 'Pending'
                                     END
                              ORDER BY ComplaintOutcomeId
                            ) OUTCM
                OUTER APPLY ( SELECT TOP 1 ComplaintSourceID
                              FROM   tblComplaintSource
                              WHERE  Source = CASE WHEN CMP.CMP_Source = 'Customer via rep' THEN 'Authorised Representative' ELSE CMP.CMP_Source END
                              ORDER BY ComplaintSourceID
                            ) SRCLK
                OUTER APPLY ( SELECT TOP 1 ComplaintOriginatorID
                              FROM   tblComplaintOriginator
                              WHERE  OriginatorType = CMP.CMP_Entity
                              ORDER BY ComplaintOriginatorID
                            ) ORIG
                OUTER APPLY ( SELECT TOP 1 ComplaintLevelID
                              FROM   tblComplaintLevel
                              WHERE  Level = CASE WHEN CMP.CMP_Escalate_To = 'Government bodies / agencies' THEN 'Other Government/bodies' ELSE CMP.CMP_Escalate_To END
                              ORDER BY ComplaintLevelID
                            ) LVL
                OUTER APPLY ( SELECT TOP 1 ComplaintUpheldID
                              FROM   tblComplaintUpheld
                              WHERE  ComplaintUpheld = CASE WHEN CMP.CMP_Warranted = 'Not Sure' THEN 'Not sure' ELSE CMP.CMP_Warranted END
                              ORDER BY ComplaintUpheldID
                            ) UPHELD
                OUTER APPLY ( SELECT TOP 1 ComplaintPriorityID
                              FROM   tblComplaintPriority
                              WHERE  PriorityLevel = CMP.CMP_Priority
                              ORDER BY ComplaintPriorityID
                            ) PRIOR
                OUTER APPLY ( SELECT TOP 1 ComplaintSeverityID
                              FROM   tblComplaintSeverity
                              WHERE  SeverityLevel = CMP.CMP_Severity
                              ORDER BY ComplaintSeverityID
                            ) SEV
        WHERE   A.LoadID = {{LoadID}}
;

-- tblComplaintAccountLink is the new many-to-many linking table (replacing a single AccountId
-- FK as the only way to associate a complaint with a debt); one originating link per complaint.
INSERT  INTO tblComplaintAccountLink WITH ( ROWLOCK )
        ( ComplaintID, AccountID, ClientCode, IsOriginating, LinkedBy, CreateTS )
        SELECT  C.ComplaintId, A.AccountID, CMP.Client_Code, 1, 'Migration', GETUTCDATE()
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.Z_REF = CMP.ZID
                                                          AND C.AccountId = A.AccountID
                                                          AND C.CreateSessionId = {{CurrentSessionID}}
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1 FROM tblComplaintAccountLink L WITH ( NOLOCK ) WHERE L.ComplaintID = C.ComplaintId )
;

INSERT  INTO tblComplaintIssue WITH ( ROWLOCK )
        ( ComplaintID, ComplaintRootID, ComplaintRootSecondaryID, CreateID, CreateSessionId, CreateTS, Position )
        SELECT  C.ComplaintId, R.ComplaintRootId, RS.ComplaintRootSecondaryID, 1, {{CurrentSessionID}}, GETDATE(), 1
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.Z_REF = CMP.ZID
                                                          AND C.AccountId = A.AccountID
                                                          AND C.CreateSessionId = {{CurrentSessionID}}
                CROSS APPLY ( SELECT TOP 1 ComplaintRootId FROM tblComplaintRoot WHERE RootCause = CMP.CMP_Issue_1 ORDER BY ComplaintRootId ) R
                OUTER APPLY ( SELECT TOP 1 ComplaintRootSecondaryID FROM tblComplaintRootSecondary
                              WHERE ComplaintRootSecondary = CMP.CMP_Sub_Issue_1 AND ComplaintRootID = R.ComplaintRootId
                              ORDER BY ComplaintRootSecondaryID ) RS
        WHERE   A.LoadID = {{LoadID}}
                AND CMP.CMP_Issue_1 IS NOT NULL
                AND NOT EXISTS ( SELECT 1 FROM tblComplaintIssue I WITH ( NOLOCK ) WHERE I.ComplaintID = C.ComplaintId AND I.Position = 1 )
;

INSERT  INTO tblComplaintIssue WITH ( ROWLOCK )
        ( ComplaintID, ComplaintRootID, ComplaintRootSecondaryID, CreateID, CreateSessionId, CreateTS, Position )
        SELECT  C.ComplaintId, R.ComplaintRootId, RS.ComplaintRootSecondaryID, 1, {{CurrentSessionID}}, GETDATE(), 2
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.Z_REF = CMP.ZID
                                                          AND C.AccountId = A.AccountID
                                                          AND C.CreateSessionId = {{CurrentSessionID}}
                CROSS APPLY ( SELECT TOP 1 ComplaintRootId FROM tblComplaintRoot WHERE RootCause = CMP.CMP_Issue_2 ORDER BY ComplaintRootId ) R
                OUTER APPLY ( SELECT TOP 1 ComplaintRootSecondaryID FROM tblComplaintRootSecondary
                              WHERE ComplaintRootSecondary = CMP.CMP_Sub_Issue_2 AND ComplaintRootID = R.ComplaintRootId
                              ORDER BY ComplaintRootSecondaryID ) RS
        WHERE   A.LoadID = {{LoadID}}
                AND CMP.CMP_Issue_2 IS NOT NULL
                AND NOT EXISTS ( SELECT 1 FROM tblComplaintIssue I WITH ( NOLOCK ) WHERE I.ComplaintID = C.ComplaintId AND I.Position = 2 )
;

INSERT  INTO tblComplaintIssue WITH ( ROWLOCK )
        ( ComplaintID, ComplaintRootID, ComplaintRootSecondaryID, CreateID, CreateSessionId, CreateTS, Position )
        SELECT  C.ComplaintId, R.ComplaintRootId, RS.ComplaintRootSecondaryID, 1, {{CurrentSessionID}}, GETDATE(), 3
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.Z_REF = CMP.ZID
                                                          AND C.AccountId = A.AccountID
                                                          AND C.CreateSessionId = {{CurrentSessionID}}
                CROSS APPLY ( SELECT TOP 1 ComplaintRootId FROM tblComplaintRoot WHERE RootCause = CMP.CMP_Issue_3 ORDER BY ComplaintRootId ) R
                OUTER APPLY ( SELECT TOP 1 ComplaintRootSecondaryID FROM tblComplaintRootSecondary
                              WHERE ComplaintRootSecondary = CMP.CMP_Sub_Issue_3 AND ComplaintRootID = R.ComplaintRootId
                              ORDER BY ComplaintRootSecondaryID ) RS
        WHERE   A.LoadID = {{LoadID}}
                AND CMP.CMP_Issue_3 IS NOT NULL
                AND NOT EXISTS ( SELECT 1 FROM tblComplaintIssue I WITH ( NOLOCK ) WHERE I.ComplaintID = C.ComplaintId AND I.Position = 3 )
;

INSERT  INTO TblComplaintHistories WITH ( ROWLOCK )
        ( ComplaintId, ActionTaken, CreateId, CreateSessionId, CreateTs, StatusId, Action, Status, ChangedBy )
        SELECT  C.ComplaintId, 'Migrated from RC_COMPLAINT_EXTRACT', 1, {{CurrentSessionID}}, SYSDATETIME(), 1,
                'Migrated from RC_COMPLAINT_EXTRACT', CMP.CMP_Status, 'Migration'
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.Z_REF = CMP.ZID
                                                          AND C.AccountId = A.AccountID
                                                          AND C.CreateSessionId = {{CurrentSessionID}}
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1 FROM TblComplaintHistories H WITH ( NOLOCK ) WHERE H.ComplaintId = C.ComplaintId )
;
