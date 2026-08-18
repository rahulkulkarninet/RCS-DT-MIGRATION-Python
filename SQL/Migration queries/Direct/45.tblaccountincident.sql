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
	        CASE 
	           WHEN AE.Cause_Description LIKE '%THEFT%' THEN 2  -- Theft
	           WHEN AE.Cause_Description LIKE '%FIRE%' THEN 3   -- Fire
	           WHEN AE.Cause_Description LIKE '%WATER%' THEN 4  -- Flood
	           WHEN AE.Cause_Description LIKE '%DAMAGE%' THEN 8 -- Damage
	        ELSE 9 -- Property
	        END,
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
        WHERE A.loadid = {{LoadID}}
        AND Addr.loadid = {{LoadID}}