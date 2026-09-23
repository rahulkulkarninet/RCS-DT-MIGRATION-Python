INSERT  INTO tblWorkflowLine WITH ( ROWLOCK )
        ( AccountID ,
          AccountStatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          MasterWorkflowID ,
          LoadID
        )
        SELECT  A.AccountID ,
                A.AccountStatusID ,
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 AS StatusID ,
                E.DefautMasterWorkflowID AS MasterWorkflowID ,
                {{LoadID}}
        FROM    tblAccount A WITH ( NOLOCK )
                INNER JOIN tblEntity E WITH ( NOLOCK ) ON A.EntityID = E.EntityID
        WHERE   A.LoadID = {{LoadID}}
;