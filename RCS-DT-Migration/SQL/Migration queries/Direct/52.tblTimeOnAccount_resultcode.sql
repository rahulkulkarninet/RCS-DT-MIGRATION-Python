INSERT  INTO tblTimeOnAccount
        ( ContactID ,
          AccountID ,
          SessionID ,
          TimeOnAccount ,
          AccountOpened ,
          AccountClosed
        )
        SELECT  1 ,
                A.AccountID ,
                {{CurrentSessionID}} ,
                '1900-01-01 00:00:1.000' ,   -- 1 sec counting from 1900-01-01 00:00:00.000
                DATEADD(S, -1, GETDATE()) ,
                GETDATE()
        FROM    tblAccount A WITH ( NOLOCK )
                INNER JOIN RC_ACCOUNT_EXTRACT RC WITH ( NOLOCK ) ON A.AccountNumberPrevious = RC.Full_Debt_Code
        WHERE   A.LoadID = {{LoadID}}
                AND A.StatusID = 1

INSERT  INTO tblTimeOnAccount_Outcome
        ( TimeOnAccountID ,
          OutcomeID
        )
        SELECT  TOA.TimeOnAccountID ,
                O.OutcomeID
        FROM    tblTimeOnAccount TOA WITH ( NOLOCK )
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON TOA.AccountID = A.AccountID
                INNER JOIN RC_ACCOUNT_EXTRACT RC WITH ( NOLOCK ) ON A.AccountNumberPrevious = RC.Full_Debt_Code
                INNER JOIN tblOutcome O WITH ( NOLOCK ) ON O.OutcomeCode = RC.Result_Code
        WHERE   A.LoadID = {{LoadID}}
                AND ISNULL(RC.Result_Code, '') <> ''
                AND A.StatusID = 1
;