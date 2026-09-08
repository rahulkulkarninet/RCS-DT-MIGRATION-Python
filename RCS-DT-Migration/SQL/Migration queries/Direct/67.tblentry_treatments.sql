
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
        SELECT  ISNULL({{EntryTypeID_Treatment}}, -1) ,
                1 ,
                A.AccountID ,
                CONCAT(T.Treatment_Step, ' - ', T.Treatment_Type, ' - ', T.Treatment_Result_Code, ' - ',
                       T.Treatment_Result, ' - ', T.Treatment_Code, ' - ', T.Treatment_Description) ,
                T.Treatment_Date ,
                1 ,
                {{CurrentSessionID}} ,
                T.Treatment_Date ,  --GETDATE() ,
                1 ,
                {{LoadID}}
        FROM    RC_TREATMENT T
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = T.Full_Debt_Code
        WHERE   A.LoadID = {{LoadID}}
;