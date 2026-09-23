INSERT  INTO tblSMSOutput WITH ( ROWLOCK )
        ( AccountID ,
          SMSOutputStatusID ,
          Mobile ,
          MessageFrom ,
          MessageContent ,
          DateForSending ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS,
          Z_ID,
          Z_REF
        )
        SELECT  A.AccountID ,
                IIF(RC_SMS.Error_Message IS NULL, 2, 5) , --Error or Sent based on the date
                RC_SMS.Mobile_Phone ,
                REPLACE(RC_SMS.Sms_Source_Tag, ',', '') ,
                RC_SMS.Message_Text ,
                RC_SMS.Date_to_Send ,
                1 ,
                ISNULL(OM.ContactID, {{DefaultOperatorContactID}}) ,
                {{CurrentSessionID}} ,
                RC_SMS.Date_Queued, --GETDATE()
                RC_SMS.ZID,
                RC_SMS.Contact_Ref
        FROM    RC_SMS
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON CONVERT(nvarchar(100), RC_SMS.Extended_Debt_Code) = A.AccountNumberPrevious
                OUTER APPLY ( SELECT TOP 1
                                        C.ContactID
                              FROM      tblContact C WITH ( NOLOCK )
                              WHERE     C.UserName = LTRIM(RTRIM(REPLACE(RC_SMS.Operator_Code, NCHAR(160), ' ')))
                              ORDER BY  CASE WHEN ISNULL(C.StatusID, 0) = 1 THEN 0 ELSE 1 END ,
                                        C.ContactID
                            ) OM
        WHERE   A.LoadID = {{LoadID}}

        
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

		select 
		so.SMSOutputID ,                   -- CorrespondenceID
		'SMS',                             -- CorrespondenceTtype
		IIF(S.Solicited = 'Y',1,0),        -- CorrespondenceSolicited
		so.CreateTS,                       -- CorrespondenceTS
		IIF(S.Error_Message IS NULL, 2, 1),-- CorrespondenceStatusID (2=delivered)
		A.ACCOUNTID,                       -- AccountID
		C.CONTACTID,                       -- ContactID
		so.StatusID,                       -- StatusID
		1,                                 -- CreateID
		{{CurrentSessionID}},              -- CreateSessionID
		so.CreateTS                        -- CreateTS

		from RC_SMS S
		join tblaccount A on A.AccountNumberPrevious = CONVERT(nvarchar(100), S.Extended_Debt_Code)
		join tblcontact C on C.Z_REF2 = S.Contact_Ref
						and C.Z_REF = CONVERT(nvarchar(200), S.Extended_Debt_Code)
						and C.LoadID = {{LoadID}}
		join tblSMSOutput SO on CONVERT(nvarchar(50), SO.Z_ID) = S.ZID
					 and SO.AccountID = A.AccountID
					 and SO.Z_REF = S.Contact_Ref
					 and SO.CreateSessionID = {{CurrentSessionID}}
		where A.LoadID = {{LoadID}}
		  AND NOT EXISTS (
				SELECT 1
				FROM tblCorrespondenceHistory CH WITH ( NOLOCK )
				WHERE CH.AccountID = A.AccountID
				  AND CH.CorrespondenceType = 'SMS'
				  AND CH.CorrespondenceId = SO.SMSOutputID
		  )
;