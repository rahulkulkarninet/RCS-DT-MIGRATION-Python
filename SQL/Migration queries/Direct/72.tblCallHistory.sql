INSERT  INTO tblCallHistory
        ( CallDataSourceID ,
          SequenceNumber ,
          DebtrakAccountID ,
          DiallerLogin ,
          CallStartDateTime ,
          CallEndDateTime ,
          CallWrapDateTime ,
          AgentDisposition ,
          SwitchDisposition ,
          CallTypeId ,
          CreateTS ,
          StatusID ,
          AgentDispositionDesc ,
          SwitchDispositionDesc ,
          CommunicationID,
          Z_REF
        )
        SELECT  1 , --CallDataSourceID	
                NULL , --,SequenceNumber	
                A.AccountID ,--,DebtrakAccountID	
                NULL , --,DiallerLogin	
                DC.Date ,--,CallStartDateTime	
                NULL ,--,CallEndDateTime	
                NULL ,--,CallWrapDateTime	
                NULL , --,AgentDisposition	
                NULL , --,SwitchDisposition	
                NULL ,--,CallTypeId	    
                DC.Date ,--,CreateTS	
                1 ,--,StatusID	
                NULL ,--,AgentDispositionDesc	
                NULL ,--,SwitchDispositionDesc	
                NULL ,--,CommunicationID	
                DC.DebtContactID --,Z_REF
        FROM    RC_DEBT_CONTACTS DC
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = DC.Extended_Debt_Code
                LEFT JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = DC.Multi_Recipient_Key
        WHERE   A.LoadID = {{LoadID}}
		AND		DC.Type IN ('I','O','V') -- Only inbound/outboun calls and IVR
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

			SELECT CH.CallHistoryID ,             -- CorrespondenceID
				IIF(DC.Type = 'V','IVR','Phone'), -- CorrespondenceTtype
				IIF(DC.Solicited = 'Y',1,0),      -- CorrespondenceSolicited
				CH.CreateTS,                      -- CorrespondenceTS
				1,                                -- CorrespondenceStatusID
				A.ACCOUNTID,                      -- AccountID
				C.CONTACTID,                      -- ContactID
				CH.statusid,                      -- StatusID
				1,                                -- CreateID
				{{CurrentSessionID}},                -- SessionID
				CH.CreateTS                       -- CreateTS

				from RC_DEBT_CONTACTS DC
					join tblaccount A on A.AccountNumberPrevious = DC.Extended_Debt_Code
                                        join tblcontact C on C.Z_REF2 = DC.Multi_Recipient_Key
                                                                        and C.Z_REF = DC.Extended_Debt_Code
                                                                        and C.LoadID = {{LoadID}}
                                        join tblCallHistory CH on CH.Z_REF = DC.DebtContactID
                                                                        and CH.DebtrakAccountID = A.AccountID
				WHERE A.LOADID = {{LoadID}}
                                AND DC.Type in ('O','I','V')
                                AND NOT EXISTS (
                                        SELECT 1
                                        FROM tblCorrespondenceHistory CHIST WITH ( NOLOCK )
                                        WHERE CHIST.AccountID = A.AccountID
                                          AND CHIST.CorrespondenceType = IIF(DC.Type = 'V','IVR','Phone')
                                          AND CHIST.CorrespondenceId = CH.CallHistoryID
                                )