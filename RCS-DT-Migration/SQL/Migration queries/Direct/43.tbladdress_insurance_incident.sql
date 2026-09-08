INSERT  INTO tblAddress WITH ( ROWLOCK )
        ( ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID,
		  Z_REF
        )
		
        SELECT  
		        C.ContactID ,
                {{AddressTypeID_Home}} ,
                1 ,
                I.IncidentPlace,
                I.IncidentState ,
                I.IncidentSuburb ,
                I.IncidentPCode ,
                {{DefaultCountryID}} ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}} ,
				CAST(I.ShortDebtCode AS VARCHAR) + '*INC' -- flag address as 'incident' to distinguish it from the insured's
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DRINSURANCE I ON CAST(I.ShortDebtCode AS VARCHAR) + '*INS' = C.Z_REF2
        WHERE   LEN(I.IncidentPlace) > 0 AND C.LoadID = {{LoadID}}
