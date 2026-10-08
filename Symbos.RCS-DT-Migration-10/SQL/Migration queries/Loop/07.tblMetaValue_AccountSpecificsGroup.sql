INSERT  INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  {{AccountSpecificsGroupID}} ,
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                {{LoadID}}
        FROM    tblAccount A
        WHERE   LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = {{AccountSpecificsGroupID}}
                                        AND Z_AccountID = A.AccountID )
                                        ;