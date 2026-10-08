-- ClientReferenceNumber carries CMP_Complaint_Number (the client's own case number) -
-- added 2026-09-23 on merge with Rahul's Treatment/Hardship work. ComplaintReference here
-- holds the internal ZID instead (for the child-table joins below), so CMP_Complaint_Number
-- needed a different home rather than being dropped - ClientReferenceNumber was free and is
-- the closest semantic fit on tblComplaint.
--
-- 2026-10-02: the extract grew from 51 to 76 columns (SM9641 re-issue, SM9595). The blank
-- 35th header is now CMP_Info_Req_Date, and 25 closure/history columns follow
-- Client_Transfer_Date. What changed here because of that:
--
--   Resolved / ResolvedDate / ClosedDate / ClosedBy now come from the Resolved,
--   Resolved_Date, Closed_Date and Cct_Officer_Closing_Complaint columns. They used to be
--   inferred from CMP_Status, which turns out to be the status of the DEBT (COMPLAINTHOLD,
--   PTPB, NEG, ...) rather than of the complaint: 422 of the 656 SM9641 + SM9595 complaints
--   carry a Closed Date while CMP_Status is not a CLS/CLOSED code, and every one of them
--   was migrating as open. The CMP_Status inference survives only as the fallback for a
--   51-column extract (CG8110), recognised by Audit_Action being NULL - every row of a
--   76-column extract has an audit trail. ComplaintOutcomeId follows the same signal.
--
--   A resolved complaint is a closed complaint (Stacey, Complaints/Hardship Mapping chat,
--   2026-10-01), so a row that is Resolved = Yes with no Closed Date closes on its
--   Resolved_Date. A closed complaint is also written the way the application writes one
--   it closed itself (test-debtrak, 2026-10-02): ComplaintResolutionStageID = Closed and
--   ActualOutcomeDate alongside ResolvedDate / ClosedDate. Her 2026-09-16 report of cases
--   coming through as closed but with no dates was these columns being empty.
--
--   ResolutionDetails is Resolution_Details. It used to be CMP_Outcome, which is not text
--   at all but the code of the outcome picked in RCS - see ComplaintOutcomeId below.
--
--   New targets: RequestedDate (CMP_Info_Req_Date),
--   ResolutionMethodId (Resolution_Method), MonetaryCompensationProvided / Amount
--   (Monetary_Compensation / Compensation_Amount), ComplaintAssistanceId and
--   AdditionalAssistanceRequired (Additional_Assistance), ComplainantName / Phone / Email
--   (Unauth_Third_Party_Name / Phone / Email).
--
--   Closure_Reason is not carried over as a closure reason: Debtrak has no list for it and
--   Stacey does not want one (2026-10-02: "RCS ... had outcome reason and closure reason.
--   outcome reason is enough"). It decides the outcome instead - see ComplaintOutcomeId.
--
--   The unauthorised third party goes on the complaint row itself because that is where
--   the application keeps it: on test-debtrak every Unauthorised Third Party complaint
--   lodged through the UI has ComplainantName (and Phone / Email when known) filled, and
--   tblComplaintThirdPartyContact is empty.
--
--   TblComplaintHistories now gets the audit trail, the status history and the documents
--   sent, one row per entry of the pipe-delimited lists - see the last statement.
--
--   ClientReferenceNumber takes Westpac_Ref_Number (the Client Reference Number of the
--   legacy Client Fields box) when the extract has one, CMP_Complaint_Number otherwise.
--
--   ComplaintOutcomeId is the ASIC IDR outcome, decided by Closure_Reason exactly as
--   Stacey set it out in the Complaints/Hardship Mapping chat on 2026-10-02:
--       ... in our favour                          -> No remedy provided/apology or explanation only
--       ... in customers favour                    -> Service-based remedy
--       Referred back to client (not our jurisdiction) -> Referred to another financial firm
--       Complaint resolved with AFCA in our favour -> No remedy provided/apology or explanation only
--       Duplicate                                  -> Withdrawn/discontinued
--       No further contact from customer or rep    -> Withdrawn/discontinued
--       closed with no closure reason recorded     -> Other remedy
--   An open complaint has no outcome, as in the application. A closure reason outside this
--   list is left without an outcome rather than guessed. A 51-column extract has no
--   Closure_Reason column at all, so its complaints get no outcome either - that is a
--   missing column, not "no reason recorded", and must not be turned into Other remedy.
--   Completed / Pending, written before, are inactive on test-debtrak (StatusId 2) and are
--   no longer used. tblComplaintAsicOutcome gets the same outcome at Position 1, which is
--   what the application writes when a complaint is closed through the UI.
--
--   CMP_Outcome. RCS changed the extract on 2026-10-05 (Cheneeth, "complaints update.pdf"):
--   the column now carries the outcome DESCRIPTION picked in RCS instead of a code. Which
--   source decides the Debtrak outcome is the one-letter OPT.Source switch in the FROM
--   clause below, matching the three options put to Stacey on 2026-10-06:
--       A  closure reason first, RCS outcome text only where the closure reason is blank
--       B  closure reason only, Other remedy when blank (as agreed 2026-10-02 - CURRENT)
--       C  RCS outcome text first, closure reason as the fallback
--   The text is matched after dropping spaces, both against the Debtrak labels themselves
--   (RCS uses the same ASIC vocabulary for its newer outcomes, with one misspelling) and
--   against the legacy RCS phrases whose ASIC outcome is known from report
--   3. Complaints - ASIC.xlsx: explanation / explanation and apology -> No remedy, provision
--   of assistance and support -> Service-based remedy, referred back to client (not in
--   jurisdiction) -> Referred to another financial firm, referred back to client as remedy
--   -> Other remedy, refund or waiver of a fee -> Monetary remedy, correcting records ->
--   Service-based remedy. Anything else (Unknown, resolution pending, same day) maps to
--   nothing and falls through to the closure reason. The numeric codes of the old extract
--   are not mapped: Stacey asked for them to be left out.
--
--   AuthorisedRep is AFS_Licensee (Yes / No; Unknown stays NULL). Complaints Data
--   Mapping.xlsx gives AuthorisedRep as the home of the RG 271 ComplaintAboutRep question.
--
--   DueDate (the SLA) is DateReceived + 29 days, added 2026-10-07 after Stacey reported
--   (2026-10-06) that migrated complaints came across with no SLA. That is what the
--   application itself writes, checked on test-debtrak: every COMPLAINT it lodges has
--   DueDate = DateReceived + 29 (day 30 of the 30-day profile) and no ComplaintSlaProfileID
--   stored - the profile is resolved at run time from tblComplaintSlaRule. Of those rules,
--   the 21-day one needs Classification DISPUTE and the N-day one OMBUDSMAN; every migrated
--   complaint is COMPLAINT, so the 30-day window applies to all of them regardless of issue
--   or sub-issue, and the application leaves drafts and OMBUDSMAN cases without a DueDate.
--
-- Staged but deliberately not migrated, each confirmed with Stacey on 2026-10-02:
-- Resolution_Operator (the operator-error name; she does not want it carried over),
-- Unauth_Third_Party_DOB / Age / Address, and CMP_Outcome. The Westpac_* client-fields
-- columns other than the reference number are also not migrated yet: blank for SM9641 and
-- SM9595, but needed once a banking or insurance client is migrated.
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
          ClosedDate ,
          ClosedBy ,
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
          OmbudsmanResponseDueDate ,
          ClientCode ,
          AccountReference ,
          OwnershipStatus ,
          LodgedByTeamCode ,
          IsDraft ,
          Classification ,
          IsRestrictedVisibility ,
          ClientReferenceNumber ,
          RequestedDate ,
          ResolutionMethodId ,
          MonetaryCompensationProvided ,
          MonetaryCompensationAmount ,
          ComplaintAssistanceId ,
          AdditionalAssistanceRequired ,
          ComplainantName ,
          ComplainantPhone ,
          ComplainantEmail ,
          ActualOutcomeDate ,
          ComplaintResolutionStageID ,
          AuthorisedRep ,
          DueDate
        )
        SELECT  A.AccountID ,
                CMP.CMP_Made_Date ,
                ISNULL(COMPL.ComplainantId, COMPLDEF.ComplainantId) ,
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
                CLS.Resolved ,
                CASE WHEN CLS.Resolved = 1 THEN ISNULL(CMP.Resolved_Date, CLS.ClosedDate) END ,
                CLS.ClosedDate ,
                CASE WHEN CLS.ClosedDate IS NOT NULL THEN ISNULL(CMP.Cct_Officer_Closing_Complaint, 'Migration') END ,
                CAST(CMP.ZID AS NVARCHAR(40)) ,
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
                CMP.Resolution_Details ,
                CMP.Zendesk_Ticket_Number ,
                CMP.CMP_Referred_to_Client_Date ,
                CMP.CMP_AFCA_Date_Required ,
                'RCS' ,
                CAST(CMP.Extended_Debt_Code AS NVARCHAR(50)) ,
                CMP.CMP_Ownership ,
                CMP.CMP_Logged_By ,
                0 ,
                'COMPLAINT' ,
                0 ,
                ISNULL(LEFT(CMP.Westpac_Ref_Number, 50), CAST(CMP.CMP_Complaint_Number AS NVARCHAR(50))) ,
                CMP.CMP_Info_Req_Date ,
                RESMETH.ResolutionMethodID ,
                CASE CMP.Monetary_Compensation WHEN 'Yes' THEN 1 WHEN 'No' THEN 0 END ,
                CASE WHEN CMP.Compensation_Amount IS NULL OR LTRIM(RTRIM(CMP.Compensation_Amount)) = '' THEN NULL
                     ELSE TRY_CAST(REPLACE(REPLACE(CMP.Compensation_Amount, '$', ''), ',', '') AS DECIMAL(18,2)) END ,
                ASSIST.ComplaintAssistanceID ,
                CASE WHEN CMP.Additional_Assistance IS NOT NULL THEN 1 END ,
                LEFT(CMP.Unauth_Third_Party_Name, 255) ,
                LEFT(CMP.Unauth_Third_Party_Phone, 30) ,
                LEFT(CMP.Unauth_Third_Party_Email, 254) ,
                CASE WHEN CLS.Resolved = 1 THEN ISNULL(CMP.Resolved_Date, CLS.ClosedDate) END ,
                CASE WHEN CLS.ClosedDate IS NOT NULL THEN STAGE.ComplaintResolutionStageID END ,
                CASE CMP.AFS_Licensee WHEN 'Yes' THEN 1 WHEN 'No' THEN 0 END ,
                DATEADD(day, 29, CMP.CMP_Made_Date)
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                -- CMP_Source as sent; a source tblComplainant does not name (AFCA, blank)
                -- is filed under 'Unknown' rather than dropping the complaint.
                OUTER APPLY ( SELECT TOP 1 ComplainantId
                              FROM   tblComplainant
                              WHERE  Name = LTRIM(RTRIM(CMP.CMP_Source))
                              ORDER BY ComplainantId
                            ) COMPL
                OUTER APPLY ( SELECT TOP 1 ComplainantId
                              FROM   tblComplainant
                              WHERE  Name = 'Unknown'
                              ORDER BY ComplainantId
                            ) COMPLDEF
                -- Closure comes from the extract columns. LegacyClosed is the old CMP_Status
                -- inference, applied only to a row with no audit trail, which is what a row
                -- of a 51-column extract looks like once staged (see the top of this file).
                CROSS APPLY ( SELECT CASE WHEN CMP.Audit_Action IS NULL
                                               AND ( CMP.CMP_Status LIKE '%CLS%' OR CMP.CMP_Status LIKE '%CLOSED%' )
                                          THEN 1 ELSE 0 END AS LegacyClosed
                            ) LEG
                CROSS APPLY ( SELECT CASE CMP.Resolved WHEN 'Yes' THEN 1 WHEN 'No' THEN 0 ELSE LEG.LegacyClosed END AS Resolved ,
                                     COALESCE(CMP.Closed_Date,
                                              CASE WHEN CMP.Resolved = 'Yes' THEN CMP.Resolved_Date END,
                                              CASE WHEN LEG.LegacyClosed = 1 THEN CMP.CMP_Status_Date END) AS ClosedDate
                            ) CLS

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
                -- Outcome. RSN is the closure-reason rule Stacey set out (see the top of this
                -- file), TXT the RCS outcome description, DFLT what a closed complaint with no
                -- closure reason gets. OPT.Source picks how they combine - change the one letter
                -- when Stacey answers; nothing else in this file depends on it. The extract
                -- drops the apostrophe from the closure reason (in customers favour), so it is
                -- compared without one. Spaces are ignored on the outcome label because it has
                -- been stored both as "provided/apology" and "provided/ apology"; an active
                -- row is preferred.
                CROSS APPLY ( SELECT 'B' AS Source ) OPT
                CROSS APPLY ( SELECT REPLACE(REPLACE(LTRIM(RTRIM(CMP.Closure_Reason)), '''', ''), NCHAR(8217), '') AS Reason ,
                                     REPLACE(LOWER(LTRIM(RTRIM(CMP.CMP_Outcome))), ' ', '') AS OutcomeText
                            ) CR
                CROSS APPLY ( SELECT CASE
                                         WHEN CR.Reason IN ( 'Complaint resolved with customer or representative in our favour',
                                                             'Complaint resolved with AFCA in our favour' )
                                              THEN 'No remedy provided/apology or explanation only'
                                         WHEN CR.Reason = 'Complaint resolved with customer or representative in customers favour'
                                              THEN 'Service-based remedy'
                                         WHEN CR.Reason = 'Referred back to client as not within our jurisdiction'
                                              THEN 'Referred to another financial firm'
                                         WHEN CR.Reason IN ( 'Duplicate', 'No further contact from customer or representative' )
                                              THEN 'Withdrawn/discontinued'
                                     END AS Label
                            ) RSN
                CROSS APPLY ( SELECT CASE
                                         WHEN CR.OutcomeText IN ( 'noremedyprovided/apologyorexplanationonly', 'noremedyprovided/apologyorexpalantiononly',
                                                                  'anexplanationofthecircumstancesgivingrisetothecomplaint',
                                                                  'anexplanationofthecircumstancesgivingrisetothecomplaintandanapology' )
                                              THEN 'No remedy provided/apology or explanation only'
                                         WHEN CR.OutcomeText IN ( 'service-basedremedy', 'provisionofassistanceandsupport', 'correctingincorrectorout-of-daterecords' )
                                              THEN 'Service-based remedy'
                                         WHEN CR.OutcomeText IN ( 'referredtoanotherfinancialfirm', 'referredbacktoclient(notinjurisdiction)' )
                                              THEN 'Referred to another financial firm'
                                         WHEN CR.OutcomeText IN ( 'otherremedy', 'referredbacktoclientasremedy' )
                                              THEN 'Other remedy'
                                         WHEN CR.OutcomeText IN ( 'monetaryremedy', 'arefundorwaiverofafeeorcharge' )
                                              THEN 'Monetary remedy'
                                         WHEN CR.OutcomeText = 'contract/policyvariation' THEN 'Contract/policy variation'
                                         WHEN CR.OutcomeText = 'decisionchanged'          THEN 'Decision changed'
                                         WHEN CR.OutcomeText = 'withdrawn/discontinued'   THEN 'Withdrawn/discontinued'
                                     END AS Label
                            ) TXT
                CROSS APPLY ( SELECT CASE WHEN CR.Reason IS NULL AND ( CLS.Resolved = 1 OR CLS.ClosedDate IS NOT NULL ) THEN 'Other remedy' END AS Label ) DFLT
                OUTER APPLY ( SELECT TOP 1 ComplaintOutcomeId
                              FROM   tblComplaintOutcome
                              WHERE  REPLACE(Outcome, ' ', '') = REPLACE(CASE
                                         WHEN CMP.Audit_Action IS NULL THEN NULL
                                         WHEN OPT.Source = 'A' THEN COALESCE(RSN.Label, TXT.Label, DFLT.Label)
                                         WHEN OPT.Source = 'C' THEN COALESCE(TXT.Label, RSN.Label, DFLT.Label)
                                         ELSE COALESCE(RSN.Label, DFLT.Label)
                                     END, ' ', '')
                              ORDER BY CASE WHEN StatusId = 1 THEN 0 ELSE 1 END, ComplaintOutcomeId
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
                OUTER APPLY ( SELECT TOP 1 ResolutionMethodID
                              FROM   tblResolutionMethod
                              WHERE  Method = CMP.Resolution_Method
                              ORDER BY ResolutionMethodID
                            ) RESMETH
                OUTER APPLY ( SELECT TOP 1 ComplaintAssistanceID
                              FROM   tblComplaintAssistance
                              WHERE  AssistanceType = CMP.Additional_Assistance
                              ORDER BY ComplaintAssistanceID
                            ) ASSIST
                OUTER APPLY ( SELECT TOP 1 ComplaintResolutionStageID
                              FROM   tblComplaintResolutionStage
                              WHERE  ResolutionStage = 'Closed'
                              ORDER BY ComplaintResolutionStageID
                            ) STAGE
        WHERE   A.LoadID = {{LoadID}}

                AND NOT EXISTS ( SELECT 1 FROM tblComplaint X WITH ( NOLOCK )
                                 WHERE  X.AccountId = A.AccountID
                                        AND X.ComplaintReference = CAST(CMP.ZID AS NVARCHAR(40))
                                        AND X.CreateSessionId = {{CurrentSessionID}} )
;

-- The outcome again, as the Position 1 row of the ASIC outcome list. The application keeps
-- both: ComplaintOutcomeId on the complaint and up to three rows here.
INSERT  INTO tblComplaintAsicOutcome WITH ( ROWLOCK )
        ( ComplaintID, ComplaintOutcomeID, Position, StatusId, CreateID, CreateSessionId )
        SELECT  C.ComplaintId, C.ComplaintOutcomeId, 1, 1, 1, {{CurrentSessionID}}
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.AccountId = A.AccountID
                                                          AND C.ComplaintReference = CAST(CMP.ZID AS NVARCHAR(40))
                                                          AND C.CreateSessionId = {{CurrentSessionID}}
        WHERE   A.LoadID = {{LoadID}}
                AND C.ComplaintOutcomeId IS NOT NULL
                AND NOT EXISTS ( SELECT 1 FROM tblComplaintAsicOutcome X WITH ( NOLOCK ) WHERE X.ComplaintID = C.ComplaintId )
;

INSERT  INTO tblComplaintAccountLink WITH ( ROWLOCK )
        ( ComplaintID, AccountID, ClientCode, IsOriginating, LinkedBy, CreateTS )
        SELECT  C.ComplaintId, A.AccountID, CMP.Client_Code, 1, 'Migration', GETUTCDATE()
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.AccountId = A.AccountID
                                                          AND C.ComplaintReference = CAST(CMP.ZID AS NVARCHAR(40))
                                                          AND C.CreateSessionId = {{CurrentSessionID}}
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1 FROM tblComplaintAccountLink L WITH ( NOLOCK ) WHERE L.ComplaintID = C.ComplaintId )
;

INSERT  INTO tblComplaintIssue WITH ( ROWLOCK )
        ( ComplaintID, ComplaintRootID, ComplaintRootSecondaryID, CreateID, CreateSessionId, CreateTS, Position )
        SELECT  C.ComplaintId, R.ComplaintRootId, RS.ComplaintRootSecondaryID, 1, {{CurrentSessionID}}, GETDATE(), 1
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.AccountId = A.AccountID
                                                          AND C.ComplaintReference = CAST(CMP.ZID AS NVARCHAR(40))
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
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.AccountId = A.AccountID
                                                          AND C.ComplaintReference = CAST(CMP.ZID AS NVARCHAR(40))
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
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.AccountId = A.AccountID
                                                          AND C.ComplaintReference = CAST(CMP.ZID AS NVARCHAR(40))
                                                          AND C.CreateSessionId = {{CurrentSessionID}}
                CROSS APPLY ( SELECT TOP 1 ComplaintRootId FROM tblComplaintRoot WHERE RootCause = CMP.CMP_Issue_3 ORDER BY ComplaintRootId ) R
                OUTER APPLY ( SELECT TOP 1 ComplaintRootSecondaryID FROM tblComplaintRootSecondary
                              WHERE ComplaintRootSecondary = CMP.CMP_Sub_Issue_3 AND ComplaintRootID = R.ComplaintRootId
                              ORDER BY ComplaintRootSecondaryID ) RS
        WHERE   A.LoadID = {{LoadID}}
                AND CMP.CMP_Issue_3 IS NOT NULL
                AND NOT EXISTS ( SELECT 1 FROM tblComplaintIssue I WITH ( NOLOCK ) WHERE I.ComplaintID = C.ComplaintId AND I.Position = 3 )
;

-- History. The extract carries three families of pipe-delimited lists, paired by position:
--   Audit_Action / Audit_Date / Audit_Operator  -> Action / CreateTs / ChangedBy
--   Status_History / Status_History_Date        -> Status (+ PreviousStatus) / CreateTs
--   Document_Code / Document_Sent_Date          -> ActionTaken / CreateTs
-- Each entry becomes one row, under the Category the application files that kind of row
-- in: Audit History, Status History or Document Sent (Action = DocumentSent, the name its
-- own acknowledgement job writes). Documents sent have no table of their own on the target
-- - tblComplaintDocumentChecklist tracks documents received FROM the client.
--
-- The source dates carry no time of day, so rows of one day share a CreateTs; the ORDER BY
-- makes ComplaintHistoryId follow source order within the day. An entry whose date is
-- missing or unreadable falls back to CMP_Enter_date rather than being skipped.
--
-- The closing Migrated from RC_COMPLAINT_EXTRACT row is unchanged. It is still the only
-- place CMP_Status is kept, and for a 51-column extract it is the only row written.
WITH MIGRATED AS (
        SELECT  C.ComplaintId ,
                CMP.CMP_Status ,
                CMP.CMP_Enter_date ,
                CMP.Audit_Action ,
                CMP.Audit_Date ,
                CMP.Audit_Operator ,
                CMP.Status_History ,
                CMP.Status_History_Date ,
                CMP.Document_Code ,
                CMP.Document_Sent_Date
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.AccountId = A.AccountID
                                                          AND C.ComplaintReference = CAST(CMP.ZID AS NVARCHAR(40))
                                                          AND C.CreateSessionId = {{CurrentSessionID}}
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1 FROM TblComplaintHistories H WITH ( NOLOCK ) WHERE H.ComplaintId = C.ComplaintId )
),
HISTORY AS (
        SELECT  M.ComplaintId ,
                1 AS Kind ,
                ACT.ordinal AS Seq ,
                COALESCE(TRY_CONVERT(DATETIME2, LTRIM(RTRIM(DT.value)), 23), M.CMP_Enter_date, SYSDATETIME()) AS CreateTs ,
                CAST(LTRIM(RTRIM(ACT.value)) AS NVARCHAR(MAX)) AS ActionTaken ,
                CAST(LEFT(LTRIM(RTRIM(ACT.value)), 50) AS NVARCHAR(50)) AS Action ,
                CAST(NULL AS NVARCHAR(50)) AS Status ,
                CAST(NULL AS NVARCHAR(50)) AS PreviousStatus ,
                CAST(ISNULL(NULLIF(LTRIM(RTRIM(OP.value)), ''), 'Migration') AS NVARCHAR(255)) AS ChangedBy ,
                CAST('Audit History' AS NVARCHAR(30)) AS Category
        FROM    MIGRATED M
                CROSS APPLY STRING_SPLIT(M.Audit_Action, '|', 1) ACT
                OUTER APPLY ( SELECT S.value FROM STRING_SPLIT(M.Audit_Date, '|', 1) S WHERE S.ordinal = ACT.ordinal ) DT
                OUTER APPLY ( SELECT S.value FROM STRING_SPLIT(M.Audit_Operator, '|', 1) S WHERE S.ordinal = ACT.ordinal ) OP
        WHERE   LTRIM(RTRIM(ACT.value)) <> ''
        UNION ALL
        SELECT  M.ComplaintId ,
                2 ,
                ST.ordinal ,
                COALESCE(TRY_CONVERT(DATETIME2, LTRIM(RTRIM(DT.value)), 23), M.CMP_Enter_date, SYSDATETIME()) ,
                CAST('Status changed to ' + LTRIM(RTRIM(ST.value)) AS NVARCHAR(MAX)) ,
                CAST('Status Changed' AS NVARCHAR(50)) ,
                CAST(LEFT(LTRIM(RTRIM(ST.value)), 50) AS NVARCHAR(50)) ,
                CAST(LEFT(LTRIM(RTRIM(PREV.value)), 50) AS NVARCHAR(50)) ,
                CAST('Migration' AS NVARCHAR(255)) ,
                CAST('Status History' AS NVARCHAR(30))
        FROM    MIGRATED M
                CROSS APPLY STRING_SPLIT(M.Status_History, '|', 1) ST
                OUTER APPLY ( SELECT S.value FROM STRING_SPLIT(M.Status_History_Date, '|', 1) S WHERE S.ordinal = ST.ordinal ) DT
                OUTER APPLY ( SELECT S.value FROM STRING_SPLIT(M.Status_History, '|', 1) S WHERE S.ordinal = ST.ordinal - 1 ) PREV
        WHERE   LTRIM(RTRIM(ST.value)) <> ''
        UNION ALL
        SELECT  M.ComplaintId ,
                3 ,
                DOC.ordinal ,
                COALESCE(TRY_CONVERT(DATETIME2, LTRIM(RTRIM(DT.value)), 23), M.CMP_Enter_date, SYSDATETIME()) ,
                CAST('Document sent: ' + LTRIM(RTRIM(DOC.value)) AS NVARCHAR(MAX)) ,
                CAST('DocumentSent' AS NVARCHAR(50)) ,
                CAST(NULL AS NVARCHAR(50)) ,
                CAST(NULL AS NVARCHAR(50)) ,
                CAST('Migration' AS NVARCHAR(255)) ,
                CAST('Document Sent' AS NVARCHAR(30))
        FROM    MIGRATED M
                CROSS APPLY STRING_SPLIT(M.Document_Code, '|', 1) DOC
                OUTER APPLY ( SELECT S.value FROM STRING_SPLIT(M.Document_Sent_Date, '|', 1) S WHERE S.ordinal = DOC.ordinal ) DT
        WHERE   LTRIM(RTRIM(DOC.value)) <> ''
        UNION ALL
        SELECT  M.ComplaintId ,
                4 ,
                1 ,
                SYSDATETIME() ,
                CAST('Migrated from RC_COMPLAINT_EXTRACT' AS NVARCHAR(MAX)) ,
                CAST('Migrated from RC_COMPLAINT_EXTRACT' AS NVARCHAR(50)) ,
                CAST(LEFT(M.CMP_Status, 50) AS NVARCHAR(50)) ,
                CAST(NULL AS NVARCHAR(50)) ,
                CAST('Migration' AS NVARCHAR(255)) ,
                CAST(NULL AS NVARCHAR(30))
        FROM    MIGRATED M
)
INSERT  INTO TblComplaintHistories WITH ( ROWLOCK )
        ( ComplaintId, ActionTaken, CreateId, CreateSessionId, CreateTs, StatusId, Action, Status, PreviousStatus, ChangedBy, Category )
        SELECT  H.ComplaintId, H.ActionTaken, 1, {{CurrentSessionID}}, H.CreateTs, 1,
                H.Action, H.Status, H.PreviousStatus, H.ChangedBy, H.Category
        FROM    HISTORY H
        ORDER BY H.ComplaintId, H.CreateTs, H.Kind, H.Seq
;
