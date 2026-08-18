-- Disable constraints to speed up deletions
ALTER TABLE tblLastLetterSent NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAlert NOCHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowLine_NavigationAction NOCHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowHistory NOCHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowLine_Contact NOCHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowLine NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Contact NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAddress NOCHECK CONSTRAINT ALL;		
ALTER TABLE tblAddressAudit NOCHECK CONSTRAINT ALL;
ALTER TABLE tblLog NOCHECK CONSTRAINT ALL;
ALTER TABLE tblLogin NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Contact_DataDictionaryField NOCHECK CONSTRAINT ALL;
ALTER TABLE tblContact_DebtorStatus NOCHECK CONSTRAINT ALL;
ALTER TABLE tblContactDetail NOCHECK CONSTRAINT ALL;
ALTER TABLE tblContactPaymentReferences NOCHECK CONSTRAINT ALL;
ALTER TABLE tblContactProfileAudit NOCHECK CONSTRAINT ALL;
ALTER TABLE tblContactProfile NOCHECK CONSTRAINT ALL;
ALTER TABLE tblContactDetailAudit NOCHECK CONSTRAINT ALL;
ALTER TABLE tblSMSOutput NOCHECK CONSTRAINT ALL;
ALTER TABLE tblEmail NOCHECK CONSTRAINT ALL;
ALTER TABLE tblCommunication NOCHECK CONSTRAINT ALL;
ALTER TABLE tblCommunication_Contact NOCHECK CONSTRAINT ALL;
ALTER TABLE tblLetter_Principal NOCHECK CONSTRAINT ALL;
ALTER TABLE tblLetter NOCHECK CONSTRAINT ALL;
ALTER TABLE tblLetterData NOCHECK CONSTRAINT ALL;
ALTER TABLE tblLetterPDF NOCHECK CONSTRAINT ALL;
ALTER TABLE tblDocumentBlobVersion NOCHECK CONSTRAINT ALL;
ALTER TABLE tblDocumentBlob NOCHECK CONSTRAINT ALL;
ALTER TABLE tblDocument NOCHECK CONSTRAINT ALL;
ALTER TABLE tblMetaValue_DocumentGroup NOCHECK CONSTRAINT ALL;
ALTER TABLE tblContactAudit NOCHECK CONSTRAINT ALL;
ALTER TABLE tblContact NOCHECK CONSTRAINT ALL;
ALTER TABLE tblDebtContact NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAccountSpecifics NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAllocation NOCHECK CONSTRAINT ALL;
ALTER TABLE tblPrincipalAudit NOCHECK CONSTRAINT ALL;
ALTER TABLE tblPrincipal NOCHECK CONSTRAINT ALL;
ALTER TABLE tblPaymentAudit NOCHECK CONSTRAINT ALL;
ALTER TABLE tblPayment NOCHECK CONSTRAINT ALL;
ALTER TABLE tblBankTransaction NOCHECK CONSTRAINT ALL;
ALTER TABLE tblCostAudit NOCHECK CONSTRAINT ALL;
ALTER TABLE tblCost NOCHECK CONSTRAINT ALL;
ALTER TABLE tblTransaction NOCHECK CONSTRAINT ALL;
ALTER TABLE tblTask NOCHECK CONSTRAINT ALL;
ALTER TABLE tblEntry NOCHECK CONSTRAINT ALL;
ALTER TABLE tblArrangement_ReminderMethod NOCHECK CONSTRAINT ALL;
ALTER TABLE tblArrangementSchedule NOCHECK CONSTRAINT ALL;
ALTER TABLE tblArrangementAudit NOCHECK CONSTRAINT ALL;
ALTER TABLE tblArrangement NOCHECK CONSTRAINT ALL;
ALTER TABLE tblArrangement_Contact NOCHECK CONSTRAINT ALL;
ALTER TABLE tblInvoice NOCHECK CONSTRAINT ALL;
ALTER TABLE tblMetaValue_AccountSpecifics NOCHECK CONSTRAINT ALL;
ALTER TABLE tblMetaValue_AccountSpecificsGroup NOCHECK CONSTRAINT ALL;
ALTER TABLE tblCallHistory NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAccountLock NOCHECK CONSTRAINT ALL;
ALTER TABLE tblTimeOnAccount_Outcome NOCHECK CONSTRAINT ALL;
ALTER TABLE tblTimeOnAccount NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Contact_Transaction NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Entity_Transaction NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Pool NOCHECK CONSTRAINT ALL;
ALTER TABLE tblPayno NOCHECK CONSTRAINT ALL;
ALTER TABLE tblMedia NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAccountLinkHistory NOCHECK CONSTRAINT ALL;
ALTER TABLE tblCallExclusion NOCHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowTriggerBatch NOCHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowTrigger NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Token NOCHECK CONSTRAINT ALL;
ALTER TABLE tblAccount NOCHECK CONSTRAINT ALL;

--USE [sqldb-glass-dev-rc]
--go

DECLARE @BatchSize INT = 100000;  
DECLARE @RowsAffected INT = 1;  
DECLARE @LoadID INT = $(LoadID);  

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

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) WF	
	FROM tblWorkflowLine WF
	INNER JOIN tblAccount A ON WF.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
END

SELECT 1
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) AC
	FROM tblAccount_Contact AC
	INNER JOIN tblAccount A ON AC.AccountID = A.AccountID
	WHERE A.LoadID = @LoadID
	
	
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

SELECT 1--Batch delete for tblContact
while (@@ROWCOUNT >0)BEGIN
	DELETE TOP (@BatchSize) C
	FROM dbo.tblContact C 
	INNER JOIN dbo.tblAccount_Contact AC ON AC.ContactID = C.ContactID
	INNER JOIN dbo.tblAccount A ON A.AccountID = AC.AccountID
	WHERE A.LoadID = @LoadID
	
	
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




-- Re-enable constraints
ALTER TABLE tblLastLetterSent CHECK CONSTRAINT ALL;
ALTER TABLE tblAlert CHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowLine CHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowLine_NavigationAction NOCHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowHistory CHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowLine_Contact CHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Contact CHECK CONSTRAINT ALL;
ALTER TABLE tblAddress CHECK CONSTRAINT ALL;
ALTER TABLE tblAddressAudit CHECK CONSTRAINT ALL;
ALTER TABLE tblLog CHECK CONSTRAINT ALL;
ALTER TABLE tblLogin CHECK CONSTRAINT ALL;
ALTER TABLE tblContactDetail CHECK CONSTRAINT ALL;
ALTER TABLE tblContactDetailAudit CHECK CONSTRAINT ALL;
ALTER TABLE tblContactProfileAudit CHECK CONSTRAINT ALL;
ALTER TABLE tblContactProfile CHECK CONSTRAINT ALL;
ALTER TABLE tblContactPaymentReferences CHECK CONSTRAINT ALL;
ALTER TABLE tblSMSOutput CHECK CONSTRAINT ALL;
ALTER TABLE tblEmail CHECK CONSTRAINT ALL;
ALTER TABLE tblCommunication CHECK CONSTRAINT ALL;
ALTER TABLE tblCommunication_Contact CHECK CONSTRAINT ALL;
ALTER TABLE tblLetter_Principal CHECK CONSTRAINT ALL;
ALTER TABLE tblLetter CHECK CONSTRAINT ALL;
ALTER TABLE tblLetterData CHECK CONSTRAINT ALL;
ALTER TABLE tblLetterPDF CHECK CONSTRAINT ALL;
ALTER TABLE tblDocumentBlobVersion CHECK CONSTRAINT ALL;
ALTER TABLE tblDocumentBlob CHECK CONSTRAINT ALL;
ALTER TABLE tblDocument CHECK CONSTRAINT ALL;
ALTER TABLE tblMetaValue_DocumentGroup CHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Contact_DataDictionaryField CHECK CONSTRAINT ALL;
ALTER TABLE tblContact_DebtorStatus CHECK CONSTRAINT ALL;
ALTER TABLE tblContactAudit CHECK CONSTRAINT ALL;
ALTER TABLE tblContact CHECK CONSTRAINT ALL;
ALTER TABLE tblDebtContact CHECK CONSTRAINT ALL;
ALTER TABLE tblAccountSpecifics CHECK CONSTRAINT ALL;
ALTER TABLE tblAllocation CHECK CONSTRAINT ALL;
ALTER TABLE tblPrincipal CHECK CONSTRAINT ALL;
ALTER TABLE tblPrincipalAudit CHECK CONSTRAINT ALL;
ALTER TABLE tblPaymentAudit CHECK CONSTRAINT ALL;
ALTER TABLE tblPayment CHECK CONSTRAINT ALL;
ALTER TABLE tblBankTransaction CHECK CONSTRAINT ALL;
ALTER TABLE tblCostAudit CHECK CONSTRAINT ALL;
ALTER TABLE tblCost CHECK CONSTRAINT ALL;
ALTER TABLE tblTransaction CHECK CONSTRAINT ALL;
ALTER TABLE tblTask CHECK CONSTRAINT ALL;
ALTER TABLE tblEntry CHECK CONSTRAINT ALL;
ALTER TABLE tblArrangement_ReminderMethod CHECK CONSTRAINT ALL;
ALTER TABLE tblArrangementSchedule CHECK CONSTRAINT ALL;
ALTER TABLE tblArrangementAudit CHECK CONSTRAINT ALL;
ALTER TABLE tblArrangement CHECK CONSTRAINT ALL;
ALTER TABLE tblArrangement_Contact CHECK CONSTRAINT ALL;
ALTER TABLE tblInvoice CHECK CONSTRAINT ALL;
ALTER TABLE tblMetaValue_AccountSpecifics CHECK CONSTRAINT ALL;
ALTER TABLE tblMetaValue_AccountSpecificsGroup CHECK CONSTRAINT ALL;
ALTER TABLE tblCallHistory CHECK CONSTRAINT ALL;
ALTER TABLE tblAccountLock CHECK CONSTRAINT ALL;
ALTER TABLE tblTimeOnAccount_Outcome CHECK CONSTRAINT ALL;
ALTER TABLE tblTimeOnAccount CHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Contact_Transaction CHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Entity_Transaction CHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Pool CHECK CONSTRAINT ALL;
ALTER TABLE tblPayno CHECK CONSTRAINT ALL;
ALTER TABLE tblMedia CHECK CONSTRAINT ALL;
ALTER TABLE tblAccountLinkHistory CHECK CONSTRAINT ALL;
ALTER TABLE tblCallExclusion CHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowTriggerBatch CHECK CONSTRAINT ALL;
ALTER TABLE tblWorkflowTrigger CHECK CONSTRAINT ALL;
ALTER TABLE tblAccount_Token CHECK CONSTRAINT ALL;
ALTER TABLE tblAccount CHECK CONSTRAINT ALL;
