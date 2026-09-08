
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
        R.RelationshipID , --RelationshipID, resolved via variables/related_party_type_codes.json
        1 ,
        1,
        {{CurrentSessionID}} ,
        GETDATE()
    FROM
        tblContact C WITH ( NOLOCK )
        INNER JOIN RC_RELATEDPARTY RPA ON C.Z_REF2 = RPA.ZID
        INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = RPA.Extended_Debt_Code
        LEFT JOIN tblRelationship R ON RPA.Related_Party_Type_Code = R.Relationship
            WHERE
                A.LoadID = {{LoadID}}
;