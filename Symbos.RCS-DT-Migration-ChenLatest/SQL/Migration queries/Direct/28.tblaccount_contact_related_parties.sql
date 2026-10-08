
INSERT  INTO  tblAccount_Contact WITH ( ROWLOCK )
        ( AccountID ,
          ContactID ,
          RelationshipID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS
        )
    SELECT 
        A.AccountID ,
        C.ContactID ,
        RPA.Related_Party_Type_Code_RelationshipID , --RelationshipID, set by related_party_type_service.py
        1 ,
        1,
        {{CurrentSessionID}} ,
        GETDATE()
    FROM
        tblContact C WITH ( NOLOCK )
        INNER JOIN RC_RELATEDPARTY RPA ON C.Z_REF2 = RPA.ZID
        INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CONVERT(nvarchar(100), RPA.Extended_Debt_Code)
            WHERE
                A.LoadID = {{LoadID}}
;