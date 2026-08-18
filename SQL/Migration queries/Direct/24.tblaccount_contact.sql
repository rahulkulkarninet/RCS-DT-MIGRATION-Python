
INSERT  INTO tblAccount_Contact WITH ( ROWLOCK )
        ( AccountID ,
          ContactID ,
          RelationshipID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS
        )
        SELECT  a.AccountID ,
                c.ContactID ,
                1--RelationshipID, 1 - Primary Debtor
                ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                GETDATE()
        FROM    tblAccount A WITH ( NOLOCK )
                INNER JOIN tblContact C WITH ( NOLOCK ) ON ( A.AccountNumberPrevious = C.Z_REF
                                                             AND C.StatusID = 1
                                                           )
        WHERE   A.LoadID = {{LoadID}}
                AND C.LoadID = {{LoadID}}
        ORDER BY C.ContactID ASC
;