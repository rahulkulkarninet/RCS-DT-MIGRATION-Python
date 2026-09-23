--USE [sqldb-glass-dev-rc]
--go

DECLARE @BatchSize INT = 100000;
DECLARE @RowsAffected INT = 1;
DECLARE @LoadID INT = $(LoadID);


DECLARE @Failed     BIT = 0;
DECLARE @ErrNumber  INT;
DECLARE @ErrLine    INT;
DECLARE @ErrMessage NVARCHAR(2048);


IF OBJECT_ID(N'dbo.tblAccount', N'U') IS NULL
BEGIN
    DECLARE @WrongDb NVARCHAR(2048) =
        N'This is database [' + DB_NAME() + N'], which has no dbo.tblAccount. '
      + N'Run DT Delete Migrated Data against the DebtRak application database.';
    THROW 50001, @WrongDb, 1;
END


DECLARE @RestoreConstraintTrust BIT = 0;

IF OBJECT_ID('tempdb..#ToggleTables') IS NOT NULL DROP TABLE #ToggleTables;
CREATE TABLE #ToggleTables (TableName SYSNAME PRIMARY KEY);

INSERT INTO #ToggleTables (TableName)
VALUES  ('tblLastLetterSent'), ('tblAlert'), ('tblWorkflowLine_NavigationAction'),
        ('tblWorkflowHistory'), ('tblWorkflowLine_Contact'), ('tblWorkflowLineAudit'),
        ('tblWorkflowLine'), ('tblBankAccount_Contact'), ('tblHardshipHistory'),
        ('tblHardship'), ('tblAccountInsurance'), ('tblIncidentPolice'),
        ('tblIncidentWitness'), ('tblAccountIncident'), ('tblAccount_Contact'),
        ('tblAddress'), ('tblAddressAudit'), ('tblLog'), ('tblLogin'),
        ('tblAccount_Contact_DataDictionaryField'), ('tblContact_DebtorStatus'),
        ('tblContactDetail'), ('tblContactPaymentReferences'),
        ('tblContactProfileAudit'), ('tblContactProfile'), ('tblContactDetailAudit'),
        ('tblCorrespondenceHistory'), ('tblProofOfIdentity'), ('tblSMSOutput'),
        ('tblEmail'), ('tblCommunication'), ('tblCommunication_Contact'),
        ('tblLetter_Principal'), ('tblLetter'), ('tblLetterData'), ('tblLetterPDF'),
        ('tblDocumentBlobVersion'), ('tblDocumentBlob'), ('tblDocument'),
        ('tblMetaValue_DocumentGroup'), ('tblContactAudit'), ('tblContact'),
        ('tblDebtContact'), ('tblAccountSpecifics'), ('tblAllocation'),
        ('tblPrincipalAudit'), ('tblPrincipal'), ('tblPaymentAudit'), ('tblPayment'),
        ('tblBankTransaction'), ('tblCostAudit'), ('tblCost'), ('tblTransaction'),
        ('tblTask'), ('tblEntry'), ('tblArrangement_ReminderMethod'),
        ('tblArrangementSchedule'), ('tblArrangementAudit'), ('tblArrangement'),
        ('tblArrangement_Contact'), ('tblInvoice'), ('tblMetaValue_AccountSpecifics'),
        ('tblMetaValue_AccountSpecificsGroup'), ('tblCallHistory'), ('tblAccountLock'),
        ('tblTimeOnAccount_Outcome'), ('tblTimeOnAccount'),
        ('tblAccount_Contact_Transaction'), ('tblAccount_Entity_Transaction'),
        ('tblAccount_Pool'), ('tblPayno'), ('tblMedia'), ('tblAccountLinkHistory'),
        ('tblCallExclusion'), ('tblWorkflowTriggerBatch'), ('tblWorkflowTrigger'),
        ('tblAccount_Token'), ('tblAccount'),
        -- Added with the tblAdjustment delete block below. tblBillableTime was
        -- already being deleted from without ever appearing in either list.
        ('tblAdjustment'), ('tblBillableTime');

-- Snapshot the state we are about to destroy.
IF OBJECT_ID('tempdb..#ConstraintState') IS NOT NULL DROP TABLE #ConstraintState;
CREATE TABLE #ConstraintState
    (
      SchemaName     SYSNAME ,
      TableName      SYSNAME ,
      ConstraintName SYSNAME ,
      WasDisabled    BIT ,
      WasTrusted     BIT
    );


IF OBJECT_ID('tempdb..#Alterable') IS NOT NULL DROP TABLE #Alterable;
SELECT      t.object_id ,
            SchemaName = SCHEMA_NAME(t.schema_id) ,
            TableName  = t.name
INTO        #Alterable
FROM        sys.tables t
            INNER JOIN #ToggleTables tt ON tt.TableName = t.name

WHERE       SCHEMA_NAME(t.schema_id) = 'dbo'
            AND HAS_PERMS_BY_NAME(QUOTENAME(SCHEMA_NAME(t.schema_id)) + '.'
                                  + QUOTENAME(t.name), 'OBJECT', 'ALTER') = 1;

DECLARE @Alterable INT = (SELECT COUNT(*) FROM #Alterable);
DECLARE @Present   INT = (SELECT COUNT(*) FROM sys.tables t
                          INNER JOIN #ToggleTables tt ON tt.TableName = t.name
                          WHERE SCHEMA_NAME(t.schema_id) = 'dbo');


INSERT INTO #ConstraintState (SchemaName, TableName, ConstraintName, WasDisabled, WasTrusted)
SELECT  a.SchemaName, a.TableName, fk.name, fk.is_disabled,
        CASE WHEN fk.is_not_trusted = 0 THEN 1 ELSE 0 END
FROM    sys.foreign_keys fk
        INNER JOIN #Alterable a ON a.object_id = fk.parent_object_id
UNION ALL
SELECT  a.SchemaName, a.TableName, cc.name, cc.is_disabled,
        CASE WHEN cc.is_not_trusted = 0 THEN 1 ELSE 0 END
FROM    sys.check_constraints cc
        INNER JOIN #Alterable a ON a.object_id = cc.parent_object_id;

SELECT  @Present                        AS tables_present,
        @Alterable                      AS tables_this_login_can_toggle,
        @Present - @Alterable           AS tables_skipped_no_alter_permission,
        (SELECT COUNT(*) FROM #ConstraintState) AS constraints_captured,
        CASE WHEN @Alterable = 0
             THEN 'No ALTER permission: constraints stay ON for the whole run. '
                + 'Deletes will still work but must be correctly ordered.'
             WHEN @Alterable < @Present
             THEN 'Partial ALTER permission: some tables keep their constraints on.'
             ELSE 'All listed tables will have their constraints disabled and restored.'
        END                             AS constraint_handling;

DECLARE @ToggleSQL NVARCHAR(MAX) = N'';

SELECT  @ToggleSQL = @ToggleSQL + N'ALTER TABLE '
        + QUOTENAME(a.SchemaName) + N'.' + QUOTENAME(a.TableName)
        + N' NOCHECK CONSTRAINT ALL;' + CHAR(10)
FROM    #Alterable a;

BEGIN TRY


IF @ToggleSQL <> N''
    EXEC sp_executesql @ToggleSQL;



IF OBJECT_ID(N'[dbo].[tblComplaint]', N'U') IS NOT NULL
BEGIN
    -- Set to 0 to roll back this load only and leave previously stranded rows be.
    DECLARE @SweepOrphanedComplaints BIT = 1;

    DECLARE @ComplaintSQL  NVARCHAR(MAX);
    DECLARE @ChildSQL      NVARCHAR(MAX) = N'';
    DECLARE @ScopedRows    INT = 0;
    DECLARE @OrphanRows    INT = 0;
    DECLARE @Remaining     INT = 0;

    IF OBJECT_ID('tempdb..#ComplaintScope') IS NOT NULL DROP TABLE #ComplaintScope;
    CREATE TABLE #ComplaintScope (ComplaintId BIGINT PRIMARY KEY);

    -- 1. Freeze the target set while tblAccount still holds this load's rows.
    SET @ComplaintSQL = N'
        INSERT INTO #ComplaintScope (ComplaintId)
        SELECT  C.ComplaintId
        FROM    dbo.tblComplaint C
                INNER JOIN dbo.tblAccount A ON A.AccountID = C.AccountId
        WHERE   A.LoadID = @LoadID;';
    EXEC sp_executesql @ComplaintSQL, N'@LoadID INT', @LoadID = @LoadID;
    SELECT @ScopedRows = COUNT(*) FROM #ComplaintScope;

    -- 2. Rows an earlier rollback stranded. AccountId IS NULL is deliberately not
    --    swept: the module supports account-less cases (HasNoAccount), and those
    --    are legitimate rather than orphaned.
    IF @SweepOrphanedComplaints = 1
    BEGIN
        SET @ComplaintSQL = N'
            INSERT INTO #ComplaintScope (ComplaintId)
            SELECT  C.ComplaintId
            FROM    dbo.tblComplaint C
            WHERE   C.AccountId IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM dbo.tblAccount A
                                    WHERE  A.AccountID = C.AccountId)
                    AND NOT EXISTS (SELECT 1 FROM #ComplaintScope S
                                    WHERE  S.ComplaintId = C.ComplaintId);';
        EXEC sp_executesql @ComplaintSQL;
        SELECT @OrphanRows = COUNT(*) - @ScopedRows FROM #ComplaintScope;
    END

    -- 3. Children, one batched delete per table that references tblComplaint.
    --    Single-column foreign keys only; a composite one would need its own join
    --    and is skipped rather than generated wrongly.
    SELECT  @ChildSQL = @ChildSQL + N'
        WHILE 1 = 1
        BEGIN
            DELETE TOP (@BatchSize) CH
            FROM   ' + QUOTENAME(SCHEMA_NAME(t.schema_id)) + N'.' + QUOTENAME(t.name) + N' CH
                   INNER JOIN #ComplaintScope S ON S.ComplaintId = CH.' + QUOTENAME(c.name) + N';
            IF @@ROWCOUNT = 0 BREAK;
        END;'
    FROM    sys.foreign_keys fk
            INNER JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
            INNER JOIN sys.tables  t ON t.object_id  = fk.parent_object_id
            INNER JOIN sys.columns c ON c.object_id  = fkc.parent_object_id
                                    AND c.column_id  = fkc.parent_column_id
    WHERE   fk.referenced_object_id = OBJECT_ID(N'dbo.tblComplaint')
            AND fk.parent_object_id <> fk.referenced_object_id
            AND (SELECT COUNT(*) FROM sys.foreign_key_columns x
                 WHERE x.constraint_object_id = fk.object_id) = 1;

    IF @ChildSQL <> N''
        EXEC sp_executesql @ChildSQL, N'@BatchSize INT', @BatchSize = @BatchSize;

    -- 4. The complaints themselves.
    SET @ComplaintSQL = N'
        WHILE 1 = 1
        BEGIN
            DELETE TOP (@BatchSize) C
            FROM   dbo.tblComplaint C
                   INNER JOIN #ComplaintScope S ON S.ComplaintId = C.ComplaintId;
            IF @@ROWCOUNT = 0 BREAK;
        END;';
    EXEC sp_executesql @ComplaintSQL, N'@BatchSize INT', @BatchSize = @BatchSize;

    -- Anything still standing means a child delete could not clear the way.
    SET @ComplaintSQL = N'
        SELECT  @out = COUNT(*)
        FROM    dbo.tblComplaint C
                INNER JOIN #ComplaintScope S ON S.ComplaintId = C.ComplaintId;';
    EXEC sp_executesql @ComplaintSQL, N'@out INT OUTPUT', @out = @Remaining OUTPUT;

    SELECT  @ScopedRows                             AS complaints_in_load,
            @OrphanRows                             AS complaints_stranded_earlier,
            @ScopedRows + @OrphanRows - @Remaining  AS complaints_deleted,
            @Remaining                              AS complaints_left_behind;

    DROP TABLE #ComplaintScope;
END

SELECT 1--Batch delete for tblHardshipHistory (child of tblHardship)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) HH
	FROM tblHardshipHistory HH
	INNER JOIN tblHardship H ON H.HardshipID = HH.HardshipID
	INNER JOIN dbo.tblAccount A ON A.AccountID = H.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1--Batch delete for tblHardship (populated outside this repo - nothing here inserts it)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) H
	FROM tblHardship H
	INNER JOIN dbo.tblAccount A ON A.AccountID = H.AccountID
	WHERE A.LoadID = @LoadID
END


IF OBJECT_ID(N'[dbo].[tblAdjustment]', N'U') IS NOT NULL
BEGIN
    DECLARE @AdjSQL       NVARCHAR(MAX);
    DECLARE @AdjChildSQL  NVARCHAR(MAX) = N'';
    DECLARE @AdjScoped    INT = 0;
    DECLARE @AdjRemaining INT = 0;

    IF OBJECT_ID('tempdb..#AdjustmentScope') IS NOT NULL DROP TABLE #AdjustmentScope;
    CREATE TABLE #AdjustmentScope (AdjustmentID BIGINT PRIMARY KEY);

    INSERT INTO #AdjustmentScope (AdjustmentID)
    SELECT  ADJ.AdjustmentID
    FROM    dbo.tblAdjustment ADJ
            INNER JOIN dbo.tblAccount A ON A.AccountID = ADJ.AccountID
    WHERE   A.LoadID = @LoadID;

    SELECT @AdjScoped = COUNT(*) FROM #AdjustmentScope;

    UPDATE  ADJ
    SET     ADJ.Source_AdjustmentID = NULL
    FROM    dbo.tblAdjustment ADJ
            INNER JOIN #AdjustmentScope S  ON S.AdjustmentID  = ADJ.AdjustmentID
            INNER JOIN #AdjustmentScope S2 ON S2.AdjustmentID = ADJ.Source_AdjustmentID;

    SELECT  @AdjChildSQL = @AdjChildSQL + N'
        WHILE 1 = 1
        BEGIN
            DELETE TOP (@BatchSize) CH
            FROM   ' + QUOTENAME(SCHEMA_NAME(t.schema_id)) + N'.' + QUOTENAME(t.name) + N' CH
                   INNER JOIN #AdjustmentScope S ON S.AdjustmentID = CH.' + QUOTENAME(c.name) + N';
            IF @@ROWCOUNT = 0 BREAK;
        END;'
    FROM    sys.foreign_keys fk
            INNER JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
            INNER JOIN sys.tables  t ON t.object_id  = fk.parent_object_id
            INNER JOIN sys.columns c ON c.object_id  = fkc.parent_object_id
                                    AND c.column_id  = fkc.parent_column_id
    WHERE   fk.referenced_object_id = OBJECT_ID(N'dbo.tblAdjustment')
            AND fk.parent_object_id <> fk.referenced_object_id
            AND (SELECT COUNT(*) FROM sys.foreign_key_columns x
                 WHERE x.constraint_object_id = fk.object_id) = 1;

    IF @AdjChildSQL <> N''
        EXEC sp_executesql @AdjChildSQL, N'@BatchSize INT', @BatchSize = @BatchSize;

    WHILE 1 = 1
    BEGIN
        DELETE TOP (@BatchSize) ADJ
        FROM   dbo.tblAdjustment ADJ
               INNER JOIN #AdjustmentScope S ON S.AdjustmentID = ADJ.AdjustmentID;
        IF @@ROWCOUNT = 0 BREAK;
    END;

    SELECT  @AdjRemaining = COUNT(*)
    FROM    dbo.tblAdjustment ADJ
            INNER JOIN #AdjustmentScope S ON S.AdjustmentID = ADJ.AdjustmentID;

    SELECT  @AdjScoped                  AS adjustments_in_load,
            @AdjScoped - @AdjRemaining  AS adjustments_deleted,
            @AdjRemaining               AS adjustments_left_behind;

    DROP TABLE #AdjustmentScope;
END

SELECT 1--Batch delete for tblLastLetterSent
while (@@ROWCOUNT >0)  
BEGIN  
	DELETE TOP (@BatchSize) LLS 
	FROM tblLastLetterSent LLS
	INNER JOIN tblWorkflowLine WF on LLS.WorkflowLineID = WF.WorkflowLineID
	INNER JOIN tblAccount A ON WF.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
		
	
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) WFLNA
	FROM tblWorkflowLine_NavigationAction WFLNA
	INNER JOIN tblWorkflowLine WF on WFLNA.WorkflowLineID = WF.WorkflowLineID
	INNER JOIN tblAccount A ON WF.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID	
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) A
	FROM tblAlert A
	INNER JOIN tblWorkflowLine WF on A.WorkflowLineID = WF.WorkflowLineID
	INNER JOIN tblAccount AC ON WF.AccountID = AC.AccountID
	WHERE AC.LoadID = @LoadID		
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) WFH
	FROM tblWorkflowHistory WFH
	INNER JOIN tblWorkflowLine WF on WFH.WorkflowLineID = WF.WorkflowLineID
	INNER JOIN tblAccount A ON WF.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) WFC
	FROM tblWorkflowLine_Contact WFC
	INNER JOIN tblWorkflowLine WF on WFC.WorkflowLineID = WF.WorkflowLineID
	INNER JOIN tblAccount A ON WF.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1--Batch delete for tblWorkflowLineAudit
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) WFLA
	FROM tblWorkflowLineAudit WFLA
	WHERE WFLA.LoadID = @LoadID
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) WF
	FROM tblWorkflowLine WF
	INNER JOIN tblAccount A ON WF.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1--Batch delete for tblCorrespondenceHistory (by account)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CHIST
	FROM tblCorrespondenceHistory CHIST
	INNER JOIN tblAccount A ON A.AccountID = CHIST.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1--Batch delete for tblCorrespondenceHistory (by contact - the letter insert does not filter contacts by LoadID)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CHIST
	FROM tblCorrespondenceHistory CHIST
	INNER JOIN tblContact C ON C.ContactID = CHIST.ContactID
	WHERE C.LoadID = @LoadID
END

SELECT 1--Batch delete for tblBankAccount_Contact (created by the application, not the migration - the link dies with the contact)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) BAC
	FROM tblBankAccount_Contact BAC
	INNER JOIN tblContact C ON C.ContactID = BAC.ContactID
	WHERE C.LoadID = @LoadID
END

SELECT 1--Batch delete for tblAccountInsurance (child of tblAccountIncident, references tblContact)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) AINS
	FROM tblAccountInsurance AINS
	WHERE AINS.LoadID = @LoadID
END

SELECT 1--Batch delete for tblIncidentPolice (child of tblAccountIncident)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) IP
	FROM tblIncidentPolice IP
	WHERE IP.LoadID = @LoadID
END

SELECT 1--Batch delete for tblIncidentWitness (child of tblAccountIncident, references tblContact)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) IW
	FROM tblIncidentWitness IW
	WHERE IW.LoadID = @LoadID
END

SELECT 1--Batch delete for tblAccountIncident (references tblAccount and tblAddress)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) AI
	FROM tblAccountIncident AI
	WHERE AI.LoadID = @LoadID
END

SELECT 1--Batch delete for tblProofOfIdentity (rows stamped by this load)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) POI
	FROM tblProofOfIdentity POI
	WHERE POI.LoadID = @LoadID
END

SELECT 1--Batch delete for tblProofOfIdentity (by account)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) POI
	FROM tblProofOfIdentity POI
	INNER JOIN tblAccount A ON A.AccountID = POI.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1--Batch delete for tblProofOfIdentity (by contact)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) POI
	FROM tblProofOfIdentity POI
	INNER JOIN tblContact C ON C.ContactID = POI.ContactID
	WHERE C.LoadID = @LoadID
END



SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CDS
	FROM tblContact_DebtorStatus CDS
	INNER JOIN dbo.tblContact C ON C.ContactID = CDS.ContactID
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE A.LoadID = @LoadID			
END



SELECT 1
WHILE (@@ROWCOUNT >0)
BEGIN
	DELETE TOP (@BatchSize) L
	FROM tblLog L
	INNER JOIN dbo.tblContact C ON C.ContactID = L.ContactID
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
WHILE (@@ROWCOUNT >0)
BEGIN
	DELETE TOP (@BatchSize) L
	FROM tblLogin L
	INNER JOIN dbo.tblContact C ON C.ContactID = L.ContactID
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
WHILE (@@ROWCOUNT >0)
BEGIN
	DELETE TOP (@BatchSize) CPR
	FROM tblContactPaymentReferences CPR
	INNER JOIN dbo.tblContact C ON C.ContactID = CPR.ContactID
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
WHILE (@@ROWCOUNT >0)
BEGIN
	DELETE TOP (@BatchSize) CPRA
	FROM tblContactProfileAudit CPRA	
	INNER JOIN dbo.tblContact C ON C.ContactID = CPRA.ContactID
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
WHILE (@@ROWCOUNT >0)
BEGIN
	DELETE TOP (@BatchSize) CPR
	FROM tblContactProfile CPR
	INNER JOIN dbo.tblContact C ON C.ContactID = CPR.ContactID
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE A.LoadID = @LoadID
END



SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) ADR
	FROM tblAddress ADR
	INNER JOIN dbo.tblContact C ON C.ContactID = ADR.ContactID
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE A.LoadID = @LoadID
	
	
END


SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) ACDD
	FROM tblAccount_Contact_DataDictionaryField ACDD
	INNER JOIN dbo.tblContact C ON C.ContactID = ACDD.ContactID
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE A.LoadID = @LoadID			
END


SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CDA
	FROM dbo.tblContactDetailAudit CDA	
	WHERE CDA.LoadID = @LoadID
	
	
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CD
	FROM dbo.tblContactDetail CD
	INNER JOIN dbo.tblContact C ON C.ContactID = CD.ContactID
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) SMS
	FROM tblSMSOutput SMS
	INNER JOIN tblAccount A ON SMS.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblEmail
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) E
	FROM tblEmail E
	INNER JOIN tblAccount A ON A.AccountID = E.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblCommunication
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) Comm
	FROM dbo.tblCommunication Comm 
	INNER JOIN tblEmail E on E.CommunicationID = Comm.CommunicationID
	INNER JOIN dbo.tblAccount A ON A.AccountID = E.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblCommunication_Contact
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CommC
	FROM dbo.tblCommunication_Contact CommC 
	INNER JOIN dbo.tblContact C ON C.ContactID = CommC.ContactID
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1
WHILE (@@ROWCOUNT >0)
BEGIN
	DELETE TOP (@BatchSize) LP
	FROM dbo.tblLetter_Principal LP 
	INNER JOIN tblLetter L on L.LetterID = LP.LetterID
	INNER JOIN tblAccount A on A.AccountID = L.AccountID
	WHERE A.LoadID = @LoadID
	
END

SELECT 1--Batch delete for tblLetter
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) L
	FROM tblLetter L
	INNER JOIN tblAccount A ON A.AccountID = L.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) DBV
	FROM tblDocumentBlobVersion DBV
	INNER JOIN tblDocumentBlob DB on DBV.DocumentBlobID = DB.DocumentBlobID
	INNER JOIN tblDocument D on D.DocumentID = DB.DocumentID
	INNER JOIN tblAccount A ON A.AccountID = D.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) DB
	FROM tblDocumentBlob DB	
	INNER JOIN tblDocument D on D.DocumentID = DB.DocumentID
	INNER JOIN tblAccount A ON A.AccountID = D.AccountID
	WHERE A.LoadID = @LoadID
	
	
END



SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) D
	FROM tblDocument D
	INNER JOIN tblAccount A ON A.AccountID = D.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblMetaValue_DocumentGroup
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) MVG
	FROM tblMetaValue_DocumentGroup MVG
	INNER JOIN tblDocument D on D.MetaValue_DocumentGroupID = MVG.MetaValue_DocumentGroupID
	INNER JOIN tblLetter L on L.DocumentID = D.DocumentID 
	INNER JOIN tblAccount A ON A.AccountID = L.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblContactAudit
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CAUD
	FROM tblContactAudit CAUD
	INNER JOIN tblContact C ON C.ContactID = CAUD.ContactID
	WHERE C.LoadID = @LoadID
	
	
END

-- Contact-scoped sweeps: catch rows the application created against this load's contacts,
-- which the tblAccount_Contact-routed deletes above never see (they only find rows whose
-- contact is still linked to an account, and only rows this migration itself inserted).
SELECT 1--Batch delete for tblCommunication_Contact (rows stamped by this load)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CommC
	FROM dbo.tblCommunication_Contact CommC
	WHERE CommC.LoadID = @LoadID
END

SELECT 1--Batch delete for tblCommunication_Contact (by contact)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CommC
	FROM dbo.tblCommunication_Contact CommC
	INNER JOIN dbo.tblContact C ON C.ContactID = CommC.ContactID
	WHERE C.LoadID = @LoadID
END

SELECT 1--Batch delete for tblContactDetail (by contact)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CD
	FROM dbo.tblContactDetail CD
	INNER JOIN dbo.tblContact C ON C.ContactID = CD.ContactID
	WHERE C.LoadID = @LoadID
END

-- Stash the contacts reachable through tblAccount_Contact before that table is emptied.
-- A contact created by an EARLIER load but linked to one of this load's accounts has
-- C.LoadID <> @LoadID, so the LoadID sweep below will not find it; this is the only
-- record that it belonged to this load.
IF OBJECT_ID('tempdb..#ACContacts') IS NOT NULL DROP TABLE #ACContacts;
SELECT      DISTINCT AC.ContactID
INTO        #ACContacts
FROM        dbo.tblAccount_Contact AC
            INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
WHERE       A.LoadID = @LoadID;

CREATE UNIQUE CLUSTERED INDEX IX_ACContacts ON #ACContacts (ContactID);

SELECT 1--Batch delete for tblAccount_Contact (must run AFTER every delete that routes through it)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) AC
	FROM tblAccount_Contact AC
	INNER JOIN tblAccount A ON AC.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1--Batch delete for tblAccount_Contact (by contact)
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) AC
	FROM tblAccount_Contact AC
	INNER JOIN tblContact C ON C.ContactID = AC.ContactID
	WHERE C.LoadID = @LoadID
END

SELECT 1--Batch delete for tblContact
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) C
	FROM dbo.tblContact C
	INNER JOIN #ACContacts ACC ON ACC.ContactID = C.ContactID
	WHERE NOT EXISTS ( SELECT 1                     -- a contact shared with another load's
					   FROM   dbo.tblAccount_Contact AC2   -- accounts stays put
					   WHERE  AC2.ContactID = C.ContactID )
END


SELECT 1--Batch delete for tblAddressAudit
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) AA 
	FROM dbo.tblAddressAudit AA
	WHERE AA.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblAddress
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) ADR 
	FROM dbo.tblAddress ADR
	WHERE ADR.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblContactDetailAudit
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CDA
	FROM dbo.tblContactDetailAudit CDA
	WHERE CDA.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblContactDetail
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CD
	FROM dbo.tblContactDetail CD
	WHERE CD.LoadID = @LoadID
	
	
END


SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) DC 
	FROM tblDebtContact DC 
	INNER JOIN tblContact C ON C.ContactID = DC.ContactID
	WHERE C.LoadID = @LoadID
	
	
END


--SELECT 1
--while (@@ROWCOUNT >0)BEGIN
--	DELETE TOP (@BatchSize) DC 
--	FROM tblDebtContact_0 DC 
--	INNER JOIN tblContact C ON C.ContactID = DC.ContactID
--	WHERE C.LoadID = @LoadID
	
	
--END


SELECT 1--Batch delete for tblContact
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) C
	FROM dbo.tblContact C 
	WHERE C.LoadID = @LoadID
	
	
END


SELECT 1--Batch delete for tblMetaValue_AccountSpecifics
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) MV
	FROM tblMetaValue_AccountSpecifics MV
	INNER JOIN dbo.tblMetaValue_AccountSpecificsGroup MVG ON  MVG.MetaValue_AccountSpecificsGroupID = MV.MetaValue_AccountSpecificsGroupID
	INNER JOIN dbo.tblAccountSpecifics ACS ON ACS.MetaValue_AccountSpecificsGroupID = MVG.MetaValue_AccountSpecificsGroupID
	INNER JOIN dbo.tblAccount A ON A.AccountID = ACS.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

-- Batch update for tblMetaValue_AccountSpecificsGroup
SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) MVGACS
	FROM tblMetaValue_AccountSpecificsGroup MVGACS 
	INNER JOIN dbo.tblAccountSpecifics ACS ON ACS.MetaValue_AccountSpecificsGroupID = MVGACS.MetaValue_AccountSpecificsGroupID
	INNER JOIN dbo.tblAccount A ON A.AccountID = ACS.AccountID
	WHERE A.LoadID = @LoadID
	
	
END


SELECT 1--Batch delete for tblAccountSpecifics
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) ACS
	FROM tblAccountSpecifics ACS
	INNER JOIN tblAccount A ON ACS.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblAllocation
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) AL
	FROM tblAllocation AL
	INNER JOIN tblPayment P ON AL.PaymentID = P.PaymentID
	INNER JOIN tblAccount A ON P.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblAllocation
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) AL 
	FROM tblAllocation AL
	INNER JOIN tblAdjustment ADJ ON AL.AdjustmentID = ADJ.AdjustmentID
	INNER JOIN tblAccount A ON ADJ.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END


SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) PRA
	FROM tblPrincipalAudit PRA
	INNER JOIN tblPrincipal PR ON PRA.PrincipalID = PR.PrincipalID
	INNER JOIN tblAccount A ON PR.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) PR
	FROM tblPrincipal PR
	INNER JOIN tblAccount A ON PR.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblPaymentAudit
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) PA
	FROM tblPaymentAudit PA
	INNER JOIN tblPayment P ON PA.PaymentID = P.PaymentID
	INNER JOIN tblAccount A ON P.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblPayment
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) P
	FROM tblPayment P
	INNER JOIN tblAccount A ON P.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblBankTransaction
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) BT
	FROM tblBankTransaction BT
	INNER JOIN tblpayment P ON P.BankTransactionID = BT.BankTransactionID
	INNER JOIN tblAccount A ON P.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblCostAudit
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CA
	FROM tblCostAudit CA
	INNER JOIN dbo.tblCost C ON C.CostID = CA.CostID
	INNER JOIN tblAccount A ON C.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblCost
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) C
	FROM tblCost C
	INNER JOIN tblAccount A ON C.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblTransaction
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) TR
	FROM tblTransaction TR
	INNER JOIN tblAccount A ON TR.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1
WHILE (@@ROWCOUNT >0)
BEGIN
	DELETE TOP (@BatchSize) T
	FROM tblTask T
	INNER JOIN tblAccount A ON T.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END


SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) E
	FROM tblEntry E
	INNER JOIN tblAccount A ON E.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblEmail
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) E
	FROM tblEmail E
	INNER JOIN tblAccount A ON E.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) ARM
	FROM tblArrangement_ReminderMethod ARM
	INNER JOIN tblArrangement AR ON ARM.ArrangementID = AR.ArrangementID
	INNER JOIN tblAccount A ON AR.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END


SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) ARA
	FROM tblArrangementAudit ARA
	INNER JOIN tblArrangement AR ON ARA.ArrangementID = AR.ArrangementID
	INNER JOIN tblAccount A ON AR.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) ARC
	FROM tblArrangement_Contact ARC
	INNER JOIN tblArrangement AR ON ARC.ArrangementID = AR.ArrangementID
	INNER JOIN tblAccount A ON AR.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1--Batch delete for tblArrangementSchedule
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) ARS
	FROM tblArrangementSchedule ARS
	INNER JOIN tblArrangement AR ON ARS.ArrangementID = AR.ArrangementID
	INNER JOIN tblAccount A ON AR.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID		
END

SELECT 1--Batch delete for tblArrangement
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) AR
	FROM tblArrangement AR
	INNER JOIN tblAccount A ON AR.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblDebtContact
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) DC
	FROM tblDebtContact DC
	INNER JOIN tblAccount A ON DC.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblInvoice
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) I
	FROM tblInvoice I
	INNER JOIN tblAccount A ON I.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END


SELECT 1--Batch delete for tblCallHistory
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) CH
	FROM tblCallHistory CH
	INNER JOIN tblAccount A ON CH.DebtrakAccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblAccountLock
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) ACL
	FROM tblAccountLock ACL 
	INNER JOIN tblAccount A ON A.AccountID = ACL.AccountID
	WHERE A.LoadID = @LoadID
	
	
END

SELECT 1--Batch delete for tblTimeOnAccount_Outcome
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) TOAO
	FROM tblTimeOnAccount_Outcome TOAO
	INNER JOIN tblTimeOnAccount TOA ON TOA.TimeOnAccountID = TOAO.TimeOnAccountID
	INNER JOIN tblAccount A ON A.AccountID = TOA.AccountID
	WHERE A.LoadID = @LoadID
	
	
END
	
SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) ADR
	FROM tblAddress ADR
	INNER JOIN dbo.tblContact C ON C.ContactID = ADR.ContactID
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE   A.LoadID = @LoadID
	

End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) CD
FROM dbo.tblContactDetail CD
INNER JOIN dbo.tblContact C ON C.ContactID = CD.ContactID
INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) SMS
FROM tblSMSOutput SMS
INNER JOIN tblAccount A ON SMS.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) E
FROM tblEmail E
INNER JOIN tblAccount A ON A.AccountID = E.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) Comm
FROM dbo.tblCommunication Comm 
INNER JOIN tblEmail E on E.CommunicationID = Comm.CommunicationID
INNER JOIN dbo.tblAccount A ON A.AccountID = E.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) Comm
FROM dbo.tblCommunication Comm 
INNER JOIN dbo.tblCommunication_Contact CommC ON CommC.CommunicationID = Comm.CommunicationID
INNER JOIN dbo.tblContact C ON C.ContactID = CommC.ContactID
INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
WHERE   A.LoadID = @LoadID


End

SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) CommC
FROM dbo.tblCommunication_Contact CommC 
INNER JOIN dbo.tblContact C ON C.ContactID = CommC.ContactID
INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) E
FROM tblEmail E
INNER JOIN tblAccount A ON A.AccountID = E.AccountID
WHERE   A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) E
FROM tblEmail E
INNER JOIN tblCommunication Comm on Comm.CommunicationID = E.CommunicationID
INNER JOIN tblCommunication_Contact CommC ON CommC.CommunicationID = Comm.CommunicationID
INNER JOIN tblContact C ON C.ContactID = CommC.ContactID
INNER JOIN tblAccount_Contact AC ON AC.ContactID = C.ContactID
INNER JOIN tblAccount A ON A.AccountID = AC.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) E
FROM tblEmail E
INNER JOIN tblCommunication Comm on Comm.CommunicationID = E.CommunicationID
WHERE  Comm.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)
BEGIN
DELETE TOP (@BatchSize)  LD
FROM dbo.tblLetterData LD
INNER join tblLetter L on LD.LetterID = L.LetterID
INNER JOIN tblAccount A on A.AccountID = L.AccountID
where A.LoadID = @LoadID
End

SELECT 1
while (@@ROWCOUNT >0)
BEGIN
DELETE TOP (@BatchSize) LP
FROM dbo.tblLetterPDF LP
INNER join tblLetter L on LP.LetterID = L.LetterID
INNER JOIN tblAccount A on A.AccountID = L.AccountID
WHERE A.LoadID = @LoadID
End

SELECT 1
while (@@ROWCOUNT >0)
BEGIN
DELETE TOP (@BatchSize) Comm
FROM dbo.tblCommunication Comm
where LoadID = @LoadID
End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) L
FROM tblLetter L
INNER JOIN tblAccount A ON A.AccountID = L.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) D
FROM tblDocument D
inner join tblLetter L on L.DocumentID = D.DocumentID 
INNER JOIN tblAccount A ON A.AccountID = L.AccountID
WHERE   A.LoadID = @LoadID


End

SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) D
FROM tblDocument D
INNER JOIN tblAccount A ON A.AccountID = D.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) MVG
FROM tblMetaValue_DocumentGroup MVG
INNER JOIN tblDocument D on D.MetaValue_DocumentGroupID = MVG.MetaValue_DocumentGroupID
inner join tblLetter L on L.DocumentID = D.DocumentID 
INNER JOIN tblAccount A ON A.AccountID = L.AccountID
WHERE   A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) CAUD
FROM tblContactAudit CAUD
INNER JOIN tblContact C ON C.ContactID = CAUD.ContactID
WHERE C.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) C
FROM dbo.tblContact C 
INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) ADR 
FROM dbo.tblAddress ADR
WHERE   ADR.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) CDA
FROM dbo.tblContactDetailAudit CDA
WHERE   CDA.LoadID = @LoadID


End

SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) CD
FROM dbo.tblContactDetail CD
WHERE   CD.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) DC 
FROM tblDebtContact DC 
INNER JOIN tblContact C ON C.ContactID = DC.ContactID
WHERE C.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) C
FROM dbo.tblContact C 
WHERE   C.LoadID = @LoadID


End




SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) AL
FROM tblAllocation AL
INNER JOIN tblPayment P ON AL.PaymentID = P.PaymentID
INNER JOIN tblAccount A ON P.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) AL 
FROM tblAllocation AL
INNER JOIN tblAdjustment ADJ ON AL.AdjustmentID = ADJ.AdjustmentID
INNER JOIN tblAccount A ON ADJ.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) PR
FROM tblPrincipal PR
INNER JOIN tblAccount A ON PR.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End

SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) PA
FROM tblPaymentAudit PA
INNER JOIN tblPayment P ON PA.PaymentID = P.PaymentID
INNER JOIN tblAccount A ON P.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID
	

End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) P
FROM tblPayment P
INNER JOIN tblAccount A ON P.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) BT
FROM tblBankTransaction BT
INNER JOIN tblpayment P ON P.BankTransactionID = BT.BankTransactionID
INNER JOIN tblAccount A ON P.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) CA
FROM tblCostAudit CA
INNER JOIN dbo.tblCost C ON C.CostID = CA.CostID
INNER JOIN tblAccount A ON C.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) C
FROM tblCost C
INNER JOIN tblAccount A ON C.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) TR
FROM tblTransaction TR
INNER JOIN tblAccount A ON TR.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End
	

SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) E
FROM tblEntry E
INNER JOIN tblAccount A ON E.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) E
FROM tblEmail E
INNER JOIN tblAccount A ON E.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) ARS
FROM tblArrangementSchedule ARS
INNER JOIN tblArrangement AR ON ARS.ArrangementID = AR.ArrangementID
INNER JOIN tblAccount A ON AR.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) AR
FROM tblArrangement AR
INNER JOIN tblAccount A ON AR.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) DC
FROM tblDebtContact DC
INNER JOIN tblAccount A ON DC.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) I
FROM tblInvoice I
INNER JOIN tblAccount A ON I.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) MVACS
FROM tblMetaValue_AccountSpecifics MVACS
INNER JOIN dbo.tblMetaValue_AccountSpecificsGroup MVGACS ON  MVGACS.MetaValue_AccountSpecificsGroupID = MVACS.MetaValue_AccountSpecificsGroupID
INNER JOIN dbo.tblAccountSpecifics ACS ON ACS.MetaValue_AccountSpecificsGroupID = MVGACS.MetaValue_AccountSpecificsGroupID
INNER JOIN dbo.tblAccount A ON A.AccountID = ACS.AccountID
WHERE  A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) MVGACS
FROM tblMetaValue_AccountSpecificsGroup MVGACS 
INNER JOIN dbo.tblAccountSpecifics ACS ON ACS.MetaValue_AccountSpecificsGroupID = MVGACS.MetaValue_AccountSpecificsGroupID
INNER JOIN dbo.tblAccount A ON A.AccountID = ACS.AccountID
WHERE  A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) ACS
FROM tblAccountSpecifics ACS
INNER JOIN tblAccount A ON ACS.AccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) CH
FROM tblCallHistory CH
INNER JOIN tblAccount A ON CH.DebtrakAccountID = A.AccountID
WHERE   A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) ACL
FROM tblAccountLock ACL 
INNER JOIN tblAccount A ON A.AccountID = ACL.AccountID
WHERE   A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) TOAO
FROM tblTimeOnAccount_Outcome TOAO
INNER JOIN tblTimeOnAccount TOA ON TOA.TimeOnAccountID = TOAO.TimeOnAccountID
INNER JOIN tblAccount A ON A.AccountID = TOA.AccountID
WHERE   A.LoadID = @LoadID


End


	
SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) TOA
FROM tblTimeOnAccount TOA
INNER JOIN tblAccount A ON A.AccountID = TOA.AccountID
WHERE   A.LoadID = @LoadID


End



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) ACT
FROM tblAccount_Contact_Transaction ACT
INNER JOIN tblAccount A on ACT.AccountID = A.AccountID
WHERE A.LoadID = @LoadID


End


SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) AET
FROM tblAccount_Entity_Transaction AET
INNER JOIN tblAccount A on AET.AccountID = A.AccountID
WHERE A.LoadID = @LoadID


End




SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) AP
FROM tblAccount_Pool AP
INNER JOIN tblAccount A on AP.AccountID = A.AccountID
WHERE A.LoadID = @LoadID


End

SELECT 1
while (@@ROWCOUNT >0)
BEGIN
DELETE TOP (@BatchSize) P
FROM tblPayno P
INNER JOIN tblAccount A on P.AccountID = A.AccountID
WHERE A.LoadID = @LoadID
END

SELECT 1
while (@@ROWCOUNT >0)
BEGIN
	DELETE TOP (@BatchSize) M
	FROM tblMedia M
	INNER JOIN tblAccount A on M.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
while (@@ROWCOUNT >0)
BEGIN
	DELETE TOP (@BatchSize) ALH
	FROM tblAccountLinkHistory ALH
	INNER JOIN tblAccount A on ALH.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
while (@@ROWCOUNT >0)
BEGIN
	DELETE TOP (@BatchSize) CE
	FROM tblCallExclusion CE
	INNER JOIN tblAccount A on CE.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
WHILE (@@ROWCOUNT >0)
BEGIN
	DELETE TOP (@BatchSize) WTB
	FROM tblWorkflowTriggerBatch WTB	
	INNER JOIN dbo.tblAccount A ON A.AccountID = WTB.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
WHILE (@@ROWCOUNT >0)	
BEGIN
	DELETE TOP (@BatchSize) WT
	FROM tblWorkflowTrigger WT
	INNER JOIN dbo.tblAccount A ON A.AccountID = WT.AccountID
	WHERE A.LoadID = @LoadID
END


SELECT 1
WHILE (@@ROWCOUNT >0)	
BEGIN
	DELETE TOP (@BatchSize) AcT
	FROM tblAccount_Token AcT
	INNER JOIN dbo.tblAccount A ON A.AccountID = AcT.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
WHILE (@@ROWCOUNT >0)	
BEGIN
	DELETE TOP (@BatchSize) BT
	FROM tblBillableTime BT
	INNER JOIN dbo.tblAccount A ON A.AccountID = BT.AccountID
	WHERE A.LoadID = @LoadID
END



SELECT 1
while (@@ROWCOUNT >0)BEGIN
DELETE TOP (@BatchSize) A
FROM tblAccount A
WHERE   A.LoadID = @LoadID


End




IF OBJECT_ID('tempdb..#ACContacts') IS NOT NULL DROP TABLE #ACContacts;

END TRY
BEGIN CATCH


    SELECT  @Failed     = 1 ,
            @ErrNumber  = ERROR_NUMBER() ,
            @ErrLine    = ERROR_LINE() ,
            @ErrMessage = ERROR_MESSAGE();

END CATCH


DECLARE @csSchema  SYSNAME ,
        @csTable   SYSNAME ,
        @csName    SYSNAME ,
        @csTrusted BIT ,
        @csSQL     NVARCHAR(MAX);

IF OBJECT_ID('tempdb..#NotRetrusted') IS NOT NULL DROP TABLE #NotRetrusted;
CREATE TABLE #NotRetrusted (TableName SYSNAME, ConstraintName SYSNAME, Reason NVARCHAR(400));

DECLARE RestoreCur CURSOR LOCAL FAST_FORWARD FOR
    SELECT  SchemaName, TableName, ConstraintName,
            CASE WHEN WasTrusted = 1 OR @RestoreConstraintTrust = 1 THEN 1 ELSE 0 END
    FROM    #ConstraintState
    WHERE   WasDisabled = 0;          -- anything already off stays off

OPEN RestoreCur;
FETCH NEXT FROM RestoreCur INTO @csSchema, @csTable, @csName, @csTrusted;

WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        SET @csSQL = N'ALTER TABLE ' + QUOTENAME(@csSchema) + N'.' + QUOTENAME(@csTable)
                   + CASE WHEN @csTrusted = 1 THEN N' WITH CHECK' ELSE N'' END
                   + N' CHECK CONSTRAINT ' + QUOTENAME(@csName) + N';';
        EXEC sp_executesql @csSQL;
    END TRY
    BEGIN CATCH
        -- Validation found rows the constraint does not accept. Fall back to a
        -- plain re-enable so the constraint is at least on, and report it.
        INSERT INTO #NotRetrusted (TableName, ConstraintName, Reason)
        VALUES (@csTable, @csName, LEFT(ERROR_MESSAGE(), 400));

        BEGIN TRY
            SET @csSQL = N'ALTER TABLE ' + QUOTENAME(@csSchema) + N'.' + QUOTENAME(@csTable)
                       + N' CHECK CONSTRAINT ' + QUOTENAME(@csName) + N';';
            EXEC sp_executesql @csSQL;
        END TRY
        BEGIN CATCH
            -- Nothing further to try; it is already recorded above.
        END CATCH
    END CATCH

    FETCH NEXT FROM RestoreCur INTO @csSchema, @csTable, @csName, @csTrusted;
END

CLOSE RestoreCur;
DEALLOCATE RestoreCur;

SELECT  (SELECT COUNT(*) FROM #ConstraintState)                       AS constraints_captured,
        (SELECT COUNT(*) FROM #ConstraintState WHERE WasDisabled = 1) AS left_disabled_as_found,
        (SELECT COUNT(*) FROM #NotRetrusted)                          AS constraints_not_retrusted;

IF EXISTS (SELECT 1 FROM #NotRetrusted)
    SELECT TableName, ConstraintName, Reason FROM #NotRetrusted ORDER BY TableName, ConstraintName;

DROP TABLE #NotRetrusted;
DROP TABLE #ConstraintState;
DROP TABLE #ToggleTables;
DROP TABLE #Alterable;

-- Constraints are back. Now surface the failure that got us here, if there was one.
IF @Failed = 1
BEGIN
    DECLARE @Rethrow NVARCHAR(2048) =
        N'DT Delete Migrated Data failed for LoadID ' + CONVERT(NVARCHAR(20), @LoadID)
      + N'. Constraints have been restored. Original error '
      + CONVERT(NVARCHAR(20), @ErrNumber) + N' at line '
      + CONVERT(NVARCHAR(20), @ErrLine)  + N': ' + @ErrMessage;
    THROW 50002, @Rethrow, 1;
END
