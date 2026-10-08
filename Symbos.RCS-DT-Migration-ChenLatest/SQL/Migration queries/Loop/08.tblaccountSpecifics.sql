INSERT  INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                {{AccountSpecificsGroupID}} ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = {{LoadID}}
                AND MetaField_AccountSpecificsGroupID = {{AccountSpecificsGroupID}}
                ;
