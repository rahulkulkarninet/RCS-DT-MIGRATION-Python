-- Incident Details
INSERT  INTO tblAccountIncident WITH ( ROWLOCK )
        ( AccountID ,
          IncidentTypeID ,
          IncidentDate ,
          IncidentDescription ,
          AddressID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID,
          Z_DB
        )
		SELECT
	        A.AccountID,
	        IT.IncidentTypeID, --IncidentTypeID, resolved via variables/incident_type_codes.json
	        I.IncidentDate,
	        LEFT(I.IncidentDescription, 500),
	        Addr.AddressID,
	        1,
	        {{CurrentSessionID}},
	        GETDATE(),
	        1,
	        {{LoadID}},
			I.FullDebtCode

        FROM tblAccount A
	        JOIN RC_ACCOUNT_EXTRACT AE ON AE.Full_Debt_Code = A.AccountNumberPrevious
	        JOIN RC_DRINSURANCE I ON I.FullDebtCode = A.AccountNumberPrevious 
	        JOIN tblAddress Addr ON Addr.z_ref = CAST(AE.Short_Debt_Code AS VARCHAR) + '*INC'
	        LEFT JOIN tblIncidentType IT ON AE.Cause_Description = IT.IncidentType
        WHERE A.loadid = {{LoadID}}
        AND Addr.loadid = {{LoadID}}