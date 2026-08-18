
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
        CASE 
            WHEN (RPA.Related_Party_Type_Code = 'GTR') THEN {{RelationshipID_Guarantor}}
            WHEN (RPA.Related_Party_Type_Code = 'ACH') THEN {{RelationshipID_AdditionalCardHolder}}
            WHEN (RPA.Related_Party_Type_Code = 'SPO') THEN {{RelationshipID_Spouse}}
            WHEN (RPA.Related_Party_Type_Code = 'REF') THEN {{RelationshipID_Reference}}
            WHEN (RPA.Related_Party_Type_Code = 'SOL') THEN {{RelationshipID_Solicitor}}
            WHEN (RPA.Related_Party_Type_Code = 'WIT') THEN {{RelationshipID_Witness}}

            ELSE {{RelationshipID_Other}} -- Other                 
        END ,
        1 ,
        1,
        {{CurrentSessionID}} , 
        GETDATE()
    FROM 
        tblContact C WITH ( NOLOCK )
        INNER JOIN RC_RELATEDPARTY RPA ON C.Z_REF2 = RPA.ZID
        INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = RPA.Extended_Debt_Code
            WHERE
                A.LoadID = {{LoadID}}
;