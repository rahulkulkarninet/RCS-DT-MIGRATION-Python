INSERT  INTO tblAddressAudit WITH ( ROWLOCK )
        ( AddressID ,
          AuditTS ,
          ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          StateID ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    AddressID ,
                GETDATE() ,
                ContactID ,
                AddressTypeID ,
                AddressStatusID ,
                Address ,
                State ,
                StateID ,
                Suburb ,
                Postcode ,
                CountryID ,
                StatusID ,
                CreateID ,
                CreateSessionID ,
                CreateTS ,
                {{LoadID}}
        FROM    tblAddress ADR WITH ( NOLOCK )
        WHERE   ADR.LoadID = {{LoadID}}
                AND ADR.StatusID = 1
;