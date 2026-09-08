INSERT  INTO tblCommunication
        ( CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID ,
          Z_REF ,  --NoteKey
          Z_REF2
        ) --DebtCode
        SELECT  1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                IIF(D.Date_De_Queued is null,1,0) ,
                {{LoadID}} ,
                D.Note_Key ,
                A.AccountNumberPrevious
        FROM    RC_DOCHIST_EXTRACT D
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON D.Extended_Debt_Code = A.AccountNumberPrevious
        WHERE   A.LoadID = {{LoadID}}
                AND A.StatusID = 1
                AND (D.Doc_Link_Via IS NULL OR D.Doc_Link_Via!= 'H')

;