-- Complaint-domain tables scripted from test-debtrak (debtrak-test-sql.database.windows.net).
-- Idempotent: only creates tables/FKs that don't already exist; does not alter existing ones.
-- NOTE: nvarchar/nchar widths below are converted from sys.columns.max_length (bytes) to characters.

IF OBJECT_ID('tblCommunicationPreference') IS NULL
BEGIN
CREATE TABLE [tblCommunicationPreference] (
    [CommunicationPreferenceID] int IDENTITY(1,1) NOT NULL,
    [CommunicationPreference] nvarchar(500) NULL,
    [CreateID] int NULL,
    [CreateSessionID] int NULL,
    [CreateTS] datetime NULL,
    [ModifyID] int NULL,
    [ModifySessionID] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionID] int NULL,
    [InactiveTS] datetime NULL,
    [StatusID] int NULL,
    [Name] nvarchar(200) NOT NULL DEFAULT (N''),
    [IsActive] bit NOT NULL DEFAULT (CONVERT([bit],(1))),
    [row_version] timestamp NOT NULL,
    CONSTRAINT [PK_tblCommunicationPreference] PRIMARY KEY ([CommunicationPreferenceID])
);
END
GO

IF OBJECT_ID('tblComplaint') IS NULL
BEGIN
CREATE TABLE [tblComplaint] (
    [ComplaintId] bigint IDENTITY(1,1) NOT NULL,
    [AccountId] int NULL,
    [DateReceived] datetime NOT NULL,
    [ComplainantId] bigint NOT NULL,
    [ComplaintTypeId] int NOT NULL,
    [ComplaintMethodId] int NOT NULL,
    [FCACategoryId] int NULL,
    [Summary] nvarchar(MAX) NULL,
    [ExpectedOutcome] nvarchar(MAX) NULL,
    [CallBack] bit NULL,
    [CustomerImpact] int NULL,
    [RegulatoryDate] datetime NULL,
    [SensitiveInformationView] bit NULL,
    [ReviewDate] datetime NULL,
    [RegulatoryReferral] bit NULL,
    [RegulatoryReferralDate] datetime NULL,
    [SentDate] datetime NULL,
    [ComplaintRootId] int NULL,
    [CommunicationPreferenceID] int NULL,
    [ComplaintContactId] int NULL,
    [ComplaintOutcomeId] int NULL,
    [ComplaintSourceId] int NULL,
    [ComplaintAssistanceId] int NULL,
    [ComplaintOriginatorId] int NULL,
    [ComplaintLevelId] int NULL,
    [ComplaintSeverityId] int NULL,
    [ComplaintPriorityId] int NULL,
    [ResolutionMethodId] int NULL,
    [ConfirmResolved] bit NULL DEFAULT ((0)),
    [ResolvedByAgent] bit NULL,
    [Resolved] bit NULL,
    [ResolvedDate] datetime NULL,
    [RequestedDate] datetime NULL,
    [MonetaryCompensationProvided] bit NULL,
    [MonetaryCompensationAmount] decimal(18,2) NULL,
    [ComplaintReference] nvarchar(20) NULL,
    [RegulatoryCaseNumber] nvarchar(MAX) NULL,
    [DefaultListingRemoved] bit NULL,
    [ActionTaken] nvarchar(MAX) NULL,
    [ComplaintUpheldID] int NULL,
    [ComplaintRootSecondaryId] int NULL,
    [ComplaintRootTertiary] nvarchar(MAX) NULL,
    [CorrectiveActionId] int NULL,
    [RemedialAction] nvarchar(MAX) NULL,
    [ComplaintRootTertiaryID] int NULL,
    [AuthorisedRep] bit NULL,
    [CreateId] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveId] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    [ActualOutcomeDate] datetime2(7) NULL,
    [ClosureReasonId] int NULL,
    [ComplainantSatisfied] int NULL,
    [CustomerImpactDetails] nvarchar(MAX) NULL,
    [DecisionInformationRequestedComplainant] bit NULL,
    [NotifiedRCLVia] int NULL,
    [ResolutionDetails] nvarchar(MAX) NULL,
    [ResolvedOnCall] int NULL,
    [ZendeskTicketNumber] nvarchar(MAX) NULL,
    [ClientContactedDetails] nvarchar(MAX) NULL,
    [ClientDisputeResponse] nvarchar(MAX) NULL,
    [ComplaintClientContactedDate] datetime2(7) NULL,
    [ComplaintRequireClientAssistance] bit NULL,
    [ComplaintRequireToContactManager] bit NULL,
    [DueDate] datetime2(7) NULL,
    [ClientCode] nvarchar(50) NULL,
    [AccountReference] nvarchar(255) NULL,
    [ComplainantName] nvarchar(255) NULL,
    [ComplainantEmail] nvarchar(254) NULL,
    [ComplainantPhone] nvarchar(30) NULL,
    [PostalAddress] nvarchar(500) NULL,
    [IsPrivacyRelated] bit NULL,
    [IPAddress] nvarchar(64) NULL,
    [PrivacyOfficerNotified] bit NULL,
    [DeactivatedBy] nvarchar(255) NULL,
    [DeactivationReason] nvarchar(500) NULL,
    [ModifiedBy] nvarchar(255) NULL,
    [OwnershipStatus] nvarchar(20) NULL,
    [ComplaintInitiationDate] datetime2(7) NULL,
    [AdditionalAssistanceRequired] bit NULL,
    [ThreatDateTime] datetime2(7) NULL,
    [CallbackRequiredBy] datetime2(7) NULL,
    [AcknowledgedDate] datetime2(7) NULL,
    [ComplainantNotifiedDate] datetime2(7) NULL,
    [ClientReferralDate] datetime2(7) NULL,
    [ClientReferenceNumber] nvarchar(50) NULL,
    [ClientEscalationMethodID] int NULL,
    [OmbudsmanResponseDueDate] datetime2(7) NULL,
    [OmbudsmanResponseSentDate] datetime2(7) NULL,
    [OmbudsmanApplicableFees] decimal(18,2) NULL,
    [ReopenReason] nvarchar(MAX) NULL,
    [ReopenedAt] datetime2(7) NULL,
    [ReopenedBy] nvarchar(255) NULL,
    [ComplainantGender] nvarchar(20) NULL,
    [ComplainantAgeGroup] int NULL,
    [ComplainantPostcode] nvarchar(10) NULL,
    [LodgedByRole] nvarchar(50) NULL,
    [LodgedByTeamCode] nvarchar(50) NULL,
    [ReviewedByContactID] int NULL,
    [ResolvedByContactID] int NULL,
    [PoiUnconfirmedAtLodgement] bit NULL,
    [ClosedDate] datetime2(7) NULL,
    [IdrOutcomeSent] bit NULL,
    [IdrOutcomeSentDate] datetime2(7) NULL,
    [IdrOutcomeSentInWriting] bit NULL,
    [WrittenResponseRequested] bit NULL,
    [CompensationApprovalRequired] bit NULL,
    [CompensationApprovedBy] nvarchar(255) NULL,
    [CompensationApprovedAt] datetime2(7) NULL,
    [ClientConfirmationToHandleDate] datetime2(7) NULL,
    [ClientFinalResponseDate] datetime2(7) NULL,
    [ClientRecallDecisionID] int NULL,
    [CustomerSeenInvoice] bit NULL,
    [RaisedWithClientPreviously] bit NULL,
    [RaisedWithClientDetail] nvarchar(MAX) NULL,
    [DisputingFullBalance] bit NULL,
    [DisputingCreditListing] bit NULL,
    [NextActionRequestSupportingDocuments] bit NULL,
    [NextActionRequestInvoiceSent] bit NULL,
    [IsDraft] bit NOT NULL DEFAULT ((0)),
    [Classification] nvarchar(20) NOT NULL DEFAULT (N'COMPLAINT'),
    [CompensationApprovalStatus] nvarchar(20) NULL,
    [CompensationApprovalRequestedBy] nvarchar(255) NULL,
    [CompensationApprovalRequestedAt] datetime2(7) NULL,
    [CompensationApprovalDecisionReason] nvarchar(2000) NULL,
    [CompensationReason] nvarchar(2000) NULL,
    [IdrNotSentReason] nvarchar(2000) NULL,
    [SlaOffsetDays] int NULL,
    [ComplaintSlaProfileID] int NULL,
    [OmbudsmanBody] nvarchar(20) NULL,
    [OmbudsmanDateClosed] datetime2(7) NULL,
    [OmbudsmanClosureReasonID] int NULL,
    [OmbudsmanStatus] nvarchar(30) NULL,
    [OmbudsmanDateReferralPeriod] datetime2(7) NULL,
    [OmbudsmanDateLodged] datetime2(7) NULL,
    [IsRestrictedVisibility] bit NOT NULL DEFAULT ((0)),
    CONSTRAINT [PK_tblComplaint] PRIMARY KEY ([ComplaintId])
);
END
GO

IF OBJECT_ID('tblComplaint_Notification') IS NULL
BEGIN
CREATE TABLE [tblComplaint_Notification] (
    [ComplaintNotificationID] int IDENTITY(1,1) NOT NULL,
    [ComplaintID] bigint NOT NULL,
    [MilestoneCode] nvarchar(64) NOT NULL,
    [RecipientKind] int NOT NULL,
    [TemplateCode] nvarchar(128) NULL,
    [Status] nvarchar(40) NOT NULL,
    [Detail] nvarchar(MAX) NULL,
    [RequestedAt] datetime2(7) NOT NULL,
    [RequestedBy] nvarchar(255) NOT NULL,
    [CommunicationID] bigint NULL,
    [DueDate] datetime2(7) NULL,
    CONSTRAINT [PK_tblComplaint_Notification] PRIMARY KEY ([ComplaintNotificationID])
);
END
GO

IF OBJECT_ID('tblComplaintAccountLink') IS NULL
BEGIN
CREATE TABLE [tblComplaintAccountLink] (
    [ComplaintAccountLinkID] bigint IDENTITY(1,1) NOT NULL,
    [ComplaintID] bigint NOT NULL,
    [AccountID] int NOT NULL,
    [ClientCode] nvarchar(50) NULL,
    [IsOriginating] bit NOT NULL,
    [LinkedBy] nvarchar(255) NOT NULL,
    [CreateTS] datetime2(7) NOT NULL,
    [UnlinkedTS] datetime2(7) NULL,
    [UnlinkedBy] nvarchar(255) NULL,
    [ExclusionRecordID] int NULL,
    CONSTRAINT [PK_tblComplaintAccountLink] PRIMARY KEY ([ComplaintAccountLinkID])
);
END
GO

IF OBJECT_ID('tblComplaintAsicOutcome') IS NULL
BEGIN
CREATE TABLE [tblComplaintAsicOutcome] (
    [ComplaintAsicOutcomeID] int IDENTITY(1,1) NOT NULL,
    [ComplaintID] bigint NOT NULL,
    [ComplaintOutcomeID] int NULL,
    [Position] int NULL,
    [StatusId] int NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    CONSTRAINT [PK_tblComplaintAsicOutcome] PRIMARY KEY ([ComplaintAsicOutcomeID])
);
END
GO

IF OBJECT_ID('tblComplaintAssignee') IS NULL
BEGIN
CREATE TABLE [tblComplaintAssignee] (
    [ComplaintAssigneeID] int IDENTITY(1,1) NOT NULL,
    [ComplaintID] bigint NOT NULL,
    [Assignee] int NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintAssignee] PRIMARY KEY ([ComplaintAssigneeID])
);
END
GO

IF OBJECT_ID('tblComplaintAssistance') IS NULL
BEGIN
CREATE TABLE [tblComplaintAssistance] (
    [ComplaintAssistanceID] int IDENTITY(1,1) NOT NULL,
    [AssistanceType] nvarchar(100) NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintAssistance] PRIMARY KEY ([ComplaintAssistanceID])
);
END
GO

IF OBJECT_ID('tblComplaintClientReferral') IS NULL
BEGIN
CREATE TABLE [tblComplaintClientReferral] (
    [ComplaintClientReferralID] int IDENTITY(1,1) NOT NULL,
    [ClientCode] nvarchar(50) NULL,
    [ComplaintID] bigint NOT NULL,
    [DateReferredToClient] datetime2(7) NULL,
    [ReferralChannel] nvarchar(200) NULL,
    [ClientReferenceNumber] nvarchar(50) NULL,
    [DateClientFinalResponseReceived] datetime2(7) NULL,
    [ClientRecallDecisionID] int NULL,
    [Notes] nvarchar(MAX) NULL,
    [CreateTS] datetime2(7) NOT NULL,
    [CreateId] int NOT NULL,
    [ModifiedAt] datetime2(7) NULL,
    [ModifiedBy] nvarchar(200) NULL,
    CONSTRAINT [PK_tblComplaintClientReferral] PRIMARY KEY ([ComplaintClientReferralID])
);
END
GO

IF OBJECT_ID('tblComplaintConfiguration') IS NULL
BEGIN
CREATE TABLE [tblComplaintConfiguration] (
    [ComplaintConfigurationID] int IDENTITY(1,1) NOT NULL,
    [ClientCode] nvarchar(50) NOT NULL,
    [SettingKey] nvarchar(128) NOT NULL,
    [EntityID] int NULL,
    [UserGroupID] int NULL,
    [SettingValue] nvarchar(MAX) NULL,
    [StatusId] int NOT NULL,
    [CreateTS] datetime2(7) NOT NULL,
    [ModifyTS] datetime2(7) NOT NULL,
    [ModifiedBy] nvarchar(200) NOT NULL,
    CONSTRAINT [PK_tblComplaintConfiguration] PRIMARY KEY ([ComplaintConfigurationID])
);
END
GO

IF OBJECT_ID('tblComplaintConfiguration_Audit') IS NULL
BEGIN
CREATE TABLE [tblComplaintConfiguration_Audit] (
    [ComplaintConfigurationAuditID] int IDENTITY(1,1) NOT NULL,
    [ClientCode] nvarchar(50) NOT NULL,
    [SettingKey] nvarchar(128) NOT NULL,
    [EntityID] int NULL,
    [UserGroupID] int NULL,
    [OldValue] nvarchar(MAX) NULL,
    [NewValue] nvarchar(MAX) NULL,
    [ChangeKind] nvarchar(20) NOT NULL,
    [ChangedAt] datetime2(7) NOT NULL,
    [ChangedBy] nvarchar(200) NOT NULL,
    [IsRegulatory] bit NOT NULL,
    [ConfirmationAcknowledgement] nvarchar(400) NULL,
    [ConfirmationReason] nvarchar(MAX) NULL,
    CONSTRAINT [PK_tblComplaintConfiguration_Audit] PRIMARY KEY ([ComplaintConfigurationAuditID])
);
END
GO

IF OBJECT_ID('tblComplaintContact') IS NULL
BEGIN
CREATE TABLE [tblComplaintContact] (
    [ComplaintContactId] int IDENTITY(1,1) NOT NULL,
    [RootContact] nvarchar(60) NOT NULL,
    [CreateId] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveId] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintContact] PRIMARY KEY ([ComplaintContactId])
);
END
GO

IF OBJECT_ID('tblComplaintDecision') IS NULL
BEGIN
CREATE TABLE [tblComplaintDecision] (
    [ComplaintDecisionId] int IDENTITY(1,1) NOT NULL,
    [ComplaintDecision] nvarchar(MAX) NULL,
    [ComplaintDecisionTypeId] int NOT NULL,
    [IsClosureReason] bit NOT NULL DEFAULT ((0)),
    [OperatorId] int NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintDecision] PRIMARY KEY ([ComplaintDecisionId])
);
END
GO

IF OBJECT_ID('tblComplaintDecisionType') IS NULL
BEGIN
CREATE TABLE [tblComplaintDecisionType] (
    [ComplaintDecisionTypeId] int IDENTITY(1,1) NOT NULL,
    [DecisionType] nvarchar(50) NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusID] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintDecisionType] PRIMARY KEY ([ComplaintDecisionTypeId])
);
END
GO

IF OBJECT_ID('tblComplaintDocument') IS NULL
BEGIN
CREATE TABLE [tblComplaintDocument] (
    [ComplaintDocumentId] int IDENTITY(1,1) NOT NULL,
    [ComplaintId] bigint NOT NULL,
    [ComplaintDocumentTypeId] int NOT NULL,
    [Required] bit NOT NULL DEFAULT ((0)),
    [Received] bit NOT NULL DEFAULT ((0)),
    [OtherDocumentDescription] nvarchar(MAX) NULL,
    [CreateId] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveId] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    [ReceivedDate] datetime2(7) NULL,
    [RequiredFromPartyID] int NULL,
    [MediaID] int NULL,
    [ProvidedBy] nvarchar(100) NULL,
    [IsSensitive] bit NOT NULL DEFAULT ((0)),
    [IsInternalOnly] bit NOT NULL DEFAULT ((0)),
    CONSTRAINT [PK_tblComplaintDocument] PRIMARY KEY ([ComplaintDocumentId])
);
END
GO

IF OBJECT_ID('tblComplaintDocumentChecklist') IS NULL
BEGIN
CREATE TABLE [tblComplaintDocumentChecklist] (
    [ComplaintDocumentChecklistID] int IDENTITY(1,1) NOT NULL,
    [ClientCode] nvarchar(50) NULL,
    [ComplaintID] bigint NOT NULL,
    [ComplaintDocumentTypeID] int NULL,
    [DocumentName] nvarchar(200) NULL,
    [RequiredFrom] nvarchar(20) NULL,
    [IsRequired] bit NOT NULL DEFAULT ((0)),
    [IsReceived] bit NOT NULL DEFAULT ((0)),
    [ReceivedDate] datetime2(7) NULL,
    [CreateTS] datetime2(7) NOT NULL,
    [CreateId] int NOT NULL,
    [ModifiedAt] datetime2(7) NULL,
    [ModifiedBy] nvarchar(200) NULL,
    CONSTRAINT [PK_tblComplaintDocumentChecklist] PRIMARY KEY ([ComplaintDocumentChecklistID])
);
END
GO

IF OBJECT_ID('tblComplaintDocumentType') IS NULL
BEGIN
CREATE TABLE [tblComplaintDocumentType] (
    [ComplaintDocumentTypeId] int IDENTITY(1,1) NOT NULL,
    [DocumentType] nvarchar(100) NOT NULL,
    [IsOtherDocument] bit NOT NULL DEFAULT ((0)),
    [CreateId] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveId] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    [Classification] nvarchar(20) NULL,
    [Description] nvarchar(500) NULL,
    CONSTRAINT [PK_tblComplaintDocumentType] PRIMARY KEY ([ComplaintDocumentTypeId])
);
END
GO

IF OBJECT_ID('tblComplaintEscalation') IS NULL
BEGIN
CREATE TABLE [tblComplaintEscalation] (
    [ComplaintEscalationID] int IDENTITY(1,1) NOT NULL,
    [ComplaintID] bigint NOT NULL,
    [EscalationLevel] int NOT NULL,
    [EscalatedAt] datetime2(7) NOT NULL,
    [EscalatedFromContactID] int NULL,
    [EscalatedToContactID] int NULL,
    [EscalatedToUserGroupID] int NULL,
    [EscalationReason] nvarchar(MAX) NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime2(7) NOT NULL DEFAULT (sysutcdatetime()),
    [ModifyID] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime2(7) NULL,
    [InactiveID] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime2(7) NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintEscalation] PRIMARY KEY ([ComplaintEscalationID])
);
END
GO

IF OBJECT_ID('tblComplaintFCACategory') IS NULL
BEGIN
CREATE TABLE [tblComplaintFCACategory] (
    [ComplaintFCACategoryId] int IDENTITY(1,1) NOT NULL,
    [FCACategory] nvarchar(80) NOT NULL,
    [CreateId] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveId] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintFCACategory] PRIMARY KEY ([ComplaintFCACategoryId])
);
END
GO

IF OBJECT_ID('TblComplaintHistories') IS NULL
BEGIN
CREATE TABLE [TblComplaintHistories] (
    [ComplaintHistoryId] int IDENTITY(1,1) NOT NULL,
    [ComplaintId] bigint NOT NULL,
    [ComplaintOutcomeId] int NULL,
    [ActionTaken] nvarchar(MAX) NULL,
    [CreateId] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTs] datetime2(7) NOT NULL,
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTs] datetime2(7) NULL,
    [StatusId] int NOT NULL,
    [Action] nvarchar(50) NULL,
    [Status] nvarchar(50) NULL,
    [ChangedBy] nvarchar(255) NULL,
    [PreviousStatus] nvarchar(50) NULL,
    CONSTRAINT [PK_TblComplaintHistories] PRIMARY KEY ([ComplaintHistoryId])
);
END
GO

IF OBJECT_ID('tblComplaintInsuranceDetail') IS NULL
BEGIN
CREATE TABLE [tblComplaintInsuranceDetail] (
    [ComplaintInsuranceDetailID] bigint IDENTITY(1,1) NOT NULL,
    [ComplaintID] bigint NOT NULL,
    [IsLiabilityDispute] bit NOT NULL DEFAULT (CONVERT([bit],(0))),
    [IsQuantumDispute] bit NOT NULL DEFAULT (CONVERT([bit],(0))),
    [ThirdPartyVersion] nvarchar(2000) NULL,
    [HasEvidenceVehicleAndDriver] bit NOT NULL DEFAULT (CONVERT([bit],(0))),
    [HasEvidenceWitness] bit NOT NULL DEFAULT (CONVERT([bit],(0))),
    [HasEvidenceDashcam] bit NOT NULL DEFAULT (CONVERT([bit],(0))),
    [IsThirdPartyDisputingFullCost] bit NULL,
    [HasWrittenIndependentAssessment] bit NULL,
    [IncidentDescriptionManual] nvarchar(2000) NULL,
    [RoadRulesManual] nvarchar(2000) NULL,
    [ClaimAmountManual] decimal(18,2) NULL,
    [CreateTS] datetime2(7) NOT NULL,
    [ModifyTS] datetime2(7) NULL,
    CONSTRAINT [PK_tblComplaintInsuranceDetail] PRIMARY KEY ([ComplaintInsuranceDetailID])
);
END
GO

IF OBJECT_ID('tblComplaintIssue') IS NULL
BEGIN
CREATE TABLE [tblComplaintIssue] (
    [ComplaintIssueID] int IDENTITY(1,1) NOT NULL,
    [ComplaintID] bigint NOT NULL,
    [ComplaintRootID] int NULL,
    [ComplaintRootSecondaryID] int NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [TblComplainantComplainantId] bigint NULL,
    [Position] int NULL,
    CONSTRAINT [PK_tblComplaintIssue] PRIMARY KEY ([ComplaintIssueID])
);
END
GO

IF OBJECT_ID('tblComplaintLevel') IS NULL
BEGIN
CREATE TABLE [tblComplaintLevel] (
    [ComplaintLevelID] int IDENTITY(1,1) NOT NULL,
    [Level] nvarchar(50) NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintLevel] PRIMARY KEY ([ComplaintLevelID])
);
END
GO

IF OBJECT_ID('tblComplaintMethod') IS NULL
BEGIN
CREATE TABLE [tblComplaintMethod] (
    [ComplaintMethodId] int IDENTITY(1,1) NOT NULL,
    [Method] nvarchar(60) NOT NULL,
    [CreateId] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveId] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintMethod] PRIMARY KEY ([ComplaintMethodId])
);
END
GO

IF OBJECT_ID('tblComplaintOmbudsmanClosureReason') IS NULL
BEGIN
CREATE TABLE [tblComplaintOmbudsmanClosureReason] (
    [ComplaintOmbudsmanClosureReasonID] int IDENTITY(1,1) NOT NULL,
    [ClientCode] nvarchar(50) NULL,
    [ClosureReason] nvarchar(100) NOT NULL,
    [Description] nvarchar(500) NULL,
    [Classification] nvarchar(20) NULL,
    [IsActive] bit NOT NULL DEFAULT ((1)),
    [CreateTS] datetime2(7) NOT NULL,
    [CreateId] int NOT NULL,
    [ModifiedAt] datetime2(7) NULL,
    [ModifiedBy] nvarchar(200) NULL,
    CONSTRAINT [PK_tblComplaintOmbudsmanClosureReason] PRIMARY KEY ([ComplaintOmbudsmanClosureReasonID])
);
END
GO

IF OBJECT_ID('tblComplaintOriginator') IS NULL
BEGIN
CREATE TABLE [tblComplaintOriginator] (
    [ComplaintOriginatorID] int IDENTITY(1,1) NOT NULL,
    [OriginatorType] nvarchar(50) NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    [Classification] nvarchar(20) NULL,
    [Description] nvarchar(500) NULL,
    [IsInternal] bit NULL,
    CONSTRAINT [PK_tblComplaintOriginator] PRIMARY KEY ([ComplaintOriginatorID])
);
END
GO

IF OBJECT_ID('tblComplaintOutcome') IS NULL
BEGIN
CREATE TABLE [tblComplaintOutcome] (
    [ComplaintOutcomeId] int IDENTITY(1,1) NOT NULL,
    [Outcome] nvarchar(100) NOT NULL,
    [CreateId] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveId] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    [Classification] nvarchar(20) NULL,
    [Description] nvarchar(500) NULL,
    CONSTRAINT [PK_tblComplaintOutcome] PRIMARY KEY ([ComplaintOutcomeId])
);
END
GO

IF OBJECT_ID('tblComplaintPriority') IS NULL
BEGIN
CREATE TABLE [tblComplaintPriority] (
    [ComplaintPriorityID] int IDENTITY(1,1) NOT NULL,
    [PriorityLevel] nvarchar(50) NOT NULL,
    [Description] nvarchar(200) NULL,
    [SLA] int NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintPriority] PRIMARY KEY ([ComplaintPriorityID])
);
END
GO

IF OBJECT_ID('tblComplaintProduct') IS NULL
BEGIN
CREATE TABLE [tblComplaintProduct] (
    [ComplaintProductID] int IDENTITY(1,1) NOT NULL,
    [ComplaintID] bigint NOT NULL,
    [AsicProductCode] int NULL,
    [Position] int NULL,
    [StatusId] int NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    CONSTRAINT [PK_tblComplaintProduct] PRIMARY KEY ([ComplaintProductID])
);
END
GO

IF OBJECT_ID('tblComplaintReportColumn') IS NULL
BEGIN
CREATE TABLE [tblComplaintReportColumn] (
    [ComplaintReportColumnID] int IDENTITY(1,1) NOT NULL,
    [ClientCode] nvarchar(50) NULL,
    [ColumnKey] nvarchar(128) NOT NULL,
    [Heading] nvarchar(200) NOT NULL,
    [ColumnGroup] nvarchar(20) NOT NULL,
    [FormatRule] nvarchar(50) NULL,
    [SortOrder] int NOT NULL,
    [IsActive] bit NOT NULL DEFAULT ((1)),
    [CreateTS] datetime2(7) NOT NULL,
    [CreateId] int NOT NULL,
    [ModifiedAt] datetime2(7) NULL,
    [ModifiedBy] nvarchar(200) NULL,
    CONSTRAINT [PK_tblComplaintReportColumn] PRIMARY KEY ([ComplaintReportColumnID])
);
END
GO

IF OBJECT_ID('tblComplaintResolution') IS NULL
BEGIN
CREATE TABLE [tblComplaintResolution] (
    [ComplaintResolutionId] int IDENTITY(1,1) NOT NULL,
    [ComplaintId] bigint NOT NULL,
    [ComplaintDecisionId] int NOT NULL,
    [DecisionAnalysis] nvarchar(MAX) NULL,
    [FinalResponse] datetime NULL,
    [FOSExpiration] datetime NULL,
    [CorrectiveAction] nvarchar(MAX) NULL,
    [ComplaintRootId] int NULL,
    [ComplaintContactId] int NULL,
    [ComplaintOutcomeId] int NULL,
    [CreateId] int NOT NULL DEFAULT ((1)),
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveId] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    [ADRAgreed] bit NULL,
    [ComplaintResolutionStageID] int NULL,
    [ComplaintRootSecondaryId] int NULL,
    [ComplaintRootTertiary] nvarchar(MAX) NULL,
    [ComplaintRootTertiaryID] int NULL,
    [DecisionInformationRequested] bit NULL,
    [ResolutionStageChangedAt] datetime2(7) NULL,
    CONSTRAINT [PK_tblComplaintResolution] PRIMARY KEY ([ComplaintResolutionId])
);
END
GO

IF OBJECT_ID('tblComplaintResolutionStage') IS NULL
BEGIN
CREATE TABLE [tblComplaintResolutionStage] (
    [ComplaintResolutionStageID] int IDENTITY(1,1) NOT NULL,
    [ResolutionStage] nvarchar(250) NULL,
    [CreateID] int NOT NULL,
    [CreateSessionID] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionID] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionID] int NULL,
    [InactiveTS] datetime NULL,
    [StatusID] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintResolutionStage] PRIMARY KEY ([ComplaintResolutionStageID])
);
END
GO

IF OBJECT_ID('tblComplaintRoot') IS NULL
BEGIN
CREATE TABLE [tblComplaintRoot] (
    [ComplaintRootId] int IDENTITY(1,1) NOT NULL,
    [RootCause] nvarchar(100) NOT NULL,
    [RootCauseTypeId] int NOT NULL,
    [CreateId] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveId] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    [Classification] nvarchar(20) NULL,
    [Description] nvarchar(500) NULL,
    CONSTRAINT [PK_tblComplaintRoot] PRIMARY KEY ([ComplaintRootId])
);
END
GO

IF OBJECT_ID('tblComplaintRootSecondary') IS NULL
BEGIN
CREATE TABLE [tblComplaintRootSecondary] (
    [ComplaintRootSecondaryID] int IDENTITY(1,1) NOT NULL,
    [ComplaintRootSecondary] nvarchar(MAX) NOT NULL,
    [ComplaintRootID] int NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionID] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveTS] datetime NULL,
    [StatusID] int NOT NULL DEFAULT ((1)),
    [Classification] nvarchar(20) NULL,
    [Description] nvarchar(500) NULL,
    CONSTRAINT [PK_tblComplaintRootSecondary] PRIMARY KEY ([ComplaintRootSecondaryID])
);
END
GO

IF OBJECT_ID('tblComplaintRootType') IS NULL
BEGIN
CREATE TABLE [tblComplaintRootType] (
    [ComplaintRootTypeId] int IDENTITY(1,1) NOT NULL,
    [RootType] nvarchar(50) NOT NULL,
    [CreateId] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveId] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintRootType] PRIMARY KEY ([ComplaintRootTypeId])
);
END
GO

IF OBJECT_ID('tblComplaintSeverity') IS NULL
BEGIN
CREATE TABLE [tblComplaintSeverity] (
    [ComplaintSeverityID] int IDENTITY(1,1) NOT NULL,
    [SeverityLevel] nvarchar(50) NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintSeverity] PRIMARY KEY ([ComplaintSeverityID])
);
END
GO

IF OBJECT_ID('tblComplaintSlaNotification') IS NULL
BEGIN
CREATE TABLE [tblComplaintSlaNotification] (
    [ComplaintSlaNotificationID] int IDENTITY(1,1) NOT NULL,
    [ClientCode] nvarchar(50) NULL,
    [ComplaintSlaWorkflowID] int NOT NULL,
    [TemplateName] nvarchar(128) NOT NULL,
    [RecipientKind] nvarchar(30) NOT NULL,
    [RecipientValue] nvarchar(400) NULL,
    [IsActive] bit NOT NULL DEFAULT ((1)),
    [CreateTS] datetime2(7) NOT NULL,
    [CreateId] int NOT NULL,
    [ModifiedAt] datetime2(7) NULL,
    [ModifiedBy] nvarchar(200) NULL,
    CONSTRAINT [PK_tblComplaintSlaNotification] PRIMARY KEY ([ComplaintSlaNotificationID])
);
END
GO

IF OBJECT_ID('tblComplaintSlaProfile') IS NULL
BEGIN
CREATE TABLE [tblComplaintSlaProfile] (
    [ComplaintSlaProfileID] int IDENTITY(1,1) NOT NULL,
    [ClientCode] nvarchar(50) NULL,
    [Name] nvarchar(100) NOT NULL,
    [Description] nvarchar(500) NULL,
    [WindowDays] int NULL,
    [NotificationsEnabled] bit NOT NULL DEFAULT ((0)),
    [IsActive] bit NOT NULL DEFAULT ((1)),
    [CreateTS] datetime2(7) NOT NULL,
    [CreateId] int NOT NULL,
    [ModifiedAt] datetime2(7) NULL,
    [ModifiedBy] nvarchar(200) NULL,
    CONSTRAINT [PK_tblComplaintSlaProfile] PRIMARY KEY ([ComplaintSlaProfileID])
);
END
GO

IF OBJECT_ID('tblComplaintSlaRule') IS NULL
BEGIN
CREATE TABLE [tblComplaintSlaRule] (
    [ComplaintSlaRuleID] int IDENTITY(1,1) NOT NULL,
    [ClientCode] nvarchar(50) NULL,
    [ComplaintSlaProfileID] int NOT NULL,
    [Name] nvarchar(100) NULL,
    [Description] nvarchar(500) NULL,
    [Priority] int NOT NULL,
    [Classification] nvarchar(20) NULL,
    [ComplaintRootID] int NULL,
    [ManagingPartyID] int NULL,
    [IsActive] bit NOT NULL DEFAULT ((1)),
    [CreateTS] datetime2(7) NOT NULL,
    [CreateId] int NOT NULL,
    [ModifiedAt] datetime2(7) NULL,
    [ModifiedBy] nvarchar(200) NULL,
    CONSTRAINT [PK_tblComplaintSlaRule] PRIMARY KEY ([ComplaintSlaRuleID])
);
END
GO

IF OBJECT_ID('tblComplaintSlaWorkflow') IS NULL
BEGIN
CREATE TABLE [tblComplaintSlaWorkflow] (
    [ComplaintSlaWorkflowID] int IDENTITY(1,1) NOT NULL,
    [ClientCode] nvarchar(50) NULL,
    [ComplaintSlaProfileID] int NOT NULL,
    [Name] nvarchar(100) NOT NULL,
    [Description] nvarchar(500) NULL,
    [ThresholdDays] int NOT NULL,
    [Criticality] nvarchar(20) NOT NULL,
    [NotificationsEnabled] bit NOT NULL DEFAULT ((0)),
    [IsActive] bit NOT NULL DEFAULT ((1)),
    [CreateTS] datetime2(7) NOT NULL,
    [CreateId] int NOT NULL,
    [ModifiedAt] datetime2(7) NULL,
    [ModifiedBy] nvarchar(200) NULL,
    CONSTRAINT [PK_tblComplaintSlaWorkflow] PRIMARY KEY ([ComplaintSlaWorkflowID])
);
END
GO

IF OBJECT_ID('tblComplaintSource') IS NULL
BEGIN
CREATE TABLE [tblComplaintSource] (
    [ComplaintSourceID] int IDENTITY(1,1) NOT NULL,
    [Source] nvarchar(100) NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    [Classification] nvarchar(20) NULL,
    [Description] nvarchar(500) NULL,
    [IsInternal] bit NULL,
    CONSTRAINT [PK_tblComplaintSource] PRIMARY KEY ([ComplaintSourceID])
);
END
GO

IF OBJECT_ID('tblComplaintTemplate') IS NULL
BEGIN
CREATE TABLE [tblComplaintTemplate] (
    [ComplaintTemplateID] uniqueidentifier NOT NULL,
    [ClientCode] nvarchar(50) NOT NULL,
    [TemplateName] nvarchar(100) NOT NULL,
    [Body] nvarchar(MAX) NOT NULL,
    [ModifiedAt] datetime2(7) NOT NULL,
    [ModifiedBy] nvarchar(255) NOT NULL,
    [row_version] timestamp NOT NULL,
    CONSTRAINT [PK_tblComplaintTemplate] PRIMARY KEY ([ComplaintTemplateID])
);
END
GO

IF OBJECT_ID('tblComplaintThirdPartyContact') IS NULL
BEGIN
CREATE TABLE [tblComplaintThirdPartyContact] (
    [ComplaintThirdPartyContactID] int IDENTITY(1,1) NOT NULL,
    [ComplaintID] bigint NOT NULL,
    [ContactName] nvarchar(255) NULL,
    [Relationship] nvarchar(100) NULL,
    [Phone] nvarchar(30) NULL,
    [Email] nvarchar(254) NULL,
    [PostalAddress] nvarchar(500) NULL,
    [StatusId] int NOT NULL,
    [CreateID] int NOT NULL,
    [CreateSessionId] int NOT NULL,
    [CreateTS] datetime2(7) NOT NULL,
    CONSTRAINT [PK_tblComplaintThirdPartyContact] PRIMARY KEY ([ComplaintThirdPartyContactID])
);
END
GO

IF OBJECT_ID('tblComplaintType') IS NULL
BEGIN
CREATE TABLE [tblComplaintType] (
    [ComplaintTypeId] int IDENTITY(1,1) NOT NULL,
    [ComplaintType] nvarchar(100) NOT NULL,
    [Description] nvarchar(200) NULL,
    [CreateId] int NOT NULL,
    [CreateSessionId] int NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyId] int NULL,
    [ModifySessionId] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveId] int NULL,
    [InactiveSessionId] int NULL,
    [InactiveTS] datetime NULL,
    [StatusId] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintType] PRIMARY KEY ([ComplaintTypeId])
);
END
GO

IF OBJECT_ID('tblComplaintUpheld') IS NULL
BEGIN
CREATE TABLE [tblComplaintUpheld] (
    [ComplaintUpheldID] int IDENTITY(1,1) NOT NULL,
    [ComplaintUpheld] nvarchar(250) NULL,
    [CreateID] int NOT NULL,
    [CreateSessionID] int NOT NULL,
    [CreateTS] datetime NOT NULL DEFAULT (getdate()),
    [ModifyID] int NULL,
    [ModifySessionID] int NULL,
    [ModifyTS] datetime NULL,
    [InactiveID] int NULL,
    [InactiveSessionID] int NULL,
    [InactiveTS] datetime NULL,
    [StatusID] int NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_tblComplaintUpheld] PRIMARY KEY ([ComplaintUpheldID])
);
END
GO

-- Foreign keys (added after all tables exist, to avoid ordering issues)

IF OBJECT_ID('FK_tblComplaint_tblAccount', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblAccount') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblAccount] FOREIGN KEY ([AccountId]) REFERENCES [tblAccount] ([AccountID]);
GO

IF OBJECT_ID('FK_tblComplaint_tblCommunicationPreference', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblCommunicationPreference') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblCommunicationPreference] FOREIGN KEY ([CommunicationPreferenceID]) REFERENCES [tblCommunicationPreference] ([CommunicationPreferenceID]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplainant', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplainant') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplainant] FOREIGN KEY ([ComplainantId]) REFERENCES [tblComplainant] ([ComplainantId]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintAssistance', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintAssistance') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintAssistance] FOREIGN KEY ([ComplaintAssistanceId]) REFERENCES [tblComplaintAssistance] ([ComplaintAssistanceID]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintContact', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintContact') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintContact] FOREIGN KEY ([ComplaintContactId]) REFERENCES [tblComplaintContact] ([ComplaintContactId]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintFCACategory', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintFCACategory') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintFCACategory] FOREIGN KEY ([FCACategoryId]) REFERENCES [tblComplaintFCACategory] ([ComplaintFCACategoryId]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintLevel', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintLevel') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintLevel] FOREIGN KEY ([ComplaintLevelId]) REFERENCES [tblComplaintLevel] ([ComplaintLevelID]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintMethod', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintMethod') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintMethod] FOREIGN KEY ([ComplaintMethodId]) REFERENCES [tblComplaintMethod] ([ComplaintMethodId]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintOriginator', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintOriginator') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintOriginator] FOREIGN KEY ([ComplaintOriginatorId]) REFERENCES [tblComplaintOriginator] ([ComplaintOriginatorID]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintOutcome', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintOutcome') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintOutcome] FOREIGN KEY ([ComplaintOutcomeId]) REFERENCES [tblComplaintOutcome] ([ComplaintOutcomeId]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintPriority', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintPriority') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintPriority] FOREIGN KEY ([ComplaintPriorityId]) REFERENCES [tblComplaintPriority] ([ComplaintPriorityID]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintRoot', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintRoot') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintRoot] FOREIGN KEY ([ComplaintRootId]) REFERENCES [tblComplaintRoot] ([ComplaintRootId]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintSeverity', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintSeverity') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintSeverity] FOREIGN KEY ([ComplaintSeverityId]) REFERENCES [tblComplaintSeverity] ([ComplaintSeverityID]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintSource', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintSource') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintSource] FOREIGN KEY ([ComplaintSourceId]) REFERENCES [tblComplaintSource] ([ComplaintSourceID]);
GO

IF OBJECT_ID('FK_tblComplaint_tblComplaintType', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblComplaintType') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblComplaintType] FOREIGN KEY ([ComplaintTypeId]) REFERENCES [tblComplaintType] ([ComplaintTypeId]);
GO

IF OBJECT_ID('FK_tblComplaint_tblResolutionMethod', 'F') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL AND OBJECT_ID('tblResolutionMethod') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD CONSTRAINT [FK_tblComplaint_tblResolutionMethod] FOREIGN KEY ([ResolutionMethodId]) REFERENCES [tblResolutionMethod] ([ResolutionMethodID]);
GO

IF OBJECT_ID('FK_tblComplaint_Notification_tblComplaint_ComplaintID', 'F') IS NULL AND OBJECT_ID('tblComplaint_Notification') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaint_Notification] ADD CONSTRAINT [FK_tblComplaint_Notification_tblComplaint_ComplaintID] FOREIGN KEY ([ComplaintID]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

IF OBJECT_ID('FK_tblComplaintAccountLink_tblComplaint_ComplaintID', 'F') IS NULL AND OBJECT_ID('tblComplaintAccountLink') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaintAccountLink] ADD CONSTRAINT [FK_tblComplaintAccountLink_tblComplaint_ComplaintID] FOREIGN KEY ([ComplaintID]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

IF OBJECT_ID('FK_tblComplaintAsicOutcome_tblComplaint_ComplaintID', 'F') IS NULL AND OBJECT_ID('tblComplaintAsicOutcome') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaintAsicOutcome] ADD CONSTRAINT [FK_tblComplaintAsicOutcome_tblComplaint_ComplaintID] FOREIGN KEY ([ComplaintID]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

IF OBJECT_ID('FK_tblComplaintAsicOutcome_tblComplaintOutcome', 'F') IS NULL AND OBJECT_ID('tblComplaintAsicOutcome') IS NOT NULL AND OBJECT_ID('tblComplaintOutcome') IS NOT NULL
    ALTER TABLE [tblComplaintAsicOutcome] ADD CONSTRAINT [FK_tblComplaintAsicOutcome_tblComplaintOutcome] FOREIGN KEY ([ComplaintOutcomeID]) REFERENCES [tblComplaintOutcome] ([ComplaintOutcomeId]);
GO

IF OBJECT_ID('FK_tblComplaintAssignee_Complaints_ComplaintID', 'F') IS NULL AND OBJECT_ID('tblComplaintAssignee') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaintAssignee] ADD CONSTRAINT [FK_tblComplaintAssignee_Complaints_ComplaintID] FOREIGN KEY ([ComplaintID]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

IF OBJECT_ID('FK_tblComplaintClientReferral_tblComplaint', 'F') IS NULL AND OBJECT_ID('tblComplaintClientReferral') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaintClientReferral] ADD CONSTRAINT [FK_tblComplaintClientReferral_tblComplaint] FOREIGN KEY ([ComplaintID]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

IF OBJECT_ID('FK_tblComplaintDecision_tblComplaintDecisionType', 'F') IS NULL AND OBJECT_ID('tblComplaintDecision') IS NOT NULL AND OBJECT_ID('tblComplaintDecisionType') IS NOT NULL
    ALTER TABLE [tblComplaintDecision] ADD CONSTRAINT [FK_tblComplaintDecision_tblComplaintDecisionType] FOREIGN KEY ([ComplaintDecisionTypeId]) REFERENCES [tblComplaintDecisionType] ([ComplaintDecisionTypeId]);
GO

IF OBJECT_ID('FK_tblComplaintDecision_tblContact', 'F') IS NULL AND OBJECT_ID('tblComplaintDecision') IS NOT NULL AND OBJECT_ID('tblContact') IS NOT NULL
    ALTER TABLE [tblComplaintDecision] ADD CONSTRAINT [FK_tblComplaintDecision_tblContact] FOREIGN KEY ([OperatorId]) REFERENCES [tblContact] ([ContactID]);
GO

IF OBJECT_ID('FK_tblComplaintDocument_tblComplaint', 'F') IS NULL AND OBJECT_ID('tblComplaintDocument') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaintDocument] ADD CONSTRAINT [FK_tblComplaintDocument_tblComplaint] FOREIGN KEY ([ComplaintId]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

IF OBJECT_ID('FK_tblComplaintDocument_tblComplaintDocumentType', 'F') IS NULL AND OBJECT_ID('tblComplaintDocument') IS NOT NULL AND OBJECT_ID('tblComplaintDocumentType') IS NOT NULL
    ALTER TABLE [tblComplaintDocument] ADD CONSTRAINT [FK_tblComplaintDocument_tblComplaintDocumentType] FOREIGN KEY ([ComplaintDocumentTypeId]) REFERENCES [tblComplaintDocumentType] ([ComplaintDocumentTypeId]);
GO

IF OBJECT_ID('FK_tblComplaintDocumentChecklist_tblComplaint', 'F') IS NULL AND OBJECT_ID('tblComplaintDocumentChecklist') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaintDocumentChecklist] ADD CONSTRAINT [FK_tblComplaintDocumentChecklist_tblComplaint] FOREIGN KEY ([ComplaintID]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

IF OBJECT_ID('FK_tblComplaintEscalation_tblComplaint_ComplaintID', 'F') IS NULL AND OBJECT_ID('tblComplaintEscalation') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaintEscalation] ADD CONSTRAINT [FK_tblComplaintEscalation_tblComplaint_ComplaintID] FOREIGN KEY ([ComplaintID]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

IF OBJECT_ID('FK_TblComplaintHistories_tblComplaint_ComplaintId', 'F') IS NULL AND OBJECT_ID('TblComplaintHistories') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [TblComplaintHistories] ADD CONSTRAINT [FK_TblComplaintHistories_tblComplaint_ComplaintId] FOREIGN KEY ([ComplaintId]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

IF OBJECT_ID('FK_TblComplaintHistories_tblComplaintOutcome_ComplaintOutcomeId', 'F') IS NULL AND OBJECT_ID('TblComplaintHistories') IS NOT NULL AND OBJECT_ID('tblComplaintOutcome') IS NOT NULL
    ALTER TABLE [TblComplaintHistories] ADD CONSTRAINT [FK_TblComplaintHistories_tblComplaintOutcome_ComplaintOutcomeId] FOREIGN KEY ([ComplaintOutcomeId]) REFERENCES [tblComplaintOutcome] ([ComplaintOutcomeId]);
GO

IF OBJECT_ID('FK_tblComplaintIssue_Complaints_ComplaintID', 'F') IS NULL AND OBJECT_ID('tblComplaintIssue') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaintIssue] ADD CONSTRAINT [FK_tblComplaintIssue_Complaints_ComplaintID] FOREIGN KEY ([ComplaintID]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

IF OBJECT_ID('FK_tblComplaintIssue_tblComplaintRoot_ComplaintRootId', 'F') IS NULL AND OBJECT_ID('tblComplaintIssue') IS NOT NULL AND OBJECT_ID('tblComplaintRoot') IS NOT NULL
    ALTER TABLE [tblComplaintIssue] ADD CONSTRAINT [FK_tblComplaintIssue_tblComplaintRoot_ComplaintRootId] FOREIGN KEY ([ComplaintRootID]) REFERENCES [tblComplaintRoot] ([ComplaintRootId]);
GO

IF OBJECT_ID('FK_tblComplaintIssue_tblComplaintRootSecondary_ComplaintRootSecondaryId', 'F') IS NULL AND OBJECT_ID('tblComplaintIssue') IS NOT NULL AND OBJECT_ID('tblComplaintRootSecondary') IS NOT NULL
    ALTER TABLE [tblComplaintIssue] ADD CONSTRAINT [FK_tblComplaintIssue_tblComplaintRootSecondary_ComplaintRootSecondaryId] FOREIGN KEY ([ComplaintRootSecondaryID]) REFERENCES [tblComplaintRootSecondary] ([ComplaintRootSecondaryID]);
GO

IF OBJECT_ID('FK_tblComplaintProduct_tblComplaint_ComplaintID', 'F') IS NULL AND OBJECT_ID('tblComplaintProduct') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaintProduct] ADD CONSTRAINT [FK_tblComplaintProduct_tblComplaint_ComplaintID] FOREIGN KEY ([ComplaintID]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

IF OBJECT_ID('FK_tblComplaintResolution_tblComplaintResolutionStage', 'F') IS NULL AND OBJECT_ID('tblComplaintResolution') IS NOT NULL AND OBJECT_ID('tblComplaintResolutionStage') IS NOT NULL
    ALTER TABLE [tblComplaintResolution] ADD CONSTRAINT [FK_tblComplaintResolution_tblComplaintResolutionStage] FOREIGN KEY ([ComplaintResolutionStageID]) REFERENCES [tblComplaintResolutionStage] ([ComplaintResolutionStageID]);
GO

IF OBJECT_ID('FK_tblComplaintRoot_tblComplaintRootType', 'F') IS NULL AND OBJECT_ID('tblComplaintRoot') IS NOT NULL AND OBJECT_ID('tblComplaintRootType') IS NOT NULL
    ALTER TABLE [tblComplaintRoot] ADD CONSTRAINT [FK_tblComplaintRoot_tblComplaintRootType] FOREIGN KEY ([RootCauseTypeId]) REFERENCES [tblComplaintRootType] ([ComplaintRootTypeId]);
GO

IF OBJECT_ID('FK_tblComplaintSlaNotification_tblComplaintSlaWorkflow', 'F') IS NULL AND OBJECT_ID('tblComplaintSlaNotification') IS NOT NULL AND OBJECT_ID('tblComplaintSlaWorkflow') IS NOT NULL
    ALTER TABLE [tblComplaintSlaNotification] ADD CONSTRAINT [FK_tblComplaintSlaNotification_tblComplaintSlaWorkflow] FOREIGN KEY ([ComplaintSlaWorkflowID]) REFERENCES [tblComplaintSlaWorkflow] ([ComplaintSlaWorkflowID]);
GO

IF OBJECT_ID('FK_tblComplaintSlaRule_tblComplaintSlaProfile', 'F') IS NULL AND OBJECT_ID('tblComplaintSlaRule') IS NOT NULL AND OBJECT_ID('tblComplaintSlaProfile') IS NOT NULL
    ALTER TABLE [tblComplaintSlaRule] ADD CONSTRAINT [FK_tblComplaintSlaRule_tblComplaintSlaProfile] FOREIGN KEY ([ComplaintSlaProfileID]) REFERENCES [tblComplaintSlaProfile] ([ComplaintSlaProfileID]);
GO

IF OBJECT_ID('FK_tblComplaintSlaWorkflow_tblComplaintSlaProfile', 'F') IS NULL AND OBJECT_ID('tblComplaintSlaWorkflow') IS NOT NULL AND OBJECT_ID('tblComplaintSlaProfile') IS NOT NULL
    ALTER TABLE [tblComplaintSlaWorkflow] ADD CONSTRAINT [FK_tblComplaintSlaWorkflow_tblComplaintSlaProfile] FOREIGN KEY ([ComplaintSlaProfileID]) REFERENCES [tblComplaintSlaProfile] ([ComplaintSlaProfileID]);
GO

IF OBJECT_ID('FK_tblComplaintThirdPartyContact_tblComplaint_ComplaintID', 'F') IS NULL AND OBJECT_ID('tblComplaintThirdPartyContact') IS NOT NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaintThirdPartyContact] ADD CONSTRAINT [FK_tblComplaintThirdPartyContact_tblComplaint_ComplaintID] FOREIGN KEY ([ComplaintID]) REFERENCES [tblComplaint] ([ComplaintId]);
GO

-- tblComplaint has no Z_REF/Z_ID of its own on test-debtrak, unlike its sibling framework
-- tables (tblPayment, tblHardship, tblSMSOutput). 77.tblComplaint.sql needs one to
-- correlate its own just-inserted rows for the child-table inserts that follow, rather
-- than reusing ClientReferenceNumber - a real client-facing field ("Complaints Data
-- Mapping.xlsx" confirms 6 of 17 real client reports carry it as the client's own case
-- number) that a future client's data would otherwise silently lose.
IF COL_LENGTH('tblComplaint', 'Z_REF') IS NULL AND OBJECT_ID('tblComplaint') IS NOT NULL
    ALTER TABLE [tblComplaint] ADD [Z_REF] NVARCHAR(400) NULL;
GO
