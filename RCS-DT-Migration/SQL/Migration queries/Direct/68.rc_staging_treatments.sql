DECLARE @InsertedTreatments TABLE
(
                StagingTreatmentID BIGINT,
                LoadID INT,
                EntityID INT,
                AccountID INT
)
;

INSERT INTO RC_STAGING_TREATMENTS WITH ( ROWLOCK )
        ( AccountID ,
          EntityID ,
          AccountStatusID ,
          LoadID ,
          LoadDate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Current_Treatment ,
          Next_Step_No_1 ,
          Next_Treatment_Date ,
          Last_Treatment_Step_Date
        )
        OUTPUT  inserted.StagingTreatmentID,
                inserted.LoadID,
                inserted.EntityID,
                inserted.AccountID
        INTO    @InsertedTreatments

        SELECT  A.AccountID ,
                A.EntityID ,
                A.AccountStatusID ,
                A.LoadID ,
                A.LoadDate ,
                A.CreateID,
                A.CreateSessionID ,
                A.CreateTS ,
                A.StatusID ,
                RC.Current_Treatment,
                RC.Next_Step_No_1,
                RC.Next_Treatment_Date ,
                RC.Last_Treatment_Step_Date
        FROM    tblAccount A WITH ( NOLOCK )
                INNER JOIN RC_ACCOUNT_EXTRACT RC WITH ( NOLOCK ) ON A.AccountNumberPrevious = RC.Full_Debt_Code
        WHERE   A.LoadID = {{LoadID}}
;

INSERT INTO RC_STAGING_TREATMENT_LINES WITH ( ROWLOCK )
        ( StagingTreatmentID ,
          AccountID ,
          EntityID ,
          AccountStatusID ,
          LoadID ,
          LoadDate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Treatment_Date ,
          Treatment_Code ,
          Treatment_Description ,
          Treatment_Step ,
          Treatment_Type ,
          Treatment_Result_Code ,
          Treatment_Result
        )
        SELECT  H.StagingTreatmentID ,
                A.AccountID ,
                A.EntityID ,
                A.AccountStatusID ,
                A.LoadID ,
                A.LoadDate ,
                A.CreateID ,
                A.CreateSessionID ,
                A.CreateTS ,
                A.StatusID ,
                T.Treatment_Date ,
                T.Treatment_Code, 
                T.Treatment_Description ,
                T.Treatment_Step ,
                T.Treatment_Type ,
                T.Treatment_Result_Code ,
                T.Treatment_Result
        FROM    RC_TREATMENT T WITH ( NOLOCK )
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = T.Full_Debt_Code
                LEFT JOIN @InsertedTreatments H
                       ON H.LoadID = A.LoadID
                      AND H.EntityID = A.EntityID
                      AND H.AccountID = A.AccountID
        WHERE   A.LoadID = {{LoadID}}
;