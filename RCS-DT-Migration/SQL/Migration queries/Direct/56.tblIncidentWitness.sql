INSERT  INTO tblIncidentWitness WITH ( ROWLOCK )
        ( AccountIncidentID ,
          ContactID,
          Remark,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )

	SELECT 
		AI.AccountIncidentID,
		C.ContactID,
		LEFT(RP.Witness_Statement, 500),
		1,
		{{CurrentSessionID}},
		GETDATE(),
		1,
		{{LoadID}}

	FROM tblaccount A
		JOIN tblAccountIncident AI ON AI.AccountID = A.AccountID
		JOIN RC_RELATEDPARTY RP ON RP.Extended_Debt_Code = A.AccountNumberPrevious 
		JOIN tblContact C ON C.Z_REF2 = RP.ZID
	WHERE A.loadID = {{LoadID}}
	AND C.LoadID = {{LoadID}}