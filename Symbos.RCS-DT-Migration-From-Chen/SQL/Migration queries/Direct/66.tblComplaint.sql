
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
                CASE WHEN CMP.CMP_Status LIKE '%CLS%' OR CMP.CMP_Status LIKE '%CLOSED%' THEN CMP.CMP_Status_Date END ,
                CASE WHEN CMP.CMP_Status LIKE '%CLS%' OR CMP.CMP_Status LIKE '%CLOSED%' THEN 'Migration' END ,
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
                CMP.CMP_Outcome ,
                CMP.Zendesk_Ticket_Number ,
                CMP.CMP_Referred_to_Client_Date ,
                CMP.CMP_AFCA_Date_Required ,
                'RCS' ,
                CAST(CMP.Extended_Debt_Code AS NVARCHAR(50)) ,
                CMP.CMP_Ownership ,
                CMP.CMP_Logged_By ,
                0 ,
                'COMPLAINT' ,
                0
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplainant COMPL ON COMPL.Name = CMP.CMP_Source

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

                AND NOT EXISTS ( SELECT 1 FROM tblComplaint X WITH ( NOLOCK )
                                 WHERE  X.AccountId = A.AccountID
                                        AND X.ComplaintReference = CAST(CMP.ZID AS NVARCHAR(40))
                                        AND X.CreateSessionId = {{CurrentSessionID}} )
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

INSERT  INTO TblComplaintHistories WITH ( ROWLOCK )
        ( ComplaintId, ActionTaken, CreateId, CreateSessionId, CreateTs, StatusId, Action, Status, ChangedBy )
        SELECT  C.ComplaintId, 'Migrated from RC_COMPLAINT_EXTRACT', 1, {{CurrentSessionID}}, SYSDATETIME(), 1,
                'Migrated from RC_COMPLAINT_EXTRACT', CMP.CMP_Status, 'Migration'
        FROM    RC_COMPLAINT_EXTRACT CMP
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CMP.Extended_Debt_Code
                INNER JOIN tblComplaint C WITH ( NOLOCK ) ON C.AccountId = A.AccountID
                                                          AND C.ComplaintReference = CAST(CMP.ZID AS NVARCHAR(40))
                                                          AND C.CreateSessionId = {{CurrentSessionID}}
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1 FROM TblComplaintHistories H WITH ( NOLOCK ) WHERE H.ComplaintId = C.ComplaintId )
;
