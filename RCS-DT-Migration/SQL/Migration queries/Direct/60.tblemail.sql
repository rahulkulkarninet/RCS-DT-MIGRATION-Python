
INSERT  INTO tblEmail WITH ( ROWLOCK )
        ( AccountID ,
          CommunicationID ,
          Subject ,
          Email ,
          ToEmailAddress ,
          FromEmailAddress ,
          Attachments_MediaAndDocumentGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID,
          Z_REF,
          Z_IDSTR
        )
        SELECT  A.AccountID ,
                Comm.CommunicationID ,
                'Document' ,
                E.Document_Code ,
                E.Email_Addr ,
                '' ,
                NULL ,
                ISNULL(OM.ContactIDDestination, 1) ,
                {{CurrentSessionID}} ,
                E.Queue_Date , --GETDATE(),
                IIF(E.Fail_Date IS NULL,1,0),
                E.ZID,
                E.Debtor_Code
        FROM    RC_EMAIL_EXTRACT E
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON E.Extended_Debt_Code = A.AccountNumberPrevious
                INNER JOIN tblCommunication Comm WITH ( NOLOCK ) ON Comm.Z_REF = E.Doc_Hist_Code
                                                           AND Comm.LoadID = {{LoadID}}
                LEFT JOIN CSRC_OperatorContactMapping OM ON OM.OperatorCode = E.Op_code
        WHERE   A.LoadID = {{LoadID}}
        ;

        INSERT INTO tblCorrespondenceHistory  WITH ( ROWLOCK )
	(   CorrespondenceId,
		CorrespondenceType,
		CorrespondenceSolicited,
		CorrespondenceTS,
		CorrespondenceStatusID,
		AccountID,
		ContactID,
		StatusID,
		CreateID,
		CreateSessionID,
		CreateTS
	)

	SELECT E.EmailID ,                 -- CorrespondenceID
		'Email',                       -- CorrespondenceTtype
		IIF(DH.Solicited = 'Y',1,0),   -- CorrespondenceSolicited
		E.CreateTS,                    -- CorrespondenceTS
		IIF(RCE.Fail_Date IS NULL,2,1),-- CorrespondenceStatusID (2=delivered)
		A.ACCOUNTID,                   -- AccountID
		C.CONTACTID,                   -- ContactID
		E.StatusID,                    -- StatusID
		1,                             -- CreateID
		{{CurrentSessionID}},             -- SessionID
		E.CreateTS                     -- CreateTS

	FROM RC_EMAIL_EXTRACT RCE
                join tblaccount A on A.AccountNumberPrevious = RCE.Extended_Debt_Code
                join tblcontact C on C.Z_REF2 = RCE.Debtor_Code
                                                and C.Z_REF = RCE.Extended_Debt_Code
                                                and C.LoadID = {{LoadID}}
                join tblEmail E on E.Z_REF = RCE.ZID
                                         and E.AccountID = A.AccountID
                                         and E.Z_IDSTR = RCE.Debtor_Code
                                         and E.CreateSessionID = {{CurrentSessionID}}
		JOIN RC_DOCHIST_EXTRACT DH ON RCE.DOC_HIST_CODE = DH.ZID
    WHERE A.LoadID = {{LoadID}}
          AND NOT EXISTS (
                        SELECT 1
                        FROM tblCorrespondenceHistory CH WITH ( NOLOCK )
                        WHERE CH.AccountID = A.AccountID
                          AND CH.CorrespondenceType = 'Email'
                          AND CH.CorrespondenceId = E.EmailID
          )
        ;