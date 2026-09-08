INSERT  INTO tblEntry WITH ( ROWLOCK )
        ( EntryTypeID ,
          EntryStatusID ,
          AccountID ,
          [Entry] ,
          EntryDate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )
        SELECT  49,
                1 ,
                A.AccountID ,
                CONCAT('Result: ', O.OutcomeCode, ' - ', O.Outcome) ,
                RC.Result_date ,
                1 ,
                {{CurrentSessionID}} ,
                RC.Result_date ,
                1 ,
                {{LoadID}}
        FROM    RC_ACCOUNT_EXTRACT RC
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = RC.Full_Debt_Code
                INNER JOIN tblOutcome O WITH ( NOLOCK ) ON O.OutcomeCode = RC.Result_Code
        WHERE   A.LoadID = {{LoadID}}
                AND A.StatusID = 1
                AND ISNULL(RC.Result_Code, '') <> ''
;