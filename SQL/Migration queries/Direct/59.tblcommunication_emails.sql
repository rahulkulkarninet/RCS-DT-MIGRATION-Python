INSERT  INTO tblCommunication
        ( CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID ,
          Z_REF
        )
        SELECT  1 ,
                {{CurrentSessionID}} ,
                E.Queue_Date , --GETDATE(),
                1 ,
                {{LoadID}} ,
                E.Doc_Hist_Code
        FROM    RC_EMAIL_EXTRACT E
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON E.Extended_Debt_Code = A.AccountNumberPrevious
        WHERE   A.LoadID = {{LoadID}}
;
