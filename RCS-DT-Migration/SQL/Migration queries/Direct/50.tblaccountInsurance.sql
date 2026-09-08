INSERT  INTO tblAccountInsurance WITH ( ROWLOCK )
        ( AccountIncidentID ,
		  InsuranceRefTypeID,
          InsurantContactID,
          PolicyNumber,
          ReferenceToRego,
          InsuredItems,
          ClaimNumber,
		  LiabilityAdmitted,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID,
          Z_ID
        )
	SELECT 
		AI.AccountIncidentID,
		2, -- Client Insurant
		C.ContactID,
		I.InsuredPropertyPolicyNo,
		I.InsuredPropertyRegistration,
		I.InsuredPropertyDescription,
		I.InsurerClaimNo,
		0, -- Liability admitted (no)
		1,
		{{CurrentSessionID}},
		GETDATE(),
		1,
		{{LoadID}},
      I.FullDebtCode
	FROM tblaccount A
		JOIN tblAccountIncident AI ON AI.AccountID = A.AccountID
		JOIN RC_DRINSURANCE I ON A.AccountNumberPrevious = I.FullDebtCode
		JOIN tblContact C ON C.Z_REF2 = CAST(I.ShortDebtCode AS VARCHAR) + '*INS'
	WHERE A.loadID = {{LoadID}}
	AND C.LoadID = {{LoadID}}