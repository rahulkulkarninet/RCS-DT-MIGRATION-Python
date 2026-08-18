INSERT  INTO tblLetter WITH ( ROWLOCK )
        ( AccountID ,
          CommunicationID ,
          DocumentID ,
          Letter ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          PrintedSuccess ,
          PrintedTS ,
          PrintStatusID,
          ErrorReason,
          Z_REF
        )
        SELECT  A.AccountID ,
                Comm.CommunicationID ,
                Doc.DocumentID ,
                D.Document_Code ,
                ISNULL(OM.ContactIDDestination, 1) ,
                {{CurrentSessionID}} ,
                D.Date_Queued ,
                IIF(D.Date_De_Queued is null,1,0) ,
                IIF(D.Date_De_Queued is null,1,0) ,
                D.Date_Printed ,
                IIF(D.Date_De_Queued is null,3,0), --3=Success
                D.Skip_Reason,
                D.ZID
        FROM    RC_DOCHIST_EXTRACT D
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON D.Extended_Debt_Code = A.AccountNumberPrevious
                INNER JOIN tblCommunication Comm WITH ( NOLOCK ) ON Comm.Z_REF = D.Note_Key
                INNER JOIN tblDocument Doc WITH ( NOLOCK ) ON Doc.Z_IDSTR = D.Note_Key
                LEFT JOIN CSRC_OperatorContactMapping OM ON OM.OperatorCode = D.Operator_Code
        WHERE   A.LoadID = {{LoadID}}
        AND (D.Doc_Link_Via IS NULL OR D.Doc_Link_Via!= 'H')

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

		SELECT 
				L.LetterID ,                       -- CorrespondenceID
				'Letter',                          -- CorrespondenceTtype
				IIF(DH.Solicited = 'Y',1,0),       -- CorrespondenceSolicited
				L.CreateTS,                        --CorrespondenceTS
				IIF(DH.Date_De_Queued is null,2,1),-- CorrespondenceStatusID (2=delivered)
				A.ACCOUNTID,                       -- AccountID
				C.CONTACTID,                       -- ContactID
				L.StatusID,                        -- StatusID
				1,                                 -- CreateID
				{{CurrentSessionID}},              -- SessionID
				L.CreateTS                         -- CreateTS

		FROM RC_DOCHIST_EXTRACT DH
				join tblaccount A on A.AccountNumberPrevious = DH.Extended_Debt_Code
				join tblcontact C on C.Z_REF2 = DH.Multi_Letter_keys
				join tblLetter L on L.Z_REF = DH.ZID

        WHERE   A.LoadID = {{LoadID}}
				AND (DH.Doc_Link_Via IS NULL OR DH.Doc_Link_Via!= 'H')
                ;